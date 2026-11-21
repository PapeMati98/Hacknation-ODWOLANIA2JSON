"""Ile kosztuje i co daje kontrola „dwa odczyty OCR” - pomiar bez modelu językowego.

Dla każdej wartości z gold zawierającej cyfry (numery, sygnatury) sprawdza na skanach:
  - czy jest w odczycie głównym (jeśli nie - OCR ją zgubił lub przekręcił),
  - czy potwierdza ją drugi odczyt.
Wartość obecna w odczycie głównym, a niepotwierdzona przez drugi, zostałaby wyzerowana mimo
poprawności - to koszt kontroli. Wynik pokazuje też, jak często oba odczyty są zgodne.

Użycie:
  python tools/check_second_read.py --manifest ../eval/scandev/manifest.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from odwolania2json import pdfio  # noqa: E402
from odwolania2json.config import load_classes  # noqa: E402
from odwolania2json.crosscheck import walk  # noqa: E402
from odwolania2json.extract import ocr_confirms  # noqa: E402
from odwolania2json.textmatch import second_read  # noqa: E402

APP = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    classes = {c.name: c for c in load_classes(APP / "configs" / "classes")}
    manifest = [m for m in json.loads(args.manifest.read_text(encoding="utf-8")) if m.get("gold") and m["cls"] in classes]
    if args.limit:
        manifest = manifest[: args.limit]
    stats: dict[str, Counter] = defaultdict(Counter)
    lost = []
    t0, pages = time.perf_counter(), 0
    for item in manifest:
        cls = classes[item["cls"]]
        doc = pdfio.load(item["pdf"], max_pages=cls.pages)
        pages += len(doc.pages)
        if not doc.is_scan:
            continue
        primary = doc.text(max_pages=None)
        gold = json.loads(Path(item["gold"]).read_text(encoding="utf-8"))
        for path, parent, key, spec in walk(cls.output, gold):
            value = parent.get(key)
            if value is None or "derive" in spec or "enum" in spec or "enum_from" in spec:
                continue
            kind = spec.get("validator", "text")
            value = str(value)
            if kind in ("date", "amount", "person", "email") or sum(ch.isdigit() for ch in value) < 4 or len(value) > 40:
                continue                       # gold ma daty i kwoty znormalizowane - nie da się ich szukać w tekście
            first = second_read(value, primary, doc.alt_text())
            res = first if first is not False else ocr_confirms(doc, value, primary)
            name = {None: "brak_w_glownym", True: "zgodne", False: "rozbiezne"}[res]
            stats[kind][name] += 1
            stats[kind]["trzeci_odczyt"] += first is False
            if res is False:
                lost.append(f"{item['case']}/{Path(item['pdf']).name} {path} = {value}")
    print(f"dokumentów: {len(manifest)}, stron: {pages}, czas wczytania z dwoma odczytami: {time.perf_counter() - t0:.0f} s "
          f"({(time.perf_counter() - t0) / max(pages, 1):.1f} s/str.)")
    total = Counter()
    for kind, c in sorted(stats.items()):
        total.update(c)
        print(f"  {kind:6s} zgodne={c['zgodne']:3d}  rozbieżne={c['rozbiezne']:3d}  brak w odczycie głównym={c['brak_w_glownym']:3d}"
              f"  (trzeci odczyt potrzebny: {c['trzeci_odczyt']})")
    n = (total["zgodne"] + total["rozbiezne"] + total["brak_w_glownym"]) or 1
    print(f"  RAZEM  zgodne={total['zgodne']} ({total['zgodne'] / n:.1%})  rozbieżne={total['rozbiezne']} "
          f"({total['rozbiezne'] / n:.1%})  brak w głównym={total['brak_w_glownym']} ({total['brak_w_glownym'] / n:.1%})")
    for line in lost[:20]:
        print("   poprawna wartość niepotwierdzona:", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
