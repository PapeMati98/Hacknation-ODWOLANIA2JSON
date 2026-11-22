"""Powtarza weryfikację i kontrolę krzyżową na zapisanych odpowiedziach modelu (bez uruchamiania modelu).

Ślad każdego dokumentu zawiera odpowiedź modelu, więc po zmianie walidatorów, reguł YAML albo kontroli
krzyżowej wynik można przeliczyć w sekundy (dla skanów: plus czas OCR) i od razu zmierzyć F1.

Użycie:
  python tools/replay.py --trace ../eval/runs/v3/dev-trace --output ../eval/runs/v3/dev-replay
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from odwolania2json import pdfio  # noqa: E402
from odwolania2json.config import load_classes  # noqa: E402
from odwolania2json.crosscheck import case_findings, load_rules, review_entries  # noqa: E402
from odwolania2json.extract import CONTINUED, Extractor  # noqa: E402

APP = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trace", required=True, type=Path, help="katalog trace/ z wcześniejszego przebiegu")
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    classes = {c.name: c for c in load_classes(APP / "configs" / "classes")}
    rules = load_rules(APP / "configs" / "cross_checks.yaml")
    max_pages = max(c.pages for c in classes.values())
    cases: dict[Path, dict] = {}
    for path in sorted(args.trace.rglob("*.trace.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not record.get("klasa") or "odpowiedz_modelu" not in record:
            continue
        cls = classes[record["klasa"]]
        rel = path.relative_to(args.trace).with_name(path.name.removesuffix(".trace.json") + ".json")
        more = cls.continue_when_empty      # przebieg doczytał dalsze strony: reguły potrzebują ich tekstu
        pages = int(more["pages"]) if more and CONTINUED in record["odpowiedz_modelu"] else max_pages
        doc = pdfio.load(record["plik"], max_pages=pages)
        data, trace = Extractor.finish(doc, cls, record["odpowiedz_modelu"])
        out = args.output / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        case = cases.setdefault(rel.parent, {"results": [], "review": []})
        case["results"].append((rel.name, cls.name, data))
        case["review"] += review_entries(rel.name, trace)
    total = 0
    for case_dir, case in sorted(cases.items()):
        items = case["review"] + case_findings(rules, case["results"])
        total += len(items)
        for item in items:
            print(f"  {case_dir} {item.get('plik', '')} {item.get('pole', item.get('regula'))} | "
                  f"{item.get('proponowana_wartosc', item.get('wartosc', ''))} | {item.get('powod', item.get('szczegoly'))}")
    print(f"dokumentów: {sum(len(c['results']) for c in cases.values())}, pozycji do sprawdzenia: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
