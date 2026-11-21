"""Klasyfikacja i ekstrakcja pól.

Model językowy wypełnia zwięzły formularz (sekcje `## Nazwa`, linie `klucz: wartość`).
Kod zamienia formularz na JSON, a każdą wartość sprawdza:
  1. walidatorem pola (sumy kontrolne, formaty, daty, kwoty),
  2. w tekście dokumentu - wartość, której w dokumencie nie ma, jest odrzucana,
  3. regułami klasy (np. pole wypełniane tylko przy kilku podmiotach).
Zasada: lepiej zwrócić null i oznaczyć pole jako nieodczytane, niż wpisać błędną wartość.
Wynik każdego pola trafia do śladu (trace) ze źródłem i statusem.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import DocClass, Section, is_leaf
from .pdfio import UNREADABLE, Document
from .textmatch import ID_LENGTHS, appears_in, digits_in_text, fold, snap_digits, snap_text
from .validators import VALIDATORS

SYSTEM_PROMPT = (
    "Jesteś precyzyjnym ekstraktorem danych z polskich dokumentów urzędowych (zamówienia publiczne, KIO). "
    "Wypełniasz formularz wyłącznie na podstawie podanego tekstu. Wartości przepisujesz dosłownie. "
    "Jeśli informacji nie ma, jest zakryta (anonimizacja) albo oznaczona jako [NIECZYTELNE], wpisujesz '-'. "
    "Nigdy nie zgadujesz i nie wymyślasz numerów, nazw ani dat."
)
RULES = (
    "Zasady wypełniania:\n"
    "- każda linia ma postać `klucz: wartość`, bez komentarzy i bez dodatkowego tekstu,\n"
    "- wartości przepisuj dosłownie z tekstu; daty i kwoty zapisz tak, jak występują w dokumencie,\n"
    "- gdy informacji nie ma, jest zakryta albo nieczytelna, wpisz `-`,\n"
    "- sekcję oznaczoną (xN) powtórz z kolejnym numerem dla każdego podmiotu z dokumentu "
    "(np. `## Nazwa 2`); jeśli podmiot jest jeden, wypełnij tylko `## Nazwa 1`."
)
EMPTY = {"", "-", "–", "—", "null", "none", "brak", "n/d", "nie dotyczy", "brak danych"}


@dataclass
class Result:
    doc_class: str | None
    scores: dict[str, float]
    data: dict | None = None
    trace: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------- klasyfikacja
def classify(doc: Document, classes: list[DocClass]) -> tuple[str | None, dict[str, float]]:
    text = fold(doc.text(max_pages=2))
    flat = re.sub(r"\s", "", text)
    head = re.sub(r"\s", "", fold(doc.pages[0].text if doc.pages else ""))[:250]

    def has(k: str) -> bool:
        k = fold(k)
        return k in text or re.sub(r"\s", "", k) in flat

    scores = {}
    for c in classes:
        s = sum(w for k, w in c.keywords.items() if has(k))
        s -= sum(w for k, w in c.negative.items() if has(k))
        s += sum(c.title_weight for k in c.title if re.sub(r"\s", "", fold(k)) in head)
        scores[c.name] = s
    best = max(scores, key=scores.get)
    by_name = {c.name: c for c in classes}
    if scores[best] < by_name[best].min_score:
        return None, scores
    return best, scores


# ---------------------------------------------------------------- ekstrakcja
class Extractor:
    def __init__(self, backend):
        self.backend = backend

    def build_prompt(self, doc: Document, cls: DocClass) -> str:
        # Część stała dla klasy jest na początku (cache prefiksu w llama.cpp), tekst dokumentu na końcu.
        return (f"Typ dokumentu: {cls.description}\n\n{RULES}\n\nOpis pól:\n{cls.field_guide()}\n\n"
                f"Formularz do wypełnienia:\n{cls.template()}\n\nTEKST DOKUMENTU:\n{doc.text(max_pages=cls.pages)}")

    def run(self, doc: Document, cls: DocClass) -> tuple[dict, list[dict], str]:
        answer = self.backend.complete(SYSTEM_PROMPT, self.build_prompt(doc, cls), cls.first_header() + "\n", 600)
        raw = parse_sheet(answer, cls)
        trace: list[dict] = []
        data = postprocess(cls.output, raw, doc, trace, "")
        apply_derived(cls, cls.output, data, data)
        return data, trace, answer


# ---------------------------------------------------------------- formularz -> surowa struktura
def parse_sheet(answer: str, cls: DocClass) -> dict:
    sections = {s.name.casefold(): s for s in cls.sections()}
    raw: dict = {}
    current: Section | None = None
    target: dict | None = None
    for line in answer.splitlines():
        line = line.strip().strip("`")
        head = re.match(r"^#+\s*([\w\-]+)(?:\s+(\d+))?", line)
        if head:
            current = sections.get(head.group(1).casefold())
            if current is None:
                target = None
            elif current.is_list:
                target = {}
                raw.setdefault(current.name, []).append(target)
            else:
                target = raw if current.name == "_" else raw.setdefault(current.name, {})
            continue
        kv = re.match(r"^[-*]?\s*([\w.\-]+)\s*:\s*(.*)$", line)
        if not kv or current is None or target is None:
            continue
        spec = next((f for f in current.fields if f.key.casefold() == kv.group(1).casefold()), None)
        if spec is None:
            continue
        value = kv.group(2).strip()
        if value.casefold() in EMPTY:
            value = None
        if spec.multi_inner:
            parts = [p.strip() for p in re.split(r"\s*[|;]\s*", value or "") if p.strip()]
            value = [{spec.multi_inner: p} for p in parts]
        _set_path(target, spec.key, value)
    # elementy list bez żadnej wartości (model powielił pustą sekcję) są pomijane
    for s in cls.sections():
        if s.is_list and s.name in raw:
            raw[s.name] = [item for item in raw[s.name] if _has_value(item)] or raw[s.name][:1]
    return raw


def _set_path(target: dict, dotted: str, value):
    parts = dotted.split(".")
    for p in parts[:-1]:
        target = target.setdefault(p, {})
    target[parts[-1]] = value


def _has_value(node) -> bool:
    if isinstance(node, dict):
        return any(_has_value(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_value(v) for v in node)
    return node is not None


# ---------------------------------------------------------------- walidacja wyników
def postprocess(spec, value, doc: Document, trace: list[dict], path: str):
    if isinstance(spec, list):
        items = value if isinstance(value, list) else []
        out = [postprocess(spec[0], v, doc, trace, f"{path}[{i}]") for i, v in enumerate(items)]
        out = out or [postprocess(spec[0], {}, doc, trace, f"{path}[0]")]
        if len(out) == 1 and isinstance(out[0], dict):
            for k, v in spec[0].items():   # pola mające sens tylko przy kilku elementach listy
                if is_leaf(v) and v.get("only_if_multiple"):
                    out[0][k] = None
        return out
    if is_leaf(spec):
        if "derive" in spec:
            return None
        return check_leaf(spec, value, doc, trace, path)
    value = value if isinstance(value, dict) else {}
    return {k: postprocess(v, value.get(k), doc, trace, f"{path}.{k}" if path else k) for k, v in spec.items()}


def check_leaf(spec: dict, value, doc: Document, trace: list[dict], path: str):
    from_ocr = doc.is_scan
    entry = {"pole": path, "surowa": value, "zrodlo": "ocr" if from_ocr else "warstwa_tekstowa"}

    def done(result, status, note=""):
        entry.update(wartosc=result, status=status, uwaga=note)
        trace.append(entry)
        return result

    if value is None or (isinstance(value, str) and (value.strip().casefold() in EMPTY or UNREADABLE in value)):
        return done(None, "brak")
    value = str(value).strip().strip('"„”')
    text = doc.text(max_pages=None)

    if "enum" in spec or "enum_from" in spec:
        allowed = spec.get("enum")
        m = re.search(r"-?\d+", value)
        if spec.get("type") == "integer" or "enum_from" in spec:
            if not m:
                return done(None, "nieczytelne", f"oczekiwano liczby: {value!r}")
            num = int(m.group(0))
            return done(num, "ok") if allowed is None or num in allowed else done(None, "nieczytelne", "poza słownikiem")
        return done(value, "ok") if value in allowed else done(None, "nieczytelne", "poza słownikiem")

    kind = spec.get("validator", "text")
    check = VALIDATORS[kind](value, from_ocr)
    result, status, note = check.value, check.status, check.note

    if kind in ID_LENGTHS:
        wrong_len = result is None or len(str(result)) not in ID_LENGTHS[kind]
        if status in ("nieczytelne", "ostrzezenie") and wrong_len or \
                (result is not None and status != "naprawiono" and not digits_in_text(str(result), text)):
            fixed = snap_digits(value, text, kind)
            if fixed:
                recheck = VALIDATORS[kind](fixed, from_ocr)
                if recheck.value is not None:
                    result, status, note = recheck.value, "dopasowano", f"{value!r} -> numer z tekstu"
            elif result is not None and not digits_in_text(str(result), text):
                result, status, note = None, "niezweryfikowane", "numeru nie ma w tekście dokumentu"
            elif wrong_len:
                result, status, note = None, "nieczytelne", note or "zła długość numeru"
    elif spec.get("verify_in_text") and result is not None:
        snapped = snap_text(str(result), text)
        if snapped != result:
            result, status, note = snapped, "dopasowano", "uzupełniono ucięte słowo z tekstu"
        if not appears_in(str(result), text):
            result, status, note = None, "niezweryfikowane", "wartości nie ma w tekście dokumentu"

    if result is not None and spec.get("output_type") == "integer":
        result = int(result)
    return done(result, status, note)


def apply_derived(cls: DocClass, spec, node, root):
    if isinstance(spec, list):
        for item in node or []:
            apply_derived(cls, spec[0], item, root)
        return
    if not isinstance(spec, dict) or is_leaf(spec) or not isinstance(node, dict):
        return
    for k, v in spec.items():
        if is_leaf(v) and "derive" in v:
            key_val = _get_path(root, v["derive"]["key"])
            node[k] = cls.dictionaries[v["derive"]["dictionary"]].get(key_val) if key_val is not None else None
        else:
            apply_derived(cls, v, node.get(k), root)


def _get_path(obj, dotted: str):
    for part in dotted.split("."):
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj
