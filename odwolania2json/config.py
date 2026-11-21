"""Ładowanie klas dokumentów z YAML i budowa schematu JSON dla modelu.

Nowa klasa dokumentu = nowy plik configs/classes/<nazwa>.yaml. Kod nie wymaga zmian.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class DocClass:
    name: str
    description: str
    pages: int
    keywords: dict[str, float]
    negative: dict[str, float]
    output: dict
    dictionaries: dict = field(default_factory=dict)
    min_score: float = 4.0
    title: list[str] = field(default_factory=list)   # słowa tytułu szukane na początku 1. strony
    title_weight: float = 5.0

    # ------------------------------------------------------------- schemat dla LLM
    def json_schema(self) -> dict:
        return self._schema(self.output)

    def _schema(self, node):
        if isinstance(node, list):
            return {"type": "array", "items": self._schema(node[0]), "minItems": 1, "maxItems": 4}
        if is_leaf(node):
            return self._leaf_schema(node)
        props = {k: self._schema(v) for k, v in node.items() if not (is_leaf(v) and "derive" in v)}
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}

    def _leaf_schema(self, spec: dict) -> dict:
        if "enum_from" in spec:
            return {"enum": [int(k) for k in self.dictionaries[spec["enum_from"]]] + [None]}
        if "enum" in spec:
            return {"enum": list(spec["enum"]) + [None]}
        t = spec.get("type", "string")
        return {"type": [t, "null"]}

    # ------------------------------------------------------------- opis pól dla promptu
    def field_guide(self) -> str:
        lines: list[str] = []
        self._guide(self.output, "", lines)
        return "\n".join(lines)

    def _guide(self, node, path: str, lines: list[str]):
        if isinstance(node, list):
            self._guide(node[0], path + "[]", lines)
            return
        if is_leaf(node):
            if "derive" in node:
                return
            extra = ""
            if "enum_from" in node:
                d = self.dictionaries[node["enum_from"]]
                extra = " Słownik: " + "; ".join(f"{k} = {v}" for k, v in d.items()) + "."
            lines.append(f"- {path}: {node.get('desc', '')}{extra}")
            return
        for k, v in node.items():
            self._guide(v, f"{path}.{k}" if path else k, lines)


def is_leaf(node) -> bool:
    return isinstance(node, dict) and ("type" in node or "derive" in node or "enum" in node or "enum_from" in node)


def load_classes(directory: Path) -> list[DocClass]:
    classes = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cls = raw.get("classify", {})
        classes.append(DocClass(
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
        ))
    if not classes:
        raise FileNotFoundError(f"Brak klas dokumentów w {directory}")
    return classes
