"""Interfejs wiersza poleceń: input/<sprawa>/*.pdf -> output/<sprawa>/<nazwa>.json.

Dokument nierozpoznany jako żadna klasa (np. ogłoszenie TED) nie dostaje pliku JSON.
Ślad ekstrakcji (klasa, wyniki klasyfikacji, odpowiedź modelu, źródło i status każdego pola)
trafia do katalogu trace/, a nie do output/.
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
from .llm import make_backend

APP_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="odwolania2json", description=__doc__)
    ap.add_argument("--input", type=Path, default=APP_ROOT / "input")
    ap.add_argument("--output", type=Path, default=APP_ROOT / "output")
    ap.add_argument("--trace", type=Path, default=APP_ROOT / "trace")
    ap.add_argument("--classes", type=Path, default=APP_ROOT / "configs" / "classes")
    ap.add_argument("--model", default=os.environ.get("O2J_MODEL", str(APP_ROOT / "models" / "Qwen3.5-4B-Q4_K_M.gguf")))
    ap.add_argument("--threads", type=int, default=int(os.environ.get("O2J_THREADS", min(8, os.cpu_count() or 8))))
    ap.add_argument("--only", help="przetwórz tylko te sprawy (lista po przecinku)")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    classes = load_classes(args.classes)
    by_name = {c.name: c for c in classes}
    only = set(args.only.split(",")) if args.only else None
    pdfs = sorted(p for p in args.input.rglob("*.pdf") if not only or p.parent.name in only)
    print(f"Dokumentów: {len(pdfs)} | klasy: {', '.join(by_name)}", flush=True)
    t_all = time.perf_counter()

    # Etap 1: wczytanie (tekst lub OCR) i klasyfikacja wszystkich dokumentów.
    jobs = []
    max_pages = max(c.pages for c in classes)
    for pdf in pdfs:
        rel = pdf.relative_to(args.input).with_suffix(".json")
        t0 = time.perf_counter()
        doc = pdfio.load(str(pdf), max_pages=max_pages)
        cls_name, scores = classify(doc, classes)
        record = {"plik": str(pdf), "skan": doc.is_scan, "klasa": cls_name, "punkty_klas": scores,
                  "nieczytelne_linie": sum(p.unreadable for p in doc.pages),
                  "czas_wczytania_s": round(time.perf_counter() - t0, 2)}
        if cls_name is None:
            print(f"  {rel}: pominięty (dokument spoza klas) {scores}", flush=True)
            write_trace(args.trace, rel, record)
        else:
            jobs.append((cls_name, rel, doc, record))
    print(f"Wczytano i sklasyfikowano w {time.perf_counter() - t_all:.0f} s; do ekstrakcji: {len(jobs)}", flush=True)

    # Etap 2: ekstrakcja pogrupowana klasami - stała część promptu zostaje w cache modelu.
    extractor = Extractor(make_backend(args.model, args.threads))
    print(f"Model: {extractor.backend.name}", flush=True)
    for cls_name, rel, doc, record in sorted(jobs, key=lambda j: (j[0], str(j[1]))):
        t0 = time.perf_counter()
        data, trace, answer = extractor.run(doc, by_name[cls_name])
        out_path = args.output / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        record.update(pola=trace, odpowiedz_modelu=answer, czas_ekstrakcji_s=round(time.perf_counter() - t0, 2))
        write_trace(args.trace, rel, record)
        flagged = sum(1 for t in trace if t["status"] in ("nieczytelne", "niezweryfikowane"))
        print(f"  {rel}: {cls_name} | {time.perf_counter() - t0:.1f} s | pola odrzucone: {flagged}", flush=True)
    print(f"Gotowe: {len(pdfs)} dokumentów w {time.perf_counter() - t_all:.0f} s", flush=True)
    return 0


def write_trace(trace_dir: Path, rel: Path, record: dict) -> None:
    path = trace_dir / rel.with_suffix(".trace.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
