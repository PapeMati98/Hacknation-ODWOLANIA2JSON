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

import os
import re
from dataclasses import dataclass, field

from .config import DocClass, Section, is_leaf
from .crosscheck import apply_field_rules, resolve_duplicates
from .pdfio import ALT_DPIS, REDACTED, UNREADABLE, Document
from .textmatch import (ID_LENGTHS, _compact, appears_in, dates_in_text, digits_in_text, fold, occurrences, person_in,
                        second_read,
                        snap_digits, snap_span, snap_text, words_in)
from .validators import VALIDATORS, digits_from_ocr, norm_date

SYSTEM_PROMPT = (
    "Jesteś precyzyjnym ekstraktorem danych z polskich dokumentów urzędowych (zamówienia publiczne, KIO). "
    "Wypełniasz formularz wyłącznie na podstawie podanego tekstu. Wartości przepisujesz dosłownie. "
    "Jeśli informacji nie ma, jest zakryta (w tekście znacznik [ZAKRYTE] - anonimizacja czarnym prostokątem) "
    "albo oznaczona jako [NIECZYTELNE], wpisujesz '-'. Nie składasz wartości z fragmentów stojących obok [ZAKRYTE]. "
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

    def static_prompt(self, cls: DocClass) -> str:
        # Część stała dla klasy: jej stan w modelu jest zapamiętywany i używany dla kolejnych dokumentów.
        return (f"Typ dokumentu: {cls.description}\n\n{RULES}\n\nOpis pól:\n{cls.field_guide()}\n\n"
                f"Formularz do wypełnienia:\n{cls.template()}\n\nTEKST DOKUMENTU:\n")

    def build_prompt(self, doc: Document, cls: DocClass) -> str:
        return self.static_prompt(cls) + doc.text(max_pages=cls.pages)

    def run(self, doc: Document, cls: DocClass) -> tuple[dict, list[dict], str]:
        if hasattr(self.backend, "fill"):       # model lokalny: prowadzone wypełnianie formularza
            sections = [(s.name, s.is_list, [f.key for f in s.fields]) for s in cls.sections()]
            answer = self.backend.fill(SYSTEM_PROMPT, self.static_prompt(cls), doc.text(max_pages=cls.pages), sections)
        else:
            answer = self.backend.complete(SYSTEM_PROMPT, self.build_prompt(doc, cls), cls.first_header() + "\n", 600)
        data, trace = self.finish(doc, cls, answer)
        return data, trace, answer

    @staticmethod
    def finish(doc: Document, cls: DocClass, answer: str) -> tuple[dict, list[dict]]:
        """Formularz wypełniony przez model -> zweryfikowany JSON i ślad (bez udziału modelu)."""
        raw = parse_sheet(answer, cls)
        trace: list[dict] = []
        data = postprocess(cls.output, raw, doc, trace, "")
        resolve_duplicates(cls, data, trace, doc.text(max_pages=None))
        apply_field_rules(cls, data, trace)
        apply_derived(cls, cls.output, data, data)
        return data, trace


# ---------------------------------------------------------------- formularz -> surowa struktura
def parse_sheet(answer: str, cls: DocClass) -> dict:
    sections = {s.name.casefold(): s for s in cls.sections()}
    raw: dict = {}
    current: Section | None = None
    target: dict | None = None
    seen: set[str] = set()
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
            seen = set()
            continue
        kv = re.match(r"^[-*]?\s*([\w.\-]+)\s*:\s*(.*)$", line)
        if not kv or current is None or target is None:
            continue
        spec = next((f for f in current.fields if f.key.casefold() == kv.group(1).casefold()), None)
        if spec is None:
            continue
        if spec.key in seen and current.is_list:    # powtórzony klucz bez nagłówka = kolejny element listy
            target, seen = {}, set()
            raw[current.name].append(target)
        seen.add(spec.key)
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

    def done(result, status, note="", confidence=None):
        entry.update(wartosc=result, status=status, uwaga=note)
        if confidence:
            entry["pewnosc"] = confidence
        trace.append(entry)
        return result

    if value is None or (isinstance(value, str) and (value.strip().casefold() in EMPTY or UNREADABLE in value)):
        return done(None, "brak")
    if REDACTED in str(value):
        return done(None, "brak", "pole zakryte (anonimizacja)")
    value = str(value).strip().strip('"„”')
    text = doc.text(max_pages=None)

    if "enum" in spec or "enum_from" in spec:
        allowed = spec.get("enum")
        m = re.search(r"-?\d+", value)
        if spec.get("type") == "integer" or "enum_from" in spec:
            decided = decide_from_text(spec["decide"], text) if spec.get("decide") else None
            if decided is not None and (not m or int(m.group(0)) != decided[0]):
                return done(decided[0], "dopasowano", f"{value!r} -> pozycja słownika wskazana wprost w zdaniu: {decided[1]!r}")
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
        result, status, note = verify_text(str(result), text, kind, status, note)
    elif result is not None and not value_in_text(kind, value, result, text):
        # Data, kwota, numer ogłoszenia, e-mail: model nie może podać wartości, której w dokumencie nie ma.
        result, status, note = None, "niezweryfikowane", "wartości nie ma w tekście dokumentu"

    if result is not None and spec.get("line_pattern") and not line_context_ok(spec["line_pattern"], kind, result, text):
        result, status, note = None, "niezweryfikowane", "wartość stoi w dokumencie w innym miejscu niż wymagane dla pola"

    confidence = None
    if from_ocr:
        result, status, note, confidence = cross_check_ocr(doc, kind, value, text, result, status, note)

    if result is not None and spec.get("output_type") == "integer":
        result = int(result)
    return done(result, status, note, confidence)


CHECKSUM_KINDS = {"nip", "regon", "pesel", "nrb"}
HIGH_LINE_CONF = 0.95      # pewność linii OCR, od której odczyt uznajemy za wysoki (poprawne numery na skanach: 0,945-0,99)
# Numer ze skanu ze złą sumą kontrolną, którego nie da się naprawić (decyzja właściciela 2026-11-21):
#   confidence (domyślnie) - zależy od wskaźnika pewności odczytu: wysoka -> zostaje z ostrzeżeniem, inaczej null,
#   strict                 - zawsze null i pozycja do sprawdzenia.
CHECKSUM_POLICY = os.environ.get("O2J_OCR_CHECKSUM", "confidence")
VISUAL_READER = None       # vision.VisualReader - drugi czytelnik wycinków linii; ustawia cli (--visual-reader on)


def best_line(doc: Document, probe: str):
    """Linia odczytu głównego zawierająca wartość (ta o najwyższej pewności)."""
    key = _compact(probe)
    lines = [l for p in doc.pages for l in p.lines if key and key in _compact(l.text)]
    return max(lines, key=lambda l: l.conf) if lines else None


def visual_check(doc: Document, kind: str, probe: str, conf: dict) -> tuple[dict, str | None]:
    """Pyta czytelnika wizualnego o wartość o nie-wysokiej pewności. Zwraca (wskaźnik, powód wyzerowania | None).

    Odczyt zgodny podnosi pewność o jeden stopień, inna wartość w odczycie albo czarny prostokąt w wycinku
    zerują pole, odczyt pusty lub niezwiązany z linią niczego nie zmienia.
    """
    from .vision import adjust
    verdict, detail = VISUAL_READER.check(doc, best_line(doc, probe), kind, probe)
    conf = dict(conf, czytelnik_wizualny=verdict)
    if verdict == "zakryte":
        return conf, f"linia z czarnym prostokątem ({detail})"
    if verdict == "inne":
        return conf, f"inna wartość w odczycie wizualnym ({detail})"
    if verdict == "zgodne":
        conf["poziom"] = adjust(conf["poziom"], verdict)
    return conf, None


def line_conf(doc: Document, probe: str) -> float | None:
    """Pewność OCR linii zawierającej wartość (najlepsza, gdy wartość występuje kilka razy)."""
    key = _compact(probe)
    confs = [l.conf for p in doc.pages for l in p.lines if key and key in _compact(l.text)]
    return max(confs) if confs else None


def ocr_confidence(doc: Document, probe: str, text: str) -> dict:
    """Wskaźnik pewności wartości odczytanej ze skanu.

    Składniki: pewność linii podawana przez OCR oraz werdykt innych, niezależnych odczytów strony.
      wysoka      - linia pewna (>= HIGH_LINE_CONF) i inny odczyt daje tę samą wartość,
      srednia     - brak sprzeczności, ale linia mniej pewna albo inny odczyt jej nie zawiera,
      niska       - inny odczyt daje w tym miejscu inną wartość,
      nieokreslona - wartości w tej postaci nie ma w odczycie głównym (nie da się porównać).
    """
    verdict, conf = ocr_confirms(doc, probe, text), line_conf(doc, probe)
    if verdict is None:
        level = "nieokreslona"
    elif verdict == "rozbiezne":
        level = "niska"
    elif verdict == "zgodne" and conf is not None and conf >= HIGH_LINE_CONF:
        level = "wysoka"
    else:
        level = "srednia"
    return {"poziom": level, "pewnosc_linii": None if conf is None else round(conf, 3),
            "inny_odczyt": {"zgodne": "zgodny", "rozbiezne": "inna wartość", "brak": "linia nieodczytana", None: None}[verdict]}


def _describe(c: dict) -> str:
    visual = f", czytelnik wizualny: {c['czytelnik_wizualny']}" if c.get("czytelnik_wizualny") else ""
    return f"pewność odczytu {c['poziom']}: linia {c['pewnosc_linii']}, inny odczyt: {c['inny_odczyt']}{visual}"


def cross_check_ocr(doc: Document, kind: str, value: str, text: str, result, status: str, note: str):
    """Kontrola krzyżowa wartości ze skanu na niezależnych odczytach OCR (inne rozdzielczości).

    Zwraca (wartość, status, uwaga, wskaźnik pewności). Numery z poprawną sumą kontrolną są potwierdzone
    inaczej; nazwisk i długich tekstów nie porównujemy znak po znaku (różnice w znakach diakrytycznych
    nie zmieniają znaczenia).
    """
    if kind in CHECKSUM_KINDS and status == "naprawiono":
        # Poprawka jednego znaku na podstawie sumy kontrolnej musi być widoczna w innym odczycie.
        if any(digits_in_text(str(result), doc.alt_text(dpi)) for dpi in ALT_DPIS):
            return result, status, note + "; potwierdzone innym odczytem OCR", None
        result, status, note = None, "nieczytelne", note + "; poprawki nie potwierdza żaden inny odczyt OCR"
    if kind in CHECKSUM_KINDS and result is None and status == "nieczytelne":
        for dpi in ALT_DPIS:                    # może inny odczyt ma ten numer z poprawną sumą
            other = snap_digits(value, doc.alt_text(dpi), kind)
            if other and VALIDATORS[kind](other, True).status == "ok":
                return other, "naprawiono", f"{value!r} -> numer z innego odczytu OCR (poprawna suma kontrolna)", None
        digits = digits_from_ocr(value)
        if kind == "nrb":
            digits = re.sub(r"\D", "", digits)
        if CHECKSUM_POLICY != "strict" and len(digits) in ID_LENGTHS[kind]:
            conf = ocr_confidence(doc, digits, text)
            if conf["poziom"] == "wysoka":
                extra = ""
                if VISUAL_READER is not None:       # tylko uwaga: reguły dla złej sumy czytelnik nie zmienia
                    verdict, detail = VISUAL_READER.check(doc, best_line(doc, digits), kind, digits)
                    conf["czytelnik_wizualny"] = verdict
                    extra = f"; {detail}" if verdict == "inne" else ""
                return digits, "ostrzezenie", f"zła suma kontrolna; {_describe(conf)}{extra}", conf
            return None, "nieczytelne", f"zła suma kontrolna; {_describe(conf)}", conf
        return result, status, note, None
    if result is None or not needs_second_read(kind, value, status):
        return result, status, note, None
    probe = str(result) if kind in ID_LENGTHS else value
    conf = ocr_confidence(doc, probe, text)
    if VISUAL_READER is not None and conf["poziom"] in ("niska", "srednia"):
        conf, veto = visual_check(doc, kind, probe, conf)
        if veto:
            return None, "nieczytelne", f"{veto}; {_describe(conf)}", conf
    if conf["poziom"] == "niska":
        return None, "nieczytelne", f"niezależne odczyty OCR dają różne wartości; {_describe(conf)}", conf
    if conf["poziom"] == "srednia":
        return result, "ostrzezenie", _describe(conf), conf
    if conf["poziom"] == "wysoka" and not note:
        note = _describe(conf)
    return result, status, note, conf


def ocr_confirms(doc: Document, probe: str, text: str) -> str | None:
    """Werdykt niezależnych odczytów OCR dla wartości z odczytu głównego (patrz textmatch.second_read).

    Wystarczy jeden zgodny odczyt (2 z 3). Kolejny odczyt jest wykonywany tylko wtedy, gdy poprzedni
    wartości nie potwierdził.
    """
    verdicts = []
    for dpi in ALT_DPIS:
        verdict = second_read(probe, text, doc.alt_text(dpi))
        if verdict == "zgodne":
            return verdict
        verdicts.append(verdict)
    for verdict in ("rozbiezne", "brak"):
        if verdict in verdicts:
            return verdict
    return None


def value_in_text(kind: str, raw: str, result, text: str) -> bool:
    """Czy wartość (w postaci podanej przez model albo po normalizacji) występuje w dokumencie."""
    if _compact(raw) in _compact(text):
        return True
    if kind == "date":
        return str(result) in dates_in_text(text, norm_date)
    if kind == "amount":
        whole = str(int(float(result)))
        return len(whole) >= 2 and whole in re.sub(r"[\s .']", "", text)
    if kind in ("bzp", "ted"):
        parts = [d for d in re.findall(r"\d+", str(result)) if len(d) >= 5]
        return bool(parts) and all(d in re.sub(r"[\s\-]", "", text) for d in parts)
    return _compact(str(result)) in _compact(text)


def decide_from_text(rule: dict, text: str):
    """Reguła `decide` z YAML: pozycja słownika nazwana wprost w dokumencie.

    `scope` - wyrażenia wskazujące zdanie, w którym dokument nazywa rzecz po imieniu (np. „Zamawiający w dniu …”),
    `patterns` - dla pozycji słownika lista wyrażeń. Rozstrzygnięcie zapada tylko wtedy, gdy w pierwszym
    znalezionym zdaniu pasuje dokładnie jedna pozycja; inaczej decyduje model. Zwraca (pozycja, zdanie) albo None.
    """
    flat = re.sub(r"\s+", " ", text)
    for scope in rule.get("scope", []):
        for sentence in (m.group(0) for m in re.finditer(scope, flat, flags=re.IGNORECASE)):
            hits = [key for key, patterns in rule.get("patterns", {}).items()
                    if any(re.search(p, sentence, flags=re.IGNORECASE) for p in patterns)]
            if len(hits) == 1:
                return int(hits[0]), sentence[:160]
            if hits:
                return None                      # zdanie pasuje do kilku pozycji - niech rozstrzyga model
    return None


def line_context_ok(patterns, kind: str, result, text: str) -> bool:
    """Reguła `line_pattern` z YAML: linia, w której stoi wartość, musi pasować do jednego z wzorców.

    Wzorzec to wyrażenie regularne z miejscem `{value}` na samą wartość. Służy do odróżnienia np. daty z
    nagłówka pisma („Miejscowość, dnia …” w osobnej linii) od dat w treści. Gdy wartości nie da się wskazać
    w żadnej linii (nietypowy zapis), reguła niczego nie odrzuca. Data rozbita między dwie linie to data
    ze zdania w treści - taka wymaganego miejsca nie spełnia.
    """
    hits = occurrences(str(result), text, norm_date if kind == "date" else None)
    if not hits:
        return not (kind == "date" and str(result) in dates_in_text(text, norm_date))
    patterns = [patterns] if isinstance(patterns, str) else patterns
    return any(re.search(p.replace("{value}", re.escape(fragment)), line) for line, fragment in hits for p in patterns)


def needs_second_read(kind: str, value: str, status: str) -> bool:
    if kind == "person":
        return False
    if kind in CHECKSUM_KINDS:
        return status != "ok"                  # poprawna suma kontrolna wystarcza
    if kind == "text":
        return len(value) <= 40 and sum(ch.isdigit() for ch in value) >= 2    # sygnatury, numery
    return True                                # krs, daty, kwoty, numery ogłoszeń


def verify_text(value: str, text: str, kind: str, status: str, note: str):
    """Sprawdza wartość tekstową w dokumencie; w razie potrzeby zastępuje ją dosłownym fragmentem tekstu."""
    if only_beside_redaction(value, text):
        return None, "niezweryfikowane", "wartość jest fragmentem danych zakrytych czarnym prostokątem"
    if kind == "person":       # nazwisko w dokumencie bywa odmienione, a wynik ma być w mianowniku
        if appears_in(value, text) or person_in(value, text):
            return value, status, note
        return None, "niezweryfikowane", "osoby nie ma w tekście dokumentu"
    snapped = snap_text(value, text)
    if snapped != value and appears_in(snapped, text):
        return snapped, "dopasowano", "uzupełniono ucięte słowo z tekstu"
    if appears_in(value, text):
        return value, status, note
    span = snap_span(value, text)
    if span:
        return span, "dopasowano", f"{value!r} -> dosłowny fragment dokumentu"
    if words_in(value, text):
        return value, status, "słowa wartości występują w dokumencie w kilku miejscach"
    return None, "niezweryfikowane", "wartości nie ma w tekście dokumentu"


def only_beside_redaction(value: str, text: str) -> bool:
    """Czy wartość występuje w dokumencie wyłącznie tuż obok znacznika [ZAKRYTE] w tej samej linii.

    Taka wartość to ocalały fragment zakrytej całości (np. „Kancelaria Prawna [ZAKRYTE]”), a nie pełna dana.
    """
    if REDACTED not in text:
        return False
    pattern = r"\s+".join(re.escape(w) for w in value.split())
    hits = list(re.finditer(pattern, text, flags=re.IGNORECASE)) if pattern else []
    marker, gap = re.escape(REDACTED), r"[ \t,;–\-]{0,3}"

    def beside(m) -> bool:
        before, after = text[max(0, m.start() - len(REDACTED) - 3): m.start()], text[m.end(): m.end() + len(REDACTED) + 3]
        return bool(re.search(marker + gap + r"\Z", before) or re.match(gap + marker, after))

    return bool(hits) and all(beside(m) for m in hits)


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
