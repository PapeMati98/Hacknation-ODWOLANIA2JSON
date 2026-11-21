"""Bramka wdrożenia czytelnika wizualnego (uchwała rady z 2026-11-21, punkt 7).

Buduje zestaw trudnych wycinków linii ze skanów, dla których znamy poprawną wartość (gold), i mierzy:
  - medianę czasu odczytu wycinka,
  - fałszywe weto: poprawna wartość odrzucona przez czytelnika,
  - fałszywe potwierdzenie i wykrycie: wartość zmieniona o jeden znak potwierdzona / zawetowana,
  - potwierdzenia przy czarnym prostokącie (ma być zero),
  - próg P udziału czarnych pikseli: czy oddziela linie z prostokątem od pogrubionych i podkreślonych.

  python tools/gate_visual.py --manifest ../eval/scandev/manifest.json --lines 12 --report gate.json
  python tools/gate_visual.py --manifest ... --dark-only        # sama kalibracja progu P (bez modelu)

Czytelnik jest domyślnie włączany tylko wtedy, gdy wynik to PASS.
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from odwolania2json import pdfio                                    # noqa: E402
from odwolania2json.textmatch import _compact, occurrences          # noqa: E402
from odwolania2json.validators import norm_date                     # noqa: E402
from odwolania2json.vision import DARK_SHARE, PROMPT, dark_share, judge, value_crop   # noqa: E402
from score import flatten                                           # noqa: E402

LIMITS = {"mediana_s": 6.0, "falszywe_weto": 0.05, "falszywe_potwierdzenie": 0.05, "wykrycie": 0.50}


def kind_of(value) -> str | None:
    """Rodzaj wartości z gold, o którą czytelnik bywa pytany: numer, data albo krótki tekst z cyframi."""
    if not isinstance(value, str):
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return "date"
    digits = re.sub(r"[\s\-]", "", value)
    if digits.isdigit() and len(digits) >= 9:
        return "krs"                                     # dowolny numer: porównanie pełnego fragmentu cyfr
    if len(value) <= 40 and sum(ch.isdigit() for ch in value) >= 2:
        return "text"
    return None


def find_line(doc, kind: str, value: str):
    for page in doc.pages:
        for line in page.lines:
            if kind == "date":
                if occurrences(value, line.text, norm_date):
                    return line
            elif _compact(value) and _compact(value) in _compact(line.text):
                return line
    return None


def wrong(kind: str, value: str) -> str:
    """Ta sama wartość ze zmienionym jednym znakiem (symulacja pomyłki OCR)."""
    if kind == "date":
        day = int(value[-2:])
        return value[:-2] + f"{day - 1 if day > 1 else day + 1:02d}"
    spots = [i for i, ch in enumerate(value) if ch.isdigit()]
    i = spots[len(spots) // 2]
    return value[:i] + str((int(value[i]) + 3) % 10) + value[i + 1:]


def variants(crop):
    """(nazwa, obraz, czy_z_czarnym_prostokątem) - trudne wersje jednego wycinka."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw
    yield "czysty", crop, False
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=35)
    yield "jpeg35", Image.open(io.BytesIO(buf.getvalue())).convert("RGB"), False
    yield "obrot3", crop.rotate(3, expand=True, fillcolor=(255, 255, 255)), False
    under = crop.copy()
    w, h = under.size
    ImageDraw.Draw(under).line([(int(0.03 * w), int(0.84 * h)), (int(0.97 * w), int(0.84 * h))], fill=(0, 0, 0), width=max(2, h // 22))
    yield "podkreslenie", under, False
    yield "pogrubienie", Image.fromarray(cv2.erode(np.asarray(crop), np.ones((3, 3), np.uint8))), False
    boxed = crop.copy()
    ImageDraw.Draw(boxed).rectangle([int(0.35 * w), int(0.12 * h), int(0.85 * w), int(0.88 * h)], fill=(0, 0, 0))
    yield "prostokat", boxed, True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, action="append", required=True)
    ap.add_argument("--lines", type=int, default=12, help="ile linii (każda w 6 wariantach)")
    ap.add_argument("--model", default=str(Path(__file__).resolve().parent.parent / "models" / "Qwen3.5-4B-Q4_K_M.gguf"))
    ap.add_argument("--mmproj", default=str(Path(__file__).resolve().parent.parent / "models" / "mmproj-F16.gguf"))
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0, help="inne ziarno = inny zestaw linii")
    ap.add_argument("--dark-only", action="store_true", help="tylko kalibracja progu czarnych pikseli, bez modelu")
    ap.add_argument("--save-crops", type=Path, help="zapisz wycinki do katalogu (do obejrzenia)")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    items = [it for m in args.manifest for it in json.loads(m.read_text(encoding="utf-8")) if it.get("gold")]
    rng = random.Random(args.seed)
    rng.shuffle(items)
    items.sort(key=lambda it: it.get("split") != "real")      # realny skan organizatora zawsze w zestawie
    samples, seen = [], set()
    for item in items:                                   # po jednej linii każdego rodzaju z dokumentu
        if len(samples) >= args.lines:
            break
        doc = pdfio.load(item["pdf"], max_pages=2)
        if not doc.is_scan:
            continue
        gold = json.loads(Path(item["gold"]).read_text(encoding="utf-8"))
        picked = set()
        for path, value in flatten(gold):
            kind = kind_of(value)
            if kind is None or kind in picked or (item["pdf"], value) in seen:
                continue
            line = find_line(doc, kind, value)
            if line is None or line.box is None:
                continue
            picked.add(kind)
            seen.add((item["pdf"], value))
            samples.append({"plik": item["pdf"], "pole": path, "rodzaj": kind, "wartosc": value, "linia": line.text,
                            "pewnosc_linii": round(line.conf, 3), "crop": value_crop(doc, line, kind, value)})
            if len(samples) >= args.lines:
                break
    print(f"linii: {len(samples)} | wycinków: {len(samples) * 6}", flush=True)

    reader = None
    if not args.dark_only:
        from odwolania2json.llm import LlamaCppBackend
        reader = LlamaCppBackend(args.model, args.threads)
        reader.enable_vision(args.mmproj)

    rows = []
    for n, sample in enumerate(samples):
        for name, image, boxed in variants(sample["crop"]):
            row = {k: v for k, v in sample.items() if k != "crop"} | {"wariant": name, "prostokat": boxed,
                                                                       "czarne": round(dark_share(image), 4)}
            if args.save_crops:
                args.save_crops.mkdir(parents=True, exist_ok=True)
                image.save(args.save_crops / f"{n:02d}_{name}.png")
            if reader is not None:
                t0 = time.perf_counter()
                read = reader.read_image(image, PROMPT)
                row.update(czas_s=round(time.perf_counter() - t0, 2), odczyt=read,
                           werdykt_poprawna=judge(sample["rodzaj"], sample["wartosc"], read),
                           werdykt_bledna=judge(sample["rodzaj"], wrong(sample["rodzaj"], sample["wartosc"]), read))
                print(f"  {n:02d} {name:12} {row['czas_s']:5.1f} s  poprawna={row['werdykt_poprawna']:11} "
                      f"błędna={row['werdykt_bledna']:11} {read!r}", flush=True)
            rows.append(row)

    plain = [r for r in rows if not r["prostokat"]]
    boxed = [r for r in rows if r["prostokat"]]
    lo, hi = max(r["czarne"] for r in plain), min(r["czarne"] for r in boxed)
    threshold = DARK_SHARE if lo < DARK_SHARE < hi else (round((lo + hi) / 2, 3) if lo < hi else None)
    summary = {"linii": len(samples), "wycinkow": len(rows), "wycinkow_z_prostokatem": len(boxed),
               "czarne_max_bez_prostokata": lo, "czarne_min_z_prostokatem": hi,
               "prog_P": threshold, "prog_P_domyslny_wystarcza": lo < DARK_SHARE < hi}
    print(f"czarne piksele: bez prostokąta max {lo:.1%}, z prostokątem min {hi:.1%} -> próg P = {threshold}")
    if reader is not None:
        limit = threshold if threshold is not None else DARK_SHARE
        asked = [r for r in plain if r["czarne"] <= limit]
        summary.update(
            mediana_s=round(statistics.median(r["czas_s"] for r in rows), 2),
            falszywe_weto=round(sum(r["werdykt_poprawna"] == "inne" for r in asked) / max(1, len(asked)), 4),
            falszywe_potwierdzenie=round(sum(r["werdykt_bledna"] == "zgodne" for r in asked) / max(1, len(asked)), 4),
            wykrycie=round(sum(r["werdykt_bledna"] == "inne" for r in asked) / max(1, len(asked)), 4),
            potwierdzenie_poprawnej=round(sum(r["werdykt_poprawna"] == "zgodne" for r in asked) / max(1, len(asked)), 4),
            potwierdzenia_przy_prostokacie=sum(r["werdykt_poprawna"] == "zgodne" and r["czarne"] <= limit for r in boxed),
            potwierdzenia_przy_prostokacie_bez_progu=sum(r["werdykt_poprawna"] == "zgodne" for r in boxed))
        ok = (summary["mediana_s"] <= LIMITS["mediana_s"] and summary["falszywe_weto"] <= LIMITS["falszywe_weto"]
              and summary["falszywe_potwierdzenie"] <= LIMITS["falszywe_potwierdzenie"]
              and summary["wykrycie"] >= LIMITS["wykrycie"] and summary["potwierdzenia_przy_prostokacie"] == 0
              and threshold is not None)
        summary["bramka"] = "PASS" if ok else "FAIL"
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.report:
        args.report.write_text(json.dumps({"podsumowanie": summary, "limity": LIMITS, "wycinki": rows}, ensure_ascii=False,
                                          indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
