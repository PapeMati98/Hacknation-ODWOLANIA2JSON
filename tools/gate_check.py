"""Bramka końcowej oceny modelem (opcja `check` w YAML) na gotowych wynikach - bez ponownej ekstrakcji.

Dla każdego niepustego pola z opcją `check` w zapisanym wyniku zadaje modelowi pytanie zamknięte TAK/NIE
(wartość + kilka linii dokumentu) i porównuje odpowiedź z gold:
  fałszywe NIE - pole poprawne, a model je odrzuca (strata trafienia),
  wykrycie     - pole błędne, a model je odrzuca (błąd zamienia się w brak wartości).

  python tools/gate_check.py --run ../eval/manifest.json=../eval/runs/v6/dev-out --run ../eval/skany-manifest.json=../eval/runs/skany1/out
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odwolania2json import pdfio                                          # noqa: E402
from odwolania2json.config import load_classes                            # noqa: E402
from odwolania2json.crosscheck import get_values, walk                    # noqa: E402
from odwolania2json.sanity import check_prompt, context_lines, says_no    # noqa: E402


def same(a: str, b: str) -> bool:
    a, b = " ".join(str(a).casefold().split()), " ".join(str(b).casefold().split())
    return a == b or (len(b) > 20 and SequenceMatcher(None, a, b).ratio() >= 0.8)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", required=True, help="manifest=katalog_wyników")
    ap.add_argument("--model", default=str(Path(__file__).resolve().parent.parent / "models" / "Qwen3.5-4B-Q4_K_M.gguf"))
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    app = Path(__file__).resolve().parent.parent
    classes = {c.name: c for c in load_classes(app / "configs" / "classes")}

    jobs = []
    for pair in args.run:
        manifest, pred_dir = pair.split("=", 1)
        for item in json.loads(Path(manifest).read_text(encoding="utf-8")):
            if not item.get("gold") or item.get("split") == "holdout" or item.get("cls") not in classes:
                continue
            gold_path = Path(item["gold"])
            hits = [p for p in Path(pred_dir).rglob(Path(item["pdf"]).stem + ".json") if p.parent.name == Path(item["pdf"]).parent.name]
            if len(hits) > 1:                       # ten sam numer w kilku klasach: rozstrzyga katalog klasy
                hits = [p for p in hits if Path(item["pdf"]).parent.parent.name in p.parts]
            if not hits:
                continue
            jobs.append((item, json.loads(gold_path.read_text(encoding="utf-8")), json.loads(hits[0].read_text(encoding="utf-8"))))
    print(f"dokumentów: {len(jobs)}", flush=True)

    from odwolania2json.llm import LlamaCppBackend
    backend = LlamaCppBackend(args.model, args.threads)
    rows, times = [], []
    for item, gold, pred in jobs:
        cls = classes[item["cls"]]
        text = None
        for path, parent, key, spec in walk(cls.output, pred):
            value = parent.get(key)
            if value is None or not spec.get("check"):
                continue
            if text is None:
                text = pdfio.load(item["pdf"], max_pages=cls.pages).text()
            generic = ".".join(part.split("[")[0] + ("[]" if "[" in part else "") for part in path.split("."))
            correct = any(same(value, g) for g in get_values(gold, generic))
            t0 = time.perf_counter()
            answer = backend.say(check_prompt(spec["check"], str(value), context_lines(text, str(value))), 3)
            times.append(time.perf_counter() - t0)
            no = says_no(answer)
            rows.append({"sprawa": item["case"], "klasa": item["cls"], "skan": item.get("split") == "skany", "pole": generic,
                         "wartosc": value, "poprawna": correct, "odpowiedz": answer, "czas_s": round(times[-1], 2)})
            if no or not correct:
                print(f"  {'fałszywe NIE' if correct and no else ('wykryte' if no else 'NIEWYKRYTE')}: {item['case']} {generic} {value!r} -> {answer!r}", flush=True)

    good = [r for r in rows if r["poprawna"]]
    bad = [r for r in rows if not r["poprawna"]]
    summary = {"pytan": len(rows), "pol_poprawnych": len(good), "falszywe_nie": sum(says_no(r["odpowiedz"]) for r in good),
               "pol_blednych": len(bad), "wykryte": sum(says_no(r["odpowiedz"]) for r in bad),
               "mediana_s": round(statistics.median(times), 2) if times else None,
               "pytan_na_dokument": round(len(rows) / max(1, len(jobs)), 1), "watki": args.threads}
    by_field: dict[str, dict] = {}
    for r in rows:
        f = by_field.setdefault(r["pole"], {"poprawne": 0, "falszywe_nie": 0, "bledne": 0, "wykryte": 0})
        no = says_no(r["odpowiedz"])
        f["poprawne" if r["poprawna"] else "bledne"] += 1
        f["falszywe_nie" if r["poprawna"] else "wykryte"] += no
    summary["pola"] = by_field
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.report:
        args.report.write_text(json.dumps({"podsumowanie": summary, "wiersze": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
