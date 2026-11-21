"""Buduje manifest ewaluacyjny z danych treningowych UZP i złotego zestawu realnego.

Podział: 12 spraw zamrożonych jako hold-out (stałe ziarno), reszta jako dev.
Manifest zawiera ścieżki bezwzględne: case, pdf, gold, cls, split.

Użycie:
  python tools/make_manifest.py --uzp ../dane/uzp-hacknation-2026 --gold-real ../eval/gold-real --out ../eval/manifest.json
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

# Klasa -> nazwy PDF używane w kolejnych wydaniach danych UZP.
TRAIN_FILES = {
    "odwolanie": ("odwolanie.pdf",),
    "pelnomocnictwo": ("pelnomocnictwo.pdf",),
    "przelew": ("przelew.pdf", "potwierdzenie_przelewu.pdf"),
}
HOLDOUT_SIZE = 12
SEED = 20261121


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uzp", required=True, type=Path)
    ap.add_argument("--gold-real", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    cases = sorted(p for p in (args.uzp / "dane").glob("przyklad_*") if p.is_dir())
    holdout = set(random.Random(SEED).sample([c.name for c in cases], HOLDOUT_SIZE))
    manifest = []
    for case in cases:
        for cls, names in TRAIN_FILES.items():
            matches = [case / name for name in names if (case / name).is_file()]
            if len(matches) != 1:
                raise ValueError(f"{case.name}: oczekiwano jednego PDF klasy {cls}, znaleziono {len(matches)}")
            manifest.append({
                "case": case.name,
                "pdf": str(matches[0].resolve()),
                "gold": str((case / f"{cls}.json").resolve()),
                "cls": cls,
                "split": "holdout" if case.name in holdout else "dev",
            })

    template = args.uzp / "szablon-aplikacja" / "input"
    if args.gold_real and template.is_dir():
        for case in sorted(p for p in template.iterdir() if p.is_dir()):
            for pdf in sorted(case.glob("*.pdf")):
                gold = args.gold_real / case.name / (pdf.stem + ".json")
                manifest.append({
                    "case": case.name,
                    "pdf": str(pdf.resolve()),
                    "gold": str(gold.resolve()) if gold.is_file() else None,  # brak gold = dokument spoza klas
                    "cls": "odwolanie" if gold.is_file() else "inny",
                    "split": "real",
                })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {}
    for m in manifest:
        counts[m["split"]] = counts.get(m["split"], 0) + 1
    print(f"manifest: {args.out} | dokumenty: {counts} | hold-out: {sorted(holdout)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
