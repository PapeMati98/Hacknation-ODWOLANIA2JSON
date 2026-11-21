"""Końcowa walidacja logiczna modelem: korekta zapisu z bezpiecznikiem i ocena wiarygodności wartości.

Model nigdy nie jest tu autorem wartości:
  - korekta: model proponuje poprawiony zapis (np. „Sp. z 0.o.” -> „Sp. z o.o.”, „Lukasz” -> „Łukasz”),
    a kod przyjmuje propozycję tylko wtedy, gdy różni się od wartości wyłącznie znakami, które OCR myli
    (polskie znaki, cyfra w miejscu litery i odwrotnie); każda inna zmiana jest odrzucana,
  - ocena: pytanie zamknięte „czy »X« to <rodzaj wartości>?”; odpowiedź NIE zeruje pole i kieruje je na
    listę do sprawdzenia, odpowiedź TAK niczego nie zmienia.

Rodzaj wartości pola podaje YAML klasy (`sanity: person | organization | place | title`).
"""
from __future__ import annotations

import unicodedata

KINDS = {
    "person": "imię i nazwisko osoby",
    "organization": "nazwa firmy, kancelarii, urzędu albo innej instytucji",
    "place": "nazwa miejscowości",
    "title": "treść tytułu przelewu (opis, za co jest płatność)",
}
SYSTEM = "Sprawdzasz dane odczytane ze skanów polskich dokumentów urzędowych. Odpowiadasz krótko i dokładnie."

def _chat(user: str) -> str:
    return (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n\n")


def correction_prompt(kind: str, value: str) -> str:
    return _chat(f"Wartość odczytana przez OCR ({KINDS[kind]}): «{value}»\n"
                 "Przepisz ją dokładnie. Popraw wyłącznie oczywiste pomyłki OCR: brakujące polskie znaki "
                 "(ą ć ę ł ń ó ś ź ż) oraz cyfrę w miejscu litery (np. „z 0.o.” to „z o.o.”). Nie zmieniaj słów, "
                 "kolejności, wielkości liter ani skrótów. Jeśli wartość jest poprawna, przepisz ją bez zmian. "
                 "Odpowiedz samą wartością.")


def question_prompt(kind: str, value: str) -> str:
    return _chat(f"Czy «{value}» to {KINDS[kind]}? Odpowiedz jednym słowem: TAK albo NIE.")


def skeleton(text: str) -> str:
    """Postać, w której znikają różnice typowe dla pomyłek OCR: znaki diakrytyczne oraz pary cyfra/litera
    (0/o, 1/l, 5/s) są utożsamiane; wielkość liter zostaje. Długość tekstu się nie zmienia."""
    out = []
    for ch in text:
        base = unicodedata.normalize("NFKD", {"ł": "l", "Ł": "L"}.get(ch, ch))
        base = "".join(c for c in base if not unicodedata.combining(c)) or ch
        out.append({"0": "o", "1": "l", "5": "s"}.get(base[:1], base[:1]))
    return "".join(out)


def accept_correction(value: str, proposal: str) -> bool:
    """Bezpiecznik korekty: propozycja może różnić się od wartości tylko znakami mylonymi przez OCR."""
    return bool(proposal) and proposal != value and len(proposal) == len(value) and skeleton(proposal) == skeleton(value)


# ---------------------------------------------------------------- ocena pola w kontekście dokumentu (weto)
CHECK_RULE = ("Oceniasz jedną wartość wyciągniętą z polskiego dokumentu urzędowego. Odpowiadasz jednym słowem: TAK albo NIE. "
              "Odpowiedz NIE tylko wtedy, gdy fragment jednoznacznie pokazuje, że wartość jest czymś innym: etykietą rubryki, "
              "inną rolą albo innym rodzajem danych. Przy wątpliwości, skrócie albo literówce odpowiedz TAK.")
# Przykłady (wspólny początek każdego pytania - model czyta je raz, potem zostają w pamięci kontekstu).
CHECK_SHOTS = [
    ("Szczegóły płatności\nwpis od odwołania KIO, sygn. ZP.271.5.2026\nKwota: 15 000,00 PLN", "Szczegóły płatności",
     "treść tytułu przelewu (za co jest płatność), a nie etykieta rubryki", "NIE"),
    ("Szczegóły płatności\nwpis od odwołania KIO, sygn. ZP.271.5.2026\nKwota: 15 000,00 PLN",
     "wpis od odwołania KIO, sygn. ZP.271.5.2026", "treść tytułu przelewu (za co jest płatność), a nie etykieta rubryki", "TAK"),
    ("reprezentowany przez pełnomocnika:\nadwokat Jan Kowalski\nKancelaria Adwokacka Kowalski i Wspólnicy sp. k.", "Jan Kowalski",
     "wyłącznie imię i nazwisko osoby (nie firma, kancelaria, funkcja ani etykieta)", "TAK"),
    ("KANCELARIA RADCY PRAWNEGO NOWAK\nBudmax sp. z o.o. z siedzibą w Opolu, KRS 0000123456, niniejszym udziela pełnomocnictwa:\n"
     "1. Anna Nowak - radca prawny", "Kancelaria Radcy Prawnego Nowak",
     "mocodawca, czyli podmiot, który udziela pełnomocnictwa - a nie kancelaria z nagłówka pisma ani pełnomocnik", "NIE"),
    ("KANCELARIA RADCY PRAWNEGO NOWAK\nBudmax sp. z o.o. z siedzibą w Opolu, KRS 0000123456, niniejszym udziela pełnomocnictwa:\n"
     "1. Anna Nowak - radca prawny", "Budmax sp. z o.o.",
     "mocodawca, czyli podmiot, który udziela pełnomocnictwa - a nie kancelaria z nagłówka pisma ani pełnomocnik", "TAK"),
    ("Numer referencyjny: CEN2601015794125\nTytuł: opłata skarbowa od pełnomocnictwa", "CEN2601015794125",
     "krótki numer albo identyfikator transakcji, a nie tytuł przelewu", "TAK"),
]


def _question(context: str, value: str, check: str) -> str:
    return f"Fragment dokumentu:\n{context}\n\nWartość: «{value}»\nCzy ta wartość to {check}?"


def _check_head() -> str:
    out = f"<|im_start|>system\n{CHECK_RULE}<|im_end|>\n"
    for context, value, check, answer in CHECK_SHOTS:
        out += (f"<|im_start|>user\n{_question(context, value, check)}<|im_end|>\n"
                f"<|im_start|>assistant\n<think>\n\n</think>\n\n{answer}<|im_end|>\n")
    return out


def context_lines(text: str, value: str, around: int = 1, limit: int = 3, max_lines: int = 12) -> list[str]:
    """Linie dokumentu, w których stoi wartość (z sąsiednimi) - krótki kontekst do pytania o jedno pole."""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("--- strona")]
    words = [w for w in value.split() if len(w) >= 4] or value.split()
    key = _bare(words[-1])[: max(4, len(words[-1]) - 3)] if words else ""
    hits = [i for i, ln in enumerate(lines) if key and key in _bare(ln)][:limit]
    keep: list[int] = []
    for i in hits:
        keep += [j for j in range(max(0, i - around), min(len(lines), i + around + 1)) if j not in keep]
    return [lines[j][:220] for j in sorted(keep)[:max_lines]]


def _bare(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold().replace("ł", "l"))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def check_prompt(check: str, value: str, context: list[str]) -> str:
    return (_check_head() + f"<|im_start|>user\n{_question(chr(10).join(context), value, check)}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n\n")


def says_no(answer: str) -> bool:
    return answer.strip().strip(".«»\"").upper().startswith("NIE")


def review(backend, text: str, spec, data, trace: list[dict], veto: bool = False) -> int:
    """Końcowa ocena modelem pól, które mają w YAML opcję `check` (opis tego, czym wartość ma być).

    Model nigdy nie zmienia wartości. Odpowiedź NIE kieruje pole na listę do sprawdzenia: w trybie
    `veto` pole jest dodatkowo zerowane, bez niego wartość zostaje (z ostrzeżeniem).
    Zwraca liczbę zadanych pytań.
    """
    from .crosscheck import walk
    by_path = {t["pole"]: t for t in trace}
    asked = 0
    for path, parent, key, leaf in list(walk(spec, data)):
        value = parent.get(key)
        if value is None or not leaf.get("check"):
            continue
        asked += 1
        answer = backend.say(check_prompt(leaf["check"], str(value), context_lines(text, str(value))), 3)
        entry = by_path.get(path)
        if says_no(answer):
            note = f"ocena modelu: {value!r} to nie {leaf['check']}"
            if veto:
                parent[key] = None
            if entry is None:
                entry = {"pole": path, "surowa": value, "zrodlo": "ocena modelu"}
                trace.append(entry)
            entry.update(wartosc=None if veto else value, status="niezweryfikowane" if veto else "ostrzezenie",
                         uwaga=note, ocena_modelu="NIE")
        elif entry is not None:
            entry["ocena_modelu"] = "TAK"
    return asked
