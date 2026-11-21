"""Benchmark OCR na CPU: czas na stronę i trafienie identyfikatorów.

Dla każdego dokumentu Scan-Dev renderuje pierwsze strony, uruchamia OCR i sprawdza,
czy wartości z gold (NIP, REGON, KRS, rachunki, BZP, TED, PESEL, kwoty, daty) występują
w odczytanym tekście po usunięciu spacji. To mierzy jakość cyfr, od której zależy F1.

Użycie:
  python tools/bench_ocr.py --manifest ../eval/scandev/manifest.json --dpi 200 --pages 3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium

ID_KEYS = {"nip", "regon", "krs", "pesel", "na_rachunek", "z_rachunku", "numer_bzp", "numer_ted",
           "numer_postepowania", "numer_transakcji"}


def gold_ids(obj, out: list[str]) -> list[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ID_KEYS and v not in (None, ""):
                out.append(str(v))
            else:
                gold_ids(v, out)
    elif isinstance(obj, list):
        for v in obj:
            gold_ids(v, out)
    return out


def squash(text: str) -> str:
    return re.sub(r"[\s\-]", "", text).upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--extra-pdf", action="append", default=[], help="dodatkowy PDF tylko do pomiaru czasu")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    from rapidocr import RapidOCR
    engine = RapidOCR()

    items = json.loads(args.manifest.read_text(encoding="utf-8"))
    hit = total = pages_done = 0
    t_ocr = 0.0
    misses: list[str] = []
    for item in items:
        pdf = pdfium.PdfDocument(item["pdf"])
        text_parts = []
        for i in range(min(args.pages, len(pdf))):
            img = np.array(pdf[i].render(scale=args.dpi / 72).to_pil().convert("RGB"))
            t0 = time.perf_counter()
            res = engine(img)
            t_ocr += time.perf_counter() - t0
            pages_done += 1
            text_parts.append(" ".join(res.txts or []))
        text = squash(" ".join(text_parts))
        ids = gold_ids(json.loads(Path(item["gold"]).read_text(encoding="utf-8")), [])
        for v in ids:
            total += 1
            if squash(v) in text:
                hit += 1
            else:
                misses.append(f"{item['case']}/{Path(item['pdf']).name}: {v}")
    print(f"strony: {pages_done} | śr. czas OCR: {t_ocr / max(pages_done, 1):.2f} s/str. | identyfikatory trafione: {hit}/{total} = {hit / max(total, 1):.3f}")
    for m in misses[:25]:
        print("  BRAK", m)
    for extra in args.extra_pdf:
        pdf = pdfium.PdfDocument(extra)
        t0 = time.perf_counter()
        txt = []
        for i in range(min(args.pages, len(pdf))):
            res = engine(np.array(pdf[i].render(scale=args.dpi / 72).to_pil().convert("RGB")))
            txt.append("\n".join(res.txts or []))
        print(f"\n== {Path(extra).name}: {(time.perf_counter() - t0) / min(args.pages, len(pdf)):.2f} s/str.\n{txt[0][:1500]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
