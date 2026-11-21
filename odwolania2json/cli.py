"""Interfejs wiersza poleceń: input/<sprawa>/*.pdf -> output/<sprawa>/<nazwa>.json.

Dokument nierozpoznany jako żadna klasa (np. ogłoszenie TED) nie dostaje pliku JSON.
Ślad ekstrakcji (klasa, wyniki klasyfikacji, źródło i status każdego pola) trafia do
katalogu trace/, a nie do output/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import pdfio
from .config import load_classes
from .extract import Extractor, classify

APP_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="odwolania2json", description=__doc__)
    ap.add_argument("--input", type=Path, default=APP_ROOT / "input")
    ap.add_argument("--output", type=Path, default=APP_ROOT / "output")
    ap.add_argument("--trace", type=Path, default=APP_ROOT / "trace")
    ap.add_argument("--classes", type=Path, default=APP_ROOT / "configs" / "classes")
    ap.add_argument("--model", default=os.environ.get("O2J_MODEL", str(APP_ROOT / "models" / "Qwen3.5-4B-Q4_K_M.gguf")))
    ap.add_argument("--threads", type=int, default=int(os.environ.get("O2J_THREADS", max(4, (os.cpu_count() or 8) - 2))))
    ap.add_argument("--only", help="przetwórz tylko te sprawy (lista po przecinku)")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    classes = load_classes(args.classes)
    by_name = {c.name: c for c in classes}
    extractor = Extractor(args.model, n_threads=args.threads)
    only = set(args.only.split(",")) if args.only else None

    pdfs = sorted(p for p in args.input.rglob("*.pdf") if not only or p.parent.name in only)
    print(f"Dokumentów: {len(pdfs)} | klasy: {', '.join(by_name)} | model: {Path(args.model).name}")
    t_all = time.perf_counter()
    for pdf in pdfs:
        rel = pdf.relative_to(args.input).with_suffix(".json")
        t0 = time.perf_counter()
        doc = pdfio.load(str(pdf), max_pages=max(c.pages for c in classes))
        cls_name, scores = classify(doc, classes)
        record = {"plik": str(pdf), "skan": doc.is_scan, "klasa": cls_name, "punkty_klas": scores,
                  "nieczytelne_linie": sum(p.unreadable for p in doc.pages)}
        if cls_name is None:
            print(f"  {rel}: pominięty (dokument spoza klas) {scores}")
        else:
            data, trace = extractor.run(doc, by_name[cls_name])
            out_path = args.output / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            record["pola"] = trace
            flagged = sum(1 for t in trace if t["status"] in ("nieczytelne", "niezweryfikowane"))
            print(f"  {rel}: {cls_name} | {time.perf_counter() - t0:.1f} s | pola odrzucone: {flagged}")
        trace_path = args.trace / rel.with_suffix(".trace.json")
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"Gotowe: {len(pdfs)} dokumentów w {time.perf_counter() - t_all:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
