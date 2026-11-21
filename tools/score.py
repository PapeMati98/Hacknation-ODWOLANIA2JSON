"""Licznik F1 dla Odwołania2json według definicji organizatora (Discord UZP, 21.11.2026).

  TP - wartość jest w wyniku i zgadza się z ground truth; dla długich tekstów (np. nazw firm)
       wystarcza zgodność co najmniej 80%,
  TN - wartości nie ma ani w wyniku, ani w ground truth (nie wpływa na F1),
  FP - wartość jest tylko w wyniku albo jest w obu, ale błędna,
  FN - wartości nie ma w wyniku, a jest w ground truth.

Elementy list są dopasowywane po treści (nie po kolejności). Liczone są dwa warianty:
  uzp   - długie teksty porównywane z progiem 80% (difflib),
  exact - wszystkie wartości muszą być identyczne (dolne oszacowanie).

Użycie:
  python tools/score.py --manifest ../eval/manifest.json --pred output [--split dev] [--only-present]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

LONG_TEXT = 20      # od tej długości tekst jest porównywany z progiem podobieństwa
THRESHOLD = 0.80


def flatten(obj, path: str = "") -> list[tuple[str, object]]:
    """Spłaszcza JSON do par (ścieżka, wartość) - używane przez narzędzia diagnostyczne."""
    if isinstance(obj, dict):
        return [x for k, v in obj.items() for x in flatten(v, f"{path}.{k}" if path else k)]
    if isinstance(obj, list):
        return [x for v in obj for x in flatten(v, f"{path}[]")]
    return [(path, obj)]


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


def norm(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return value


def same(gold, pred, fuzzy: bool) -> bool:
    g, p = norm(gold), norm(pred)
    if isinstance(g, float) or isinstance(p, float):
        try:
            return float(g) == float(p)
        except (TypeError, ValueError):
            return str(gold).strip() == str(pred).strip()
    if g == p:
        return True
    if fuzzy and isinstance(g, str) and isinstance(p, str) and len(g) >= LONG_TEXT:
        return SequenceMatcher(None, g.casefold(), p.casefold()).ratio() >= THRESHOLD
    return False


def compare(gold, pred, path: str, fuzzy: bool, acc: dict[str, Counter]) -> None:
    if isinstance(gold, dict) or isinstance(pred, dict):
        g = gold if isinstance(gold, dict) else {}
        p = pred if isinstance(pred, dict) else {}
        for key in list(g) + [k for k in p if k not in g]:
            compare(g.get(key), p.get(key), f"{path}.{key}" if path else key, fuzzy, acc)
        return
    if isinstance(gold, list) or isinstance(pred, list):
        g = list(gold) if isinstance(gold, list) else []
        p = list(pred) if isinstance(pred, list) else []
        pairs = sorted(((tp_count(gi, pj, fuzzy), i, j) for i, gi in enumerate(g) for j, pj in enumerate(p)),
                       reverse=True)
        used_g, used_p = set(), set()
        for _, i, j in pairs:
            if i in used_g or j in used_p:
                continue
            used_g.add(i), used_p.add(j)
            compare(g[i], p[j], f"{path}[]", fuzzy, acc)
        for i, gi in enumerate(g):
            if i not in used_g:
                compare(gi, None, f"{path}[]", fuzzy, acc)
        for j, pj in enumerate(p):
            if j not in used_p:
                compare(None, pj, f"{path}[]", fuzzy, acc)
        return
    if gold is None and pred is None:
        acc[path]["tn"] += 1
    elif gold is None:
        acc[path]["fp"] += 1
    elif pred is None:
        acc[path]["fn"] += 1
    elif same(gold, pred, fuzzy):
        acc[path]["tp"] += 1
    else:
        acc[path]["fp"] += 1      # wartość obecna, ale błędna


def tp_count(gold, pred, fuzzy: bool) -> int:
    acc: dict[str, Counter] = defaultdict(Counter)
    compare(gold, pred, "", fuzzy, acc)
    return sum(c["tp"] for c in acc.values())


def prf(c: Counter) -> dict:
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else (1.0 if not (fp or fn) else 0.0)
    return {"f1": round(f1, 4), "precision": round(precision, 4), "recall": round(recall, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": c["tn"]}


def score(manifest: list[dict], pred_dir: Path) -> dict:
    result = {}
    for mode, fuzzy in (("uzp", True), ("exact", False)):
        total: Counter = Counter()
        per_field: dict[str, Counter] = defaultdict(Counter)
        per_class: dict[str, Counter] = defaultdict(Counter)
        per_doc: dict[str, dict] = {}
        for item in manifest:
            pred = load_json(pred_dir / item["case"] / (Path(item["pdf"]).stem + ".json"))
            gold = load_json(Path(item["gold"])) if item.get("gold") else None
            acc: dict[str, Counter] = defaultdict(Counter)
            compare(gold, pred, "", fuzzy, acc)
            doc_total: Counter = Counter()
            for path, c in acc.items():
                per_field[f"{item['cls']}:{path}"].update(c)
                doc_total.update(c)
            per_class[item["cls"]].update(doc_total)
            total.update(doc_total)
            per_doc[f"{item['case']}/{Path(item['pdf']).name}"] = prf(doc_total)
        result[mode] = {**prf(total),
                        "per_class": {k: prf(v) for k, v in sorted(per_class.items())},
                        "per_field": {k: prf(v) for k, v in sorted(per_field.items())},
                        "per_doc": per_doc}
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--pred", required=True, type=Path, help="katalog output/ z wynikami")
    ap.add_argument("--split", help="filtr po polu split w manifeście (np. dev, holdout, real, scandev)")
    ap.add_argument("--only-present", action="store_true", help="oceniaj tylko sprawy obecne w katalogu wyników")
    ap.add_argument("--report", type=Path, help="zapisz pełny raport JSON")
    ap.add_argument("--worst", type=int, default=12, help="ile najsłabszych pól wypisać")
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.split:
        manifest = [m for m in manifest if m.get("split") == args.split]
    if args.only_present:
        manifest = [m for m in manifest if (args.pred / m["case"]).is_dir()]
    if not manifest:
        print("Pusty manifest po filtrze.", file=sys.stderr)
        return 2
    res = score(manifest, args.pred)
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"dokumentów: {len(manifest)} | split: {args.split or 'wszystkie'}")
    for mode in ("uzp", "exact"):
        r = res[mode]
        print(f"[{mode:5s}] F1={r['f1']:.4f} P={r['precision']:.4f} R={r['recall']:.4f} "
              f"(tp={r['tp']} fp={r['fp']} fn={r['fn']} tn={r['tn']})")
        print("        " + "  ".join(f"{cls}={c['f1']:.3f}" for cls, c in r["per_class"].items()))
    fields = [(k, v) for k, v in res["uzp"]["per_field"].items() if v["fp"] or v["fn"]]
    if fields and args.worst:
        print("Pola z błędami (uzp), od najsłabszych:")
        for name, c in sorted(fields, key=lambda kv: kv[1]["f1"])[: args.worst]:
            print(f"    {c['f1']:.3f}  {name}  (tp={c['tp']} fp={c['fp']} fn={c['fn']})")
    if args.report:
        args.report.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
