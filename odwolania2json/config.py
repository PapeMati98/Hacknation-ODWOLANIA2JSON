"""Ładowanie klas dokumentów z YAML oraz budowa formularza i opisu pól dla modelu.

Nowa klasa dokumentu = nowy plik configs/classes/<nazwa>.yaml. Kod nie wymaga zmian.

Struktura `output` w YAML odwzorowuje wynikowy JSON. Model nie generuje JSON-a, tylko
wypełnia zwięzły formularz (sekcje `## Nazwa`, linie `klucz: wartość`), który jest
zamieniany na JSON przez kod - to kilkukrotnie mniej tokenów na wyjściu niż JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Field:
    key: str                 # klucz w formularzu, np. "pelnomocnik.imie_nazwisko"
    spec: dict
    multi_inner: str | None = None   # dla listy jednopolowej: nazwa pola elementu


@dataclass
class Section:
    name: str
    is_list: bool
    fields: list[Field]


@dataclass
class DocClass:
    name: str
    description: str
    pages: int
    keywords: dict[str, float]
    negative: dict[str, float]
    output: dict
    dictionaries: dict = field(default_factory=dict)
    hints: dict = field(default_factory=dict)        # podpowiedzi do pozycji słowników
    min_score: float = 4.0
    title: list[str] = field(default_factory=list)   # słowa tytułu szukane na początku 1. strony
    title_weight: float = 5.0

    # ------------------------------------------------------------- formularz
    def sections(self) -> list[Section]:
        out, root = [], []
        for name, node in self.output.items():
            if isinstance(node, list):
                out.append(Section(name, True, _flatten(node[0])))
            elif is_leaf(node):
                if "derive" not in node:
                    root.append(Field(name, node))
            else:
                out.append(Section(name, False, _flatten(node)))
        if root:
            out.insert(0, Section("_", False, root))
        return out

    def template(self) -> str:
        lines = []
        for s in self.sections():
            lines.append(f"## {s.name} 1   (xN)" if s.is_list else f"## {s.name}")
            lines += [f"{f.key}:" for f in s.fields]
        return "\n".join(lines)

    def first_header(self) -> str:
        s = self.sections()[0]
        return f"## {s.name} 1" if s.is_list else f"## {s.name}"

    def field_guide(self) -> str:
        lines = []
        for s in self.sections():
            lines.append(f"[{s.name}]")
            for f in s.fields:
                lines.append(f"- {f.key}: {self._describe(f)}")
        return "\n".join(lines)

    def _describe(self, f: Field) -> str:
        spec, desc = f.spec, f.spec.get("desc", "")
        if "enum_from" in spec:
            name = spec["enum_from"]
            hints = self.hints.get(name, {})
            items = "; ".join(f"{k} = {v}" + (f" ({hints[k]})" if k in hints else "")
                              for k, v in self.dictionaries[name].items())
            desc += f" Wpisz sam numer. Słownik: {items}."
        elif "enum" in spec:
            desc += " Dozwolone wartości: " + ", ".join(str(v) for v in spec["enum"]) + "."
        if f.multi_inner:
            desc += " Kilka wartości oddziel znakiem ' | '."
        return desc.strip()


def _flatten(node: dict, prefix: str = "") -> list[Field]:
    out: list[Field] = []
    for key, value in node.items():
        if is_leaf(value):
            if "derive" not in value:
                out.append(Field(prefix + key, value))
        elif isinstance(value, list):
            inner = [(k, v) for k, v in value[0].items() if is_leaf(v) and "derive" not in v]
            if len(inner) != 1 or len(value[0]) != 1:
                raise ValueError(f"Lista zagnieżdżona '{prefix + key}' może mieć elementy tylko z jednym polem.")
            out.append(Field(prefix + key, inner[0][1], multi_inner=inner[0][0]))
        else:
            out.extend(_flatten(value, f"{prefix}{key}."))
    return out


def is_leaf(node) -> bool:
    return isinstance(node, dict) and ("type" in node or "derive" in node or "enum" in node or "enum_from" in node)


def load_classes(directory: Path) -> list[DocClass]:
    classes = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cls = raw.get("classify", {})
        doc_class = DocClass(
            name=raw["name"],
            description=raw.get("description", "").strip(),
            pages=int(raw.get("pages", 3)),
            keywords={k.lower(): float(v) for k, v in (cls.get("keywords") or {}).items()},
            negative={k.lower(): float(v) for k, v in (cls.get("negative") or {}).items()},
            min_score=float(cls.get("min_score", 4)),
            title=list(cls.get("title") or []),
            title_weight=float(cls.get("title_weight", 5)),
            output=raw["output"],
            dictionaries={k: {int(i): s for i, s in d.items()} for k, d in (raw.get("dictionaries") or {}).items()},
            hints={k: {int(i): s for i, s in d.items()} for k, d in (raw.get("hints") or {}).items()},
        )
        doc_class.sections()  # walidacja konfiguracji przy starcie
        classes.append(doc_class)
    if not classes:
        raise FileNotFoundError(f"Brak klas dokumentów w {directory}")
    return classes
