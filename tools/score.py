"""Licznik F1 dla Odwołania2json.

Porównuje wynikowe JSON-y z danymi referencyjnymi na poziomie liści.
Listy traktowane są jak multizbiory (kolejność elementów nie ma znaczenia).

Tryby (organizator nie opublikował dokładnej metryki, więc liczymy oba):
  - with_null: liść o wartości null też jest punktowany (null == null to TP),
  - skip_null: liście null pomijane po obu stronach.

Użycie:
  python tools/score.py --manifest eval/manifest.json --pred output [--split dev] [--lenient] [--report out.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

LIST_MARK = "[]"


def flatten(obj, path: str = "") -> list[tuple[str, object]]:
    """Spłaszcza JSON do par (ścieżka, wartość); indeksy list zastępuje znacznikiem []."""
    if isinstance(obj, dict):
        out: list[tuple[str, object]] = []
        for key, value in obj.items():
            out.extend(flatten(value, f"{path}.{key}" if path else key))
        return out
    if isinstance(obj, list):
        out = []
        for item in obj:
            out.extend(flatten(item, f"{path}{LIST_MARK}"))
        return out
    return [(path, obj)]


def norm_value(value, lenient: bool):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not lenient or not isinstance(value, str):
        return value
    text = re.sub(r"\s+", " ", value).strip().casefold()
    return text.replace("„", '"').replace("”", '"').replace("“", '"')


def leaves(obj, lenient: bool, skip_null: bool) -> Counter:
    counter: Counter = Counter()
    if obj is None:
        return counter
    for path, value in flatten(obj):
        if skip_null and value is None:
            continue
        counter[(path, json.dumps(norm_value(value, lenient), ensure_ascii=False))] += 1
    return counter


def load_json(path: Path):
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def score(manifest: list[dict], pred_dir: Path, lenient: bool) -> dict:
    result = {}
    for mode, skip_null in (("with_null", False), ("skip_null", True)):
        tp = fp = fn = 0
        per_field: dict[str, Counter] = defaultdict(Counter)
        per_class: dict[str, Counter] = defaultdict(Counter)
        bad_json = 0
        for item in manifest:
            pred_path = pred_dir / item["case"] / (Path(item["pdf"]).stem + ".json")
            pred = load_json(pred_path)
            if pred is None and pred_path.is_file() and pred_path.stat().st_size > 0:
                bad_json += 1
            gold = load_json(Path(item["gold"])) if item.get("gold") else None
            g = leaves(gold, lenient, skip_null)
            p = leaves(pred, lenient, skip_null)
            inter = g & p
            for (path, _), n in inter.items():
                per_field[f"{item['cls']}:{path}"]["tp"] += n
            for (path, _), n in (p - g).items():
                per_field[f"{item['cls']}:{path}"]["fp"] += n
            for (path, _), n in (g - p).items():
                per_field[f"{item['cls']}:{path}"]["fn"] += n
            d_tp, d_fp, d_fn = sum(inter.values()), sum((p - g).values()), sum((g - p).values())
            tp, fp, fn = tp + d_tp, fp + d_fp, fn + d_fn
            per_class[item["cls"]].update(tp=d_tp, fp=d_fp, fn=d_fn)
        result[mode] = {
            **prf(tp, fp, fn),
            "invalid_json_files": bad_json,
            "per_class": {k: prf(v["tp"], v["fp"], v["fn"]) for k, v in sorted(per_class.items())},
            "per_field": {k: prf(v["tp"], v["fp"], v["fn"]) for k, v in sorted(per_field.items())},
        }
    return result


def prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else (1.0 if not (fp or fn) else 0.0)
    return {"f1": round(f1, 4), "precision": round(precision, 4), "recall": round(recall, 4), "tp": tp, "fp": fp, "fn": fn}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--pred", required=True, type=Path, help="katalog output/ z wynikami")
    ap.add_argument("--split", help="filtr po polu split w manifeście (np. dev, holdout, real)")
    ap.add_argument("--lenient", action="store_true", help="porównanie tekstu bez wielkości liter i nadmiarowych spacji")
    ap.add_argument("--report", type=Path, help="zapisz pełny raport JSON")
    ap.add_argument("--worst", type=int, default=12, help="ile najsłabszych pól wypisać")
    ap.add_argument("--only-present", action="store_true", help="oceniaj tylko sprawy obecne w katalogu wyników")
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.split:
        manifest = [m for m in manifest if m.get("split") == args.split]
    if args.only_present:
        manifest = [m for m in manifest if (args.pred / m["case"]).is_dir()]
    if not manifest:
        print("Pusty manifest po filtrze.", file=sys.stderr)
        return 2
    res = score(manifest, args.pred, args.lenient)
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"dokumentów: {len(manifest)} | split: {args.split or 'wszystkie'} | lenient: {args.lenient}")
    for mode in ("with_null", "skip_null"):
        r = res[mode]
        print(f"[{mode}] F1={r['f1']:.4f} P={r['precision']:.4f} R={r['recall']:.4f} (tp={r['tp']} fp={r['fp']} fn={r['fn']}) błędny JSON={r['invalid_json_files']}")
        for cls, c in r["per_class"].items():
            print(f"    {cls:16s} F1={c['f1']:.4f}")
    worst = sorted(res["with_null"]["per_field"].items(), key=lambda kv: kv[1]["f1"])[: args.worst]
    print("Najsłabsze pola (with_null):")
    for field, c in worst:
        print(f"    {c['f1']:.3f}  {field}  (fp={c['fp']} fn={c['fn']})")
    if args.report:
        args.report.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
