"""Klasyfikacja i ekstrakcja: mały LLM (llama.cpp, CPU) z gramatyką JSON + walidatory.

Każda wartość zwrócona przez model przechodzi:
  1. walidator pola (validators.VALIDATORS) - sumy kontrolne, formaty, daty,
  2. weryfikację obecności w tekście (verify_in_text) - wartość, której nie ma w dokumencie,
     jest odrzucana (anty-halucynacja),
a wynik każdego pola trafia do śladu (trace) z informacją o źródle i statusie.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field

from .config import DocClass, is_leaf
from .pdfio import UNREADABLE, Document
from .validators import VALIDATORS

SYSTEM_PROMPT = (
    "Jesteś precyzyjnym ekstraktorem danych z polskich dokumentów urzędowych (zamówienia publiczne, KIO). "
    "Zwróć wyłącznie JSON zgodny ze schematem. Wartości przepisuj dokładnie tak, jak są w tekście. "
    "Jeśli informacji nie ma w tekście, jest zakryta (anonimizacja) albo oznaczona jako [NIECZYTELNE], wpisz null. "
    "Nigdy nie zgaduj i nie wymyślaj numerów, nazw ani dat."
)


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
    def __init__(self, model_path: str, n_threads: int, n_ctx: int = 8192):
        from llama_cpp import Llama
        self.llm = Llama(model_path=model_path, n_ctx=n_ctx, n_threads=n_threads, verbose=False)
        self._grammars: dict[str, object] = {}

    def _grammar(self, cls: DocClass):
        if cls.name not in self._grammars:
            from llama_cpp import LlamaGrammar
            self._grammars[cls.name] = LlamaGrammar.from_json_schema(json.dumps(cls.json_schema()), verbose=False)
        return self._grammars[cls.name]

    def run(self, doc: Document, cls: DocClass) -> tuple[dict, list[dict]]:
        text = doc.text(max_pages=cls.pages)
        user = (f"Typ dokumentu: {cls.description}\n\nPola do wypełnienia:\n{cls.field_guide()}\n\n"
                f"TEKST DOKUMENTU:\n{text}")
        out = self.llm.create_chat_completion(
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
            grammar=self._grammar(cls), temperature=0.0, max_tokens=1200)
        raw = json.loads(out["choices"][0]["message"]["content"])
        trace: list[dict] = []
        data = postprocess(cls, cls.output, raw, doc, trace, "")
        apply_derived(cls, cls.output, data, data, "")
        return data, trace


# ---------------------------------------------------------------- walidacja wyników
def postprocess(cls: DocClass, spec, value, doc: Document, trace: list[dict], path: str):
    if isinstance(spec, list):
        items = value if isinstance(value, list) else []
        out = [postprocess(cls, spec[0], v, doc, trace, f"{path}[{i}]") for i, v in enumerate(items)]
        return out or [postprocess(cls, spec[0], {}, doc, trace, f"{path}[0]")]
    if is_leaf(spec):
        if "derive" in spec:
            return None
        return check_leaf(spec, value, doc, trace, path)
    value = value if isinstance(value, dict) else {}
    return {k: postprocess(cls, v, value.get(k), doc, trace, f"{path}.{k}" if path else k) for k, v in spec.items()}


def check_leaf(spec: dict, value, doc: Document, trace: list[dict], path: str):
    from_ocr = doc.is_scan
    entry = {"pole": path, "surowa": value, "zrodlo": "ocr" if from_ocr else "warstwa_tekstowa"}
    if value is None or (isinstance(value, str) and (not value.strip() or UNREADABLE in value)):
        entry.update(wartosc=None, status="brak")
        trace.append(entry)
        return None
    if "enum" in spec or "enum_from" in spec:
        entry.update(wartosc=value, status="ok")
        trace.append(entry)
        return value
    check = VALIDATORS[spec.get("validator", "text")](value, from_ocr)
    result, status, note = check.value, check.status, check.note
    if result is not None and spec.get("verify_in_text") and not appears_in(str(result), doc.text(max_pages=None)):
        result, status, note = None, "niezweryfikowane", "wartości nie ma w tekście dokumentu"
    if result is not None and spec.get("output_type") == "integer":
        result = int(result)
    entry.update(wartosc=result, status=status, uwaga=note)
    trace.append(entry)
    return result


def apply_derived(cls: DocClass, spec, node, root, path):
    if isinstance(spec, list):
        for item in node or []:
            apply_derived(cls, spec[0], item, root, path)
        return
    if not isinstance(spec, dict) or is_leaf(spec):
        return
    for k, v in spec.items():
        if is_leaf(v) and "derive" in v:
            d = v["derive"]
            key_val = get_path(root, d["key"])
            node[k] = cls.dictionaries[d["dictionary"]].get(key_val) if key_val is not None else None
        elif isinstance(node, dict):
            apply_derived(cls, v, node.get(k), root, f"{path}.{k}")


def get_path(obj, dotted: str):
    for part in dotted.split("."):
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj


# ---------------------------------------------------------------- weryfikacja w tekście
def fold(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"[„”“\"'«»]", "", s)
    return re.sub(r"\s+", " ", s)


def appears_in(value: str, text: str) -> bool:
    v, t = fold(value), fold(text)
    if v in t:
        return True
    t_flat = re.sub(r"\s", "", t)
    if re.sub(r"\s", "", v) in t_flat:
        return True
    words = [w for w in re.findall(r"\w+", v) if len(w) >= 3]
    return bool(words) and sum(w in t for w in words) / len(words) >= 0.85
