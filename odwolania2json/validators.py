"""Walidatory i normalizatory pól.

Zasada projektu (Mateusz, 2026-11-21): gorsze jest spisanie bzdur niż oznaczenie jako
nieodczytane. Wartość pochodząca z OCR, która nie przechodzi walidacji i której nie da się
jednoznacznie naprawić o jeden znak, jest zwracana jako None ze statusem "nieczytelne".
Wartość z warstwy tekstowej PDF (odczyt dokładny) nie jest zerowana - walidator tylko ją
oznacza, bo gold organizatora zawiera fikcyjne numery ze złą sumą kontrolną.

Każdy walidator zwraca Check(value, status, note):
  status: "ok" | "naprawiono" | "nieczytelne" | "ostrzezenie" | "brak"
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Typowe pomyłki OCR: znak odczytany -> możliwe znaki prawdziwe (dla pól cyfrowych).
OCR_DIGIT_MAP = {
    "O": "0", "o": "0", "D": "0", "Q": "0", "U": "0",
    "I": "1", "l": "1", "i": "1", "|": "1", "!": "1", "L": "1",
    "Z": "2", "z": "2",
    "S": "5", "s": "5",
    "G": "6", "b": "6",
    "T": "7",
    "B": "8",
    "g": "9", "q": "9",
}
# Podmiany cyfra<->cyfra najczęstsze w PP-OCR (do naprawy o jeden znak przy złej sumie).
DIGIT_CONFUSIONS = {
    "0": "86", "1": "7", "2": "7", "3": "8", "4": "1", "5": "6", "6": "58", "7": "12", "8": "306", "9": "8",
}

MONTHS = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6, "lipca": 7,
    "sierpnia": 8, "września": 9, "wrzesnia": 9, "października": 10, "pazdziernika": 10,
    "listopada": 11, "grudnia": 12,
}


@dataclass
class Check:
    value: object
    status: str
    note: str = ""


# ---------------------------------------------------------------- sumy kontrolne
def nip_ok(d: str) -> bool:
    w = (6, 5, 7, 2, 3, 4, 5, 6, 7)
    return len(d) == 10 and d.isdigit() and sum(int(a) * b for a, b in zip(d, w)) % 11 == int(d[9])


def regon_ok(d: str) -> bool:
    if not d.isdigit():
        return False
    if len(d) == 9:
        w = (8, 9, 2, 3, 4, 5, 6, 7)
    elif len(d) == 14:
        w = (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8)
    else:
        return False
    return sum(int(a) * b for a, b in zip(d, w)) % 11 % 10 == int(d[-1])


def pesel_ok(d: str) -> bool:
    w = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    return len(d) == 11 and d.isdigit() and (10 - sum(int(a) * b for a, b in zip(d, w)) % 10) % 10 == int(d[10])


def nrb_ok(d: str) -> bool:
    return len(d) == 26 and d.isdigit() and int(d[2:] + "2521" + d[:2]) % 97 == 1


def krs_ok(d: str) -> bool:
    return len(d) == 10 and d.isdigit()


CHECKSUMS = {"nip": (nip_ok, 10), "regon": (regon_ok, None), "pesel": (pesel_ok, 11), "nrb": (nrb_ok, 26), "krs": (krs_ok, 10)}


def digits_from_ocr(raw: str) -> str:
    """Zamienia litery mylone z cyframi i usuwa separatory (spacje, myślniki, kropki)."""
    raw = re.sub(r"(?i)^(PL)(?=\s*\d)", "", raw.strip())
    return "".join(OCR_DIGIT_MAP.get(c, c) for c in raw if c not in " -. /")


def repair_one(d: str, ok) -> list[str]:
    """Wszystkie warianty różniące się jednym znakiem (wg tabeli pomyłek), które przechodzą sumę."""
    out = []
    for i, c in enumerate(d):
        for alt in DIGIT_CONFUSIONS.get(c, ""):
            cand = d[:i] + alt + d[i + 1:]
            if ok(cand):
                out.append(cand)
    return out


def check_number(kind: str, raw, from_ocr: bool) -> Check:
    """Walidacja identyfikatora: nip | regon | pesel | nrb | krs."""
    if raw in (None, ""):
        return Check(None, "brak")
    ok, length = CHECKSUMS[kind]
    d = digits_from_ocr(str(raw)) if from_ocr else re.sub(r"[\s\-.]", "", str(raw))
    if kind == "nrb":
        d = re.sub(r"(?i)^PL", "", d)
    if not d.isdigit():
        return Check(None, "nieczytelne", f"{kind}: znaki inne niż cyfry ({raw!r})") if from_ocr \
            else Check(d, "ostrzezenie", f"{kind}: znaki inne niż cyfry")
    if length and len(d) != length:
        return Check(None, "nieczytelne", f"{kind}: długość {len(d)} ≠ {length}") if from_ocr \
            else Check(d, "ostrzezenie", f"{kind}: długość {len(d)}")
    if ok(d):
        return Check(d, "ok")
    if not from_ocr:
        return Check(d, "ostrzezenie", f"{kind}: zła suma kontrolna (odczyt dokładny, zachowano)")
    fixes = repair_one(d, ok)
    if len(fixes) == 1:
        return Check(fixes[0], "naprawiono", f"{kind}: {d} -> {fixes[0]}")
    return Check(None, "nieczytelne", f"{kind}: zła suma, poprawek: {len(fixes)}")


# ---------------------------------------------------------------- formaty
def norm_date(raw) -> Check:
    """'16 czerwca 2025 r.', '16.06.2025', '2025-06-16' -> '2025-06-16'."""
    if raw in (None, ""):
        return Check(None, "brak")
    s = str(raw).strip().lower()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})", s)
        if m:
            d, mo, y = map(int, m.groups())
        else:
            m = re.search(r"(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})", s)
            if not m or m.group(2) not in MONTHS:
                return Check(None, "nieczytelne", f"data: {raw!r}")
            d, mo, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
    try:
        iso = date(y, mo, d).isoformat()
    except ValueError:
        return Check(None, "nieczytelne", f"data niemożliwa: {raw!r}")
    if not 2000 <= y <= 2035:
        return Check(None, "nieczytelne", f"rok poza zakresem: {raw!r}")
    return Check(iso, "ok")


def norm_bzp(raw) -> Check:
    if raw in (None, ""):
        return Check(None, "brak")
    s = re.sub(r"\s+", "", str(raw)).upper()
    m = re.search(r"(20\d{2})/BZP(\d{8})(/\d{2})?", s)
    if not m:
        return Check(None, "nieczytelne", f"BZP: {raw!r}")
    return Check(f"{m.group(1)}/BZP{m.group(2)}{m.group(3) or ''}", "ok")


def norm_ted(raw) -> Check:
    """'363730-2025' lub '2025/S 123-363730' -> '363730-2025'."""
    if raw in (None, ""):
        return Check(None, "brak")
    s = re.sub(r"\s+", " ", str(raw)).strip()
    m = re.search(r"(\d{4,8})\s*-\s*(20\d{2})", s)
    if m and not re.search(r"20\d{2}\s*/\s*S", s):
        return Check(f"{m.group(1)}-{m.group(2)}", "ok")
    m = re.search(r"(20\d{2})\s*/\s*S\s*\d{1,3}\s*-\s*(\d{4,8})", s)
    if m:
        return Check(f"{m.group(2)}-{m.group(1)}", "ok")
    return Check(None, "nieczytelne", f"TED: {raw!r}")


def norm_amount(raw) -> Check:
    if raw in (None, ""):
        return Check(None, "brak")
    if isinstance(raw, (int, float)):
        return Check(float(raw), "ok")
    s = str(raw).replace(" ", " ").upper().replace("PLN", "").replace("ZŁ", "").strip()
    s = re.sub(r"(?<=\d)[ .](?=\d{3}\b)", "", s).replace(",", ".")
    m = re.search(r"\d+(\.\d{1,2})?", s)
    if not m:
        return Check(None, "nieczytelne", f"kwota: {raw!r}")
    return Check(float(m.group(0)), "ok")


def norm_email(raw) -> Check:
    if raw in (None, ""):
        return Check(None, "brak")
    s = str(raw).strip().replace(" ", "")
    if re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", s):
        return Check(s.lower(), "ok")
    return Check(None, "nieczytelne", f"e-mail: {raw!r}")


def norm_text(raw) -> Check:
    if raw in (None, ""):
        return Check(None, "brak")
    s = re.sub(r"\s+", " ", str(raw)).strip().strip(",;")
    return Check(s or None, "ok" if s else "brak")


_TITLE = (r"(?:adw(?:okat\w*)?|r\.\s?pr|radc\w+\s+prawn\w+|mec(?:enas\w*)?|dr|mgr|inż|prof|hab|lic|"
          r"pan(?:i|a|u|ią)?|p\.)\.?")


def norm_person(raw) -> Check:
    """Imię i nazwisko bez tytułów zawodowych i naukowych (adw., r. pr., mec., dr ...)."""
    if raw in (None, ""):
        return Check(None, "brak")
    s = re.sub(r"\s+", " ", str(raw)).strip()
    s = re.split(r"\s*[,;(]\s*|\s+[-–—]\s+", s)[0]        # "Jan Kowalski, radca prawny" -> "Jan Kowalski"
    prev = None
    while prev != s:
        prev = s
        s = re.sub(rf"^{_TITLE}\s+", "", s, flags=re.IGNORECASE)
    s = s.strip(" .,;:")
    return Check(s or None, "ok" if s else "brak")


# Nazwa walidatora w YAML -> funkcja(raw, from_ocr) -> Check
VALIDATORS = {
    "nip": lambda v, o: check_number("nip", v, o),
    "regon": lambda v, o: check_number("regon", v, o),
    "pesel": lambda v, o: check_number("pesel", v, o),
    "nrb": lambda v, o: check_number("nrb", v, o),
    "krs": lambda v, o: check_number("krs", v, o),
    "date": lambda v, o: norm_date(v),
    "bzp": lambda v, o: norm_bzp(v),
    "ted": lambda v, o: norm_ted(v),
    "amount": lambda v, o: norm_amount(v),
    "email": lambda v, o: norm_email(v),
    "text": lambda v, o: norm_text(v),
    "person": lambda v, o: norm_person(v),
}
