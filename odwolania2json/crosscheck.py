"""Kontrola krzyżowa wyników - druga linia obrony po walidacji pojedynczych pól.

Zasada projektu: błędna wartość w JSON jest gorsza niż pole przekazane człowiekowi do sprawdzenia.
Trzy poziomy:
  1. drugi, niezależny odczyt skanu (extract.check_leaf + textmatch.second_read) - wartość z OCR
     bez sumy kontrolnej musi wyjść tak samo z dwóch odczytów w różnej rozdzielczości,
  2. kontrola przypisania (resolve_duplicates) - ten sam identyfikator nie może trafić do kilku pól;
     zostaje w tym, przy którego nazwie leży w dokumencie, a gdy nie da się tego ustalić - znika,
  3. kontrola między dokumentami jednej sprawy i reguły zdroworozsądkowe (case_findings) - reguły
     w configs/cross_checks.yaml; rozbieżność jest zgłaszana, ale nie zmienia JSON-ów, bo nie wiadomo,
     który dokument ma rację.
Wszystko, co wymaga uwagi człowieka, trafia do trace/<sprawa>/do_sprawdzenia.json.
"""
from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from .config import DocClass, is_leaf
from .textmatch import ID_LENGTHS, fold

REJECTED = ("nieczytelne", "niezweryfikowane")


# ---------------------------------------------------------------- poruszanie się po wyniku
def walk(spec, node, path: str = ""):
    """Zwraca (ścieżka, słownik-rodzic, klucz, specyfikacja) dla każdego pola końcowego."""
    if isinstance(spec, list):
        for i, item in enumerate(node if isinstance(node, list) else []):
            yield from walk(spec[0], item, f"{path}[{i}]")
    elif isinstance(spec, dict) and not is_leaf(spec):
        for key, sub in spec.items():
            sub_path = f"{path}.{key}" if path else key
            if is_leaf(sub):
                if isinstance(node, dict):
                    yield sub_path, node, key, sub
            else:
                yield from walk(sub, node.get(key) if isinstance(node, dict) else None, sub_path)


def get_values(data, path: str) -> list:
    """Wartości spod ścieżki w rodzaju `Odwolujacy[].pelnomocnik.imie_nazwisko`."""
    nodes = [data]
    for part in path.split("."):
        is_list, key = part.endswith("[]"), part.removesuffix("[]")
        found = []
        for node in nodes:
            value = node.get(key) if isinstance(node, dict) else None
            if value is None:
                continue
            found.extend(value if is_list and isinstance(value, list) else [value])
        nodes = found
    return [n for n in nodes if n is not None and not isinstance(n, (dict, list))]


# ---------------------------------------------------------------- 2. kontrola przypisania
def _digit_positions(text: str, digits: str) -> list[int]:
    pattern = r"[ \-]?".join(re.escape(d) for d in digits)
    return [m.start() for m in re.finditer(pattern, text)]


def _anchor_positions(text: str, parent: dict) -> list[int]:
    folded, out = fold(text), []
    for value in parent.values():
        if isinstance(value, str) and len(value) >= 4 and not value.replace(" ", "").isdigit():
            needle = fold(value)
            out += [m.start() for m in re.finditer(re.escape(needle), folded)]
    return out


def resolve_duplicates(cls: DocClass, data: dict, trace: list[dict], text: str) -> None:
    """Ten sam identyfikator w kilku polach: zostaje tylko tam, gdzie w dokumencie leży najbliżej nazwy."""
    groups: dict[str, list] = defaultdict(list)
    for path, parent, key, spec in walk(cls.output, data):
        value = parent.get(key)
        if value is not None and spec.get("validator") in ID_LENGTHS:
            groups[str(value)].append((path, parent, key))
    by_path = {t["pole"]: t for t in trace}
    for value, items in groups.items():
        if len(items) < 2:
            continue
        where = _digit_positions(text, value)
        scored = []
        for path, parent, key in items:
            anchors = _anchor_positions(text, parent)
            dist = min((abs(a - b) for a in anchors for b in where), default=float("inf"))
            scored.append((dist, path, parent, key))
        scored.sort(key=lambda s: s[0])
        distinct_parents = len({id(s[2]) for s in scored}) == len(scored)
        keep = scored[0][1] if distinct_parents and scored[0][0] * 2 < scored[1][0] else None
        for _, path, parent, key in scored:
            if path == keep:
                continue
            parent[key] = None
            entry = by_path.get(path)
            if entry is not None:
                entry.update(wartosc=None, status="niezweryfikowane",
                             uwaga=f"numer {value} przypisany do kilku pól"
                                   + (f"; w dokumencie leży przy polu {keep}" if keep else "; nie da się ustalić właściwego"))


def apply_field_rules(cls: DocClass, data: dict, trace: list[dict]) -> None:
    """Reguły zależności między polami jednego dokumentu, zapisane w YAML klasy:

    requires: <pole obok>  - pole ma sens tylko razem z innym (np. miejscowość z nagłówka tylko z datą),
    not_in: <ścieżka>      - wartość nie może powtarzać wartości z innej listy (np. podpisujący
                             pełnomocnictwo nie może być jednocześnie pełnomocnikiem).
    Pole łamiące regułę dostaje null i trafia na listę do sprawdzenia.
    """
    by_path = {t["pole"]: t for t in trace}

    def reject(path, parent, key, reason):
        parent[key] = None
        if path in by_path:
            by_path[path].update(wartosc=None, status="niezweryfikowane", uwaga=reason)

    for path, parent, key, spec in list(walk(cls.output, data)):
        value = parent.get(key)
        if value is None:
            continue
        need = spec.get("requires")
        if need and parent.get(need) is None:
            reject(path, parent, key, f"pole ma sens tylko razem z polem {need}, którego w dokumencie nie ma")
            continue
        other = spec.get("not_in")
        if other and any(fold(str(value)) == fold(str(v)) for v in get_values(data, other)):
            reject(path, parent, key, f"ta sama wartość występuje w {other}")
    _prune(cls.output, data)


def _empty(node) -> bool:
    if isinstance(node, dict):
        return all(_empty(v) for v in node.values())
    if isinstance(node, list):
        return all(_empty(v) for v in node)
    return node is None


def _prune(spec, node) -> None:
    """Usuwa z list elementy bez żadnej wartości (zostawia jeden, gdy lista byłaby pusta)."""
    if isinstance(spec, list) and isinstance(node, list):
        for item in node:
            _prune(spec[0], item)
        kept = [item for item in node if not _empty(item)]
        node[:] = kept or node[:1]
    elif isinstance(spec, dict) and not is_leaf(spec) and isinstance(node, dict):
        for key, sub in spec.items():
            _prune(sub, node.get(key))


# ---------------------------------------------------------------- 3. reguły między dokumentami
def load_rules(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("rules") or []


def _match(a, b) -> bool:
    a, b = str(a), str(b)
    if a.replace(" ", "").isdigit() or b.replace(" ", "").isdigit():
        return re.sub(r"\D", "", a) == re.sub(r"\D", "", b)
    fa, fb = fold(a), fold(b)
    return fa in fb or fb in fa or SequenceMatcher(None, fa, fb).ratio() >= 0.8


def _side(results: list[tuple[str, str, dict]], ref: str) -> list[tuple[str, object]]:
    cls_name, path = ref.split(":", 1)
    return [(name, v) for name, cls, data in results if cls == cls_name for v in get_values(data, path)]


def case_findings(rules: list[dict], results: list[tuple[str, str, dict]]) -> list[dict]:
    """results = [(plik, klasa, dane)] dla jednej sprawy. Zwraca listę rozbieżności (bez zmiany danych)."""
    out = []
    for rule in rules:
        kind = rule.get("kind")
        if kind == "one_of":
            allowed = rule["values"]
            for name, value in _side(results, rule["field"]):
                if value not in allowed:
                    out.append(_finding(rule, f"{name}: wartość {value!r} spoza typowych {allowed}"))
            continue
        left, right = _side(results, rule["left"]), _side(results, rule["right"])
        if not left or not right:
            continue                        # brak jednej ze stron - nie ma czego porównać
        if kind == "same" and not any(_match(a, b) for _, a in left for _, b in right):
            out.append(_finding(rule, f"{_show(left)} ≠ {_show(right)}"))
        elif kind == "not_after":
            for (ln, a), (rn, b) in ((x, y) for x in left for y in right):
                if str(a) > str(b):         # daty w formacie RRRR-MM-DD porównują się jak tekst
                    out.append(_finding(rule, f"{ln}: {a} jest później niż {b} ({rn})"))
    return out


def _show(side: list[tuple[str, object]]) -> str:
    return "; ".join(f"{name}: {value!r}" for name, value in side[:4])


def _finding(rule: dict, detail: str) -> dict:
    return {"typ": "kontrola_krzyzowa", "regula": rule.get("id"), "opis": rule.get("desc", ""), "szczegoly": detail}


# ---------------------------------------------------------------- lista do sprawdzenia przez człowieka
def review_entries(file_name: str, trace: list[dict]) -> list[dict]:
    out = []
    for t in trace:
        if t["status"] in REJECTED:
            out.append({"typ": "pole_odrzucone", "plik": file_name, "pole": t["pole"],
                        "proponowana_wartosc": t.get("surowa"), "powod": t.get("uwaga", ""), "zrodlo": t.get("zrodlo")})
        elif t["status"] == "ostrzezenie":
            out.append({"typ": "pole_z_ostrzezeniem", "plik": file_name, "pole": t["pole"],
                        "wartosc": t.get("wartosc"), "powod": t.get("uwaga", ""), "zrodlo": t.get("zrodlo")})
    return out
