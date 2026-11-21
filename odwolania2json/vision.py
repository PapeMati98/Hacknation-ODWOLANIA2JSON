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

from .textmatch import dates_in_text
from .validators import norm_date

MAX_CROPS = 12             # limit wycinków na dokument
DARK_LEVEL = 30            # jasność (0-255), poniżej której piksel liczymy jako czarny
DARK_SHARE = 0.28          # próg P: udział czarnych pikseli w wycinku, od którego linię uznajemy za zakrytą (skalibrowany:
                           # linie pogrubione dochodzą do 18%, linie z prostokątem zaczynają się od 39% - tools/gate_visual.py)
LEVELS = ("niska", "srednia", "wysoka")
NUMERIC_KINDS = {"nip", "regon", "pesel", "nrb", "krs", "amount", "bzp", "ted"}
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
    spans = [got[i: i + len(want)] for i in range(len(got) - len(want) + 1)]
    if want in spans:
        return "zgodne"
    from difflib import SequenceMatcher
    target = " ".join(want)
    similar = max((SequenceMatcher(None, target, " ".join(span)).ratio() for span in spans), default=0.0)
    return "inne" if similar >= 0.6 else "niezwiazane"


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
        crop = doc.crop(line)
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
