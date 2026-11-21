"""Dopasowanie wartości zwróconych przez model do faktycznego tekstu dokumentu.

Model bywa nieprecyzyjny w przepisywaniu (ucięte słowo, zgubione cyfry). Zamiast ufać
modelowi, sprawdzamy wartość w tekście i w razie potrzeby dociągamy ją do tego, co
naprawdę jest w dokumencie. Wartość, której nie da się znaleźć, jest odrzucana.
"""
from __future__ import annotations

import re
import unicodedata

ID_LENGTHS = {"nip": (10,), "regon": (9, 14), "pesel": (11,), "nrb": (26,), "krs": (10,)}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"[„”“\"'«»]", "", s)
    return re.sub(r"\s+", " ", s)


def appears_in(value: str, text: str) -> bool:
    v, t = fold(value), fold(text)
    if v in t:
        return True
    if re.sub(r"\s", "", v) in re.sub(r"\s", "", t):
        return True
    words = [w for w in re.findall(r"\w+", v) if len(w) >= 3]
    return bool(words) and sum(w in t for w in words) / len(words) >= 0.85


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
