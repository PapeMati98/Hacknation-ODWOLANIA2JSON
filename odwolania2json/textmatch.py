"""Dopasowanie wartości zwróconych przez model do faktycznego tekstu dokumentu.

Model bywa nieprecyzyjny w przepisywaniu (ucięte słowo, zgubione cyfry). Zamiast ufać
modelowi, sprawdzamy wartość w tekście i w razie potrzeby dociągamy ją do tego, co
naprawdę jest w dokumencie. Wartość, której nie da się znaleźć, jest odrzucana.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

ID_LENGTHS = {"nip": (10,), "regon": (9, 14), "pesel": (11,), "nrb": (26,), "krs": (10,)}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"[„”“\"'«»]", "", s)
    return re.sub(r"\s+", " ", s)


def appears_in(value: str, text: str) -> bool:
    """Czy wartość występuje w tekście dosłownie (z dokładnością do wielkości liter, spacji i cudzysłowów)."""
    v, t = fold(value), fold(text)
    return v in t or re.sub(r"\s", "", v) in re.sub(r"\s", "", t)


def words_in(value: str, text: str) -> bool:
    """Czy wszystkie słowa wartości występują w tekście jako całe słowa (wartość złożona z kilku miejsc)."""
    words = [w for w in re.findall(r"\w+", fold(value)) if len(w) >= 3]
    have = set(re.findall(r"\w+", fold(text)))
    return bool(words) and all(w in have for w in words)


def person_in(value: str, text: str) -> bool:
    """Imię i nazwisko: w tekście mogą być odmienione (Janowi Kowalskiemu), więc porównujemy tematy słów."""
    words = re.findall(r"\w+", fold(value))
    have = set(re.findall(r"\w+", fold(text)))

    def ok(w: str) -> bool:
        stem = w[: max(3, len(w) - 3)]
        return w in have or any(x.startswith(stem) and abs(len(x) - len(w)) <= 4 for x in have)

    return bool(words) and all(ok(w) for w in words)


def snap_span(value: str, text: str, min_ratio: float = 0.85) -> str | None:
    """Znajduje w tekście fragment najbardziej podobny do wartości (ta sama liczba słów +-1).

    Model bywa niedokładny w przepisywaniu (zmieniona końcówka, literówka). Zamiast jego wersji
    zwracamy dosłowny fragment dokumentu - o ile podobieństwo jest wysokie.
    """
    n = len(value.split())
    target = fold(value)
    if not n or len(target) < 4:
        return None
    tokens = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    sm = SequenceMatcher(autojunk=False)
    sm.set_seq2(target)
    best_ratio, best = min_ratio, None
    slack = 0.3 * len(target) + 2
    for size in (n, n + 1, n - 1):
        for i in range(len(tokens) - size + 1 if size > 0 else 0):
            cand = text[tokens[i][0]: tokens[i + size - 1][1]]
            folded = fold(cand)
            if abs(len(folded) - len(target)) > slack:
                continue
            sm.set_seq1(folded)
            if sm.real_quick_ratio() <= best_ratio or sm.quick_ratio() <= best_ratio:
                continue
            ratio = sm.ratio()
            if ratio > best_ratio:
                best_ratio, best = ratio, cand
    if best is None:
        return None
    best = re.sub(r"\s+", " ", best).strip("„”\"'«»()[],;: ")
    if not value.rstrip().endswith(".") and best.endswith(".") and not re.search(r"\.\w{1,3}\.$", best):
        best = best[:-1]
    return best or None


def snap_text(value: str, text: str) -> str:
    """Jeśli wartość kończy się w środku słowa występującego w tekście, dociąga ją do końca słowa."""
    words = re.findall(r"\S+", value)
    if not words:
        return value
    pattern = r"\s+".join(re.escape(w) for w in words)
    m = re.search(pattern + r"(\w*)", text, flags=re.IGNORECASE)
    if m and m.group(1):
        return value + m.group(1)
    return value


def digit_candidates(text: str, kind: str) -> list[str]:
    """Ciągi cyfr z tekstu (dopuszczalne spacje i myślniki w środku) o długości właściwej dla pola."""
    out = []
    for m in re.finditer(r"\d(?:[ \-]?\d){6,31}", text):
        d = re.sub(r"\D", "", m.group(0))
        if len(d) in ID_LENGTHS[kind] and d not in out:
            out.append(d)
    return out


def snap_digits(value: str, text: str, kind: str) -> str | None:
    """Znajduje w tekście jedyny numer właściwej długości pasujący do (niepełnej) wartości modelu."""
    v = re.sub(r"\D", "", value or "")
    if len(v) < 5:
        return None
    cands = digit_candidates(text, kind)
    hits = [c for c in cands if v in c or c in v]
    if not hits:
        hits = [c for c in cands if _lcs(v, c) >= max(6, int(0.8 * len(c)))]
    return hits[0] if len(hits) == 1 else None


def bare(word: str) -> str:
    """Wyraz bez wielkości liter i bez znaków diakrytycznych (także obcych, które dopisuje OCR)."""
    word = unicodedata.normalize("NFKD", word.casefold().replace("ł", "l"))
    return "".join(ch for ch in word if not unicodedata.combining(ch))


def majority_spelling(value: str, texts: list[str]) -> str:
    """Zapis wyrazów wartości, który przeważa w odczytach dokumentu.

    OCR potrafi ten sam wyraz odczytać raz z polskim znakiem, raz bez („Łukasz” / „Lukasz”) albo dopisać
    znak, którego nie ma („Zawadżki”). Wyraz występuje w dokumencie zwykle kilka razy (treść, podpis,
    stopka) i w kilku odczytach - wygrywa zapis częstszy. Przy remisie wartość zostaje bez zmian.
    """
    counts: dict[str, dict[str, int]] = {}
    wanted = {bare(w.strip(".,;:")) for w in value.split()}
    for text in texts:
        for token in re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)*", text):
            key = bare(token)
            if key in wanted:
                forms = counts.setdefault(key, {})
                forms[token.casefold()] = forms.get(token.casefold(), 0) + 1
    out = []
    for word in value.split():
        core = word.strip(".,;:")
        forms = counts.get(bare(core), {})
        best = max(forms, key=forms.get, default=None)
        if best and best != core.casefold() and forms[best] > forms.get(core.casefold(), 0):
            shaped = best.upper() if core.isupper() else "-".join(p[:1].upper() + p[1:] for p in best.split("-")) \
                if core[:1].isupper() else best
            word = word.replace(core, shaped)
        out.append(word)
    return " ".join(out)


def restore_known(value: str, known: list[str]) -> str:
    """Zapis z listy znanych wartości, gdy różni się od wartości tylko znakami diakrytycznymi („Lódź” -> „Łódź”)."""
    if value in known:
        return value
    hits = [k for k in known if bare(k) == bare(value)]
    return hits[0] if len(hits) == 1 else value


def digits_in_text(value: str, text: str) -> bool:
    return re.sub(r"\D", "", value) in re.sub(r"[ \-]", "", text)


def _lcs(a: str, b: str) -> int:
    """Długość najdłuższego wspólnego podciągu spójnego."""
    best, prev = 0, [0] * (len(b) + 1)
    for ca in a:
        cur = [0] * (len(b) + 1)
        for j, cb in enumerate(b, 1):
            if ca == cb:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


_OCR_TWINS = str.maketrans({"o": "0", "l": "1", "i": "1", "|": "1"})


def _compact(s: str) -> str:
    """Postać do porównań między odczytami: bez odstępów i separatorów, z ujednoliconymi znakami,
    które OCR myli najczęściej (O/0, l/I/1)."""
    return re.sub(r"[\s\-.,:/]", "", fold(s)).translate(_OCR_TWINS)


def second_read(value: str, primary: str, alt: str) -> str | None:
    """Porównuje wartość z odczytu głównego z innym, niezależnym odczytem OCR.

    "zgodne"    - drugi odczyt zawiera tę samą wartość,
    "rozbiezne" - drugi odczyt zawiera w tym miejscu inną wartość (wariant różniący się kilkoma znakami,
                  którego nie ma w odczycie głównym),
    "brak"      - drugi odczyt w ogóle nie zawiera tej linii (nie potwierdza, ale i nie zaprzecza),
    None        - nie da się ocenić: wartości w tej postaci nie ma w odczycie głównym.
    """
    v, p, a = _compact(value), _compact(primary), _compact(alt)
    n = len(v)
    if n < 3 or v not in p:
        return None
    if v in a:
        return "zgodne"
    limit = max(1, int(0.3 * n))
    for i in range(len(a) - n + 1):
        w = a[i: i + n]
        diff = sum(x != y for x, y in zip(v, w))
        if 0 < diff <= limit and w not in p:
            return "rozbiezne"
    if n >= 6:
        for k in range(n):                      # drugi odczyt zgubił jeden znak
            w = v[:k] + v[k + 1:]
            if w in a and w not in p:
                return "rozbiezne"
    return "brak"


DATE_PATTERNS = (r"\d{4}[-./]\d{1,2}[-./]\d{1,2}(?!\d)", r"\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{4}",
                 r"\d{1,2}\s+[a-ząćęłńóśźż]+\s+\d{4}", r"(?<![\d.,])\d{2} \d{2} \d{4}(?![\d.,])")


def occurrences(value: str, text: str, normalize=None) -> list[tuple[str, str]]:
    """Wystąpienia wartości w tekście jako pary (linia, dosłowny fragment linii).

    Dla dat (`normalize` = funkcja normalizująca datę) trafieniem jest każdy zapis tej samej daty.
    """
    out = []
    for line in text.splitlines():
        low = line.lower()
        if normalize is not None:
            for pattern in DATE_PATTERNS:
                out += [(line, line[m.start(): m.end()]) for m in re.finditer(pattern, low)
                        if normalize(m.group(0)).value == value]
        else:
            start = low.find(value.lower()) if value else -1
            if start >= 0:
                out.append((line, line[start: start + len(value)]))
    return out


def dates_in_text(text: str, normalize) -> set[str]:
    """Wszystkie daty występujące w tekście, znormalizowane funkcją `normalize` (RRRR-MM-DD)."""
    out = set()
    for pattern in DATE_PATTERNS:
        for m in re.finditer(pattern, text.lower()):
            value = normalize(m.group(0)).value
            if value:
                out.add(value)
    return out
