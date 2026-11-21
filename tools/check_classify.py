"""Sprawdza klasyfikator na manifestach (bez LLM): macierz pomyłek i lista błędów."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from odwolania2json import pdfio  # noqa: E402
from odwolania2json.config import load_classes  # noqa: E402
from odwolania2json.extract import classify  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    classes = load_classes(Path(__file__).resolve().parent.parent / "configs" / "classes")
    items = []
    for m in sys.argv[1:]:
        items += json.loads(Path(m).read_text(encoding="utf-8"))
    conf: collections.Counter = collections.Counter()
    errors = []
    for x in items:
        doc = pdfio.load(x["pdf"], max_pages=2)
        got, scores = classify(doc, classes)
        want = None if x["cls"] == "inny" else x["cls"]
        conf[(want, got)] += 1
        if got != want:
            errors.append(f"{x['split']}/{x['case']}/{Path(x['pdf']).name}: oczekiwano {want}, jest {got} {scores}")
    ok = sum(n for (w, g), n in conf.items() if w == g)
    print(f"trafność: {ok}/{sum(conf.values())}")
    for (w, g), n in sorted(conf.items(), key=str):
        print(f"  {str(w):15s} -> {str(g):15s} {n}")
    for e in errors:
        print("  BŁĄD", e)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
