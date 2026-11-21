"""Wypisuje różnice między wynikiem a gold dla spraw obecnych w katalogu wyników."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import flatten, load_json  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    pred_dir = Path(sys.argv[2])
    for item in manifest:
        pred_path = pred_dir / item["case"] / (Path(item["pdf"]).stem + ".json")
        if not (pred_dir / item["case"]).is_dir() or not item.get("gold"):
            continue
        gold, pred = load_json(Path(item["gold"])), load_json(pred_path)
        g, p = flatten(gold), flatten(pred) if pred else []
        if len(g) != len(p):
            print(f"{item['case']}/{pred_path.name}: liczba liści gold={len(g)} pred={len(p)}")
        for (gp, gv), (pp, pv) in zip(g, p):
            if gp == pp and gv != pv:
                print(f"{item['case']}/{pred_path.stem}  {gp}\n    gold: {gv!r}\n    pred: {pv!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
