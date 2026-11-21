"""Czytelnik wizualny - drugi, niezależny odczyt wycinka linii skanu (kontrola krzyżowa).

Ten sam model językowy (Qwen3.5-4B) z projektorem obrazu `mmproj` czyta wycinek jednej linii i przepisuje
jej tekst. Zasady (uchwała rady z 2026-11-21, docs/adr):
  - czytelnik nigdy nie jest autorem wartości: tylko potwierdza albo wetuje wartość odczytaną przez OCR,
  - pytany jest wyłącznie o pola, których pewność odczytu nie jest wysoka, najwyżej MAX_CROPS razy na dokument,
  - nie jest pytany o linie z czarnym prostokątem anonimizacji,
  - przy numerze ze złą sumą kontrolną niczego nie zmienia (obowiązuje reguła liczona z samego OCR),
    może tylko dopisać uwagę do listy do sprawdzenia.

Funkcje `judge`, `dark_share` i `adjust` są czystą logiką (testowane bez modelu).
"""
from __future__ import annotations

import re

from .textmatch import dates_in_text, occurrences
from .validators import norm_date

MAX_CROPS = 12             # limit wycinków na dokument
DARK_LEVEL = 30            # jasność (0-255), poniżej której piksel liczymy jako czarny
DARK_SHARE = 0.28          # próg P: udział czarnych pikseli w wycinku, od którego linię uznajemy za zakrytą (skalibrowany:
                           # linie pogrubione dochodzą do 18%, linie z prostokątem zaczynają się od 39% - tools/gate_visual.py)
LEVELS = ("niska", "srednia", "wysoka")
NUMERIC_KINDS = {"nip", "regon", "pesel", "nrb", "krs", "amount"}    # numery ogłoszeń (litery w środku) idą jak tekst
CROP_DPI = 300             # wycinek dla czytelnika renderujemy gęściej niż stronę dla OCR
PROMPT = "Przepisz dokładnie tekst widoczny na obrazie. Podaj wyłącznie ten tekst, bez komentarza."

_SEPARATORS = " .-/"


def digit_fragments(read: str) -> list[list[str]]:
    """Fragmenty liczbowe odczytu: ciągi cyfr, w których wolno pominąć spację, kropkę, myślnik i ukośnik.

    Fragment kończy brzeg odczytu albo znak spoza cyfr i separatorów. Każdy fragment to lista grup cyfr
    rozdzielonych w odczycie spacją (inne separatory nie dzielą grup).
    """
    read = read.replace("–", "-").replace("—", "-")
    out = []
    for m in re.finditer(r"\d[\d .\-/]*", read):
        groups = [re.sub(r"\D", "", g) for g in m.group(0).split(" ")]
        groups = [g for g in groups if g]
        if groups:
            out.append(groups)
    return out


def _words(value: str) -> list[str]:
    """Wyrazy (ciągi znaków bez spacji) bez wielkości liter; z brzegów usuwamy przecinek, średnik, dwukropek,
    kropkę, nawiasy i cudzysłowy."""
    value = value.casefold().replace("–", "-").replace("—", "-")
    return [w for w in (w.strip(",;:.()[]\"'„”«»") for w in value.split()) if w]


def judge(kind: str, value: str, read: str) -> str:
    """Werdykt czytelnika dla wartości odczytanej przez OCR: "zgodne" | "inne" | "niezwiazane".

    Numery: cyfry wartości muszą być równe wszystkim cyfrom jednego fragmentu odczytu (nie jego części).
    Weto ("inne") tylko wtedy, gdy żaden fragment nie jest równy, a jakiś ma inny komplet cyfr. Gdy cyfry
    wartości odpowiadają pełnym grupom wewnątrz dłuższego fragmentu (dwa numery rozdzielone samą spacją),
    odczyt niczego nie rozstrzyga. Daty porównujemy po normalizacji. Tekst: wartość musi być ciągiem całych
    wyrazów odczytu; podobny, ale różny ciąg wyrazów to weto.
    """
    read = (read or "").strip()
    if not read:
        return "niezwiazane"
    if kind == "date":
        want = norm_date(value).value
        found = dates_in_text(read, norm_date)
        if want and want in found:
            return "zgodne"
        return "inne" if found else "niezwiazane"
    if kind in NUMERIC_KINDS:
        want = re.sub(r"\D", "", value)
        fragments = digit_fragments(read)
        if not want or not fragments:
            return "niezwiazane"
        if any("".join(groups) == want for groups in fragments):
            return "zgodne"
        for groups in fragments:                    # pełne grupy wewnątrz dłuższego fragmentu: brak rozstrzygnięcia
            for i in range(len(groups)):
                for j in range(i + 1, len(groups) + 1):
                    if "".join(groups[i:j]) == want:
                        return "niezwiazane"
        return "inne"
    # Tekst (sygnatury, numery z literami): zgodność to ciąg całych wyrazów odczytu - fragment wyrazu nie potwierdza.
    want, got = _words(value), _words(read)
    if not want:
        return "niezwiazane"
    # Odstępy wewnątrz wartości nie mają znaczenia („2025/BZP 00270698” = „2025/BZP00270698”), ale ciąg musi
    # zaczynać się i kończyć na granicy wyrazu odczytu.
    from difflib import SequenceMatcher
    target, similar = "".join(want), 0.0
    for i in range(len(got)):
        joined = ""
        for word in got[i:]:
            joined += word
            if joined == target:
                return "zgodne"
            if len(joined) >= 0.7 * len(target):
                similar = max(similar, SequenceMatcher(None, target, joined).ratio())
            if len(joined) > 1.6 * len(target):
                break
    return "inne" if similar >= 0.6 else "niezwiazane"


def value_span(line_text: str, kind: str, value: str) -> tuple[float, float] | None:
    """Część szerokości linii (0..1), w której stoi wartość - z zapasem po obu stronach. None = cała linia.

    Położenie szacujemy z pozycji znaków w tekście linii (czcionka bywa proporcjonalna, stąd zapas). Krótki
    wycinek wokół wartości jest czytany szybciej i dokładniej niż długa linia w całości.
    """
    n = len(line_text)
    start = end = None
    if kind == "date":
        hits = occurrences(norm_date(value).value or value, line_text, norm_date)
        if hits:
            start = line_text.find(hits[0][1])
            end = start + len(hits[0][1])
    if start is None or start < 0:
        marks = [(i, ch.lower()) for i, ch in enumerate(line_text) if ch.isalnum()]
        compact, want = "".join(ch for _, ch in marks), "".join(ch.lower() for ch in value if ch.isalnum())
        at = compact.find(want) if want else -1
        if at < 0:
            return None
        start, end = marks[at][0], marks[at + len(want) - 1][0] + 1
    pad = max(6, int(0.15 * n))
    left, right = max(0, start - pad) / n, min(n, end + pad) / n
    return None if right - left > 0.8 else (left, right)


def value_crop(doc, line, kind: str, value: str):
    """Wycinek dla czytelnika: okolica wartości w jej linii."""
    return doc.crop(line, dpi=CROP_DPI, span=value_span(line.text, kind, value))


def dark_share(image) -> float:
    """Udział bardzo ciemnych pikseli w wycinku (obraz PIL lub tablica) - ślad czarnego prostokąta."""
    import numpy as np
    arr = np.asarray(image.convert("L") if hasattr(image, "convert") else image)
    if arr.ndim == 3:
        arr = arr.mean(axis=2)
    return float((arr < DARK_LEVEL).mean()) if arr.size else 0.0


def adjust(level: str, verdict: str) -> str | None:
    """Nowy poziom pewności po odczycie wizualnym; None = wartość do wyzerowania (inna wartość w odczycie)."""
    if verdict == "inne":
        return None
    if verdict == "zgodne" and level in LEVELS[:-1]:
        return LEVELS[LEVELS.index(level) + 1]
    return level


class VisualReader:
    """Odczyt wycinków linii modelem z projektorem obrazu. `backend` musi mieć metodę read_image(obraz)."""

    def __init__(self, backend, max_crops: int = MAX_CROPS, dark_share_limit: float = DARK_SHARE):
        self.backend, self.max_crops, self.dark_share_limit = backend, max_crops, dark_share_limit
        self._used: dict[str, int] = {}
        self.log: list[dict] = []

    def check(self, doc, line, kind: str, value: str) -> tuple[str, str]:
        """Zwraca (werdykt, opis): werdykt to "zgodne" | "inne" | "niezwiazane" | "zakryte" | "pominiete"."""
        if line is None or line.box is None:
            return "pominiete", "brak ramki linii"
        if self._used.get(doc.path, 0) >= self.max_crops:
            return "pominiete", "limit wycinków na dokument"
        crop = value_crop(doc, line, kind, value)
        if crop is None:
            return "pominiete", "brak wycinka"
        share = dark_share(crop)
        if share > self.dark_share_limit:
            return "zakryte", f"czarne piksele w wycinku: {share:.0%}"
        self._used[doc.path] = self._used.get(doc.path, 0) + 1
        read = self.backend.read_image(crop, PROMPT)
        verdict = judge(kind, value, read)
        self.log.append({"plik": doc.path, "wartosc": value, "odczyt": read, "werdykt": verdict})
        return verdict, f"czytelnik wizualny: {read!r}"
