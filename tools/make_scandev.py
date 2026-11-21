"""Scan-Dev: zamienia tekstowe PDF-y treningowe w „skany” bez warstwy tekstowej.

Każda strona: render 200 DPI w skali szarości, lekki obrót, szum, kompresja JPEG,
zapis jako PDF z samymi obrazami. Służy do testu ścieżki OCR (realny test to skany).

Użycie:
  python tools/make_scandev.py --manifest ../eval/manifest.json --split dev --cases 10 --out ../eval/scandev
"""
from __future__ import annotations

import argparse
import io
import json
import random
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter

SEED = 7


def degrade(img: Image.Image, rng: random.Random) -> Image.Image:
    img = img.rotate(rng.uniform(-1.5, 1.5), resample=Image.BICUBIC, expand=False, fillcolor=255)
    if rng.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.3, 0.8)))
    arr = np.asarray(img, dtype=np.float32)
    arr += np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(4, 12), arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=rng.randint(35, 70))
    return Image.open(io.BytesIO(buf.getvalue())).convert("L")


def to_scan(src: Path, dst: Path, rng: random.Random, dpi: int = 200) -> int:
    pdf = pdfium.PdfDocument(str(src))
    pages = [degrade(pdf[i].render(scale=dpi / 72).to_pil().convert("L"), rng) for i in range(len(pdf))]
    dst.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(dst, format="PDF", save_all=True, append_images=pages[1:], resolution=dpi)
    return len(pages)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--cases", type=int, default=10)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    rng = random.Random(SEED)
    manifest = [m for m in json.loads(args.manifest.read_text(encoding="utf-8")) if m["split"] == args.split]
    chosen = sorted(rng.sample(sorted({m["case"] for m in manifest}), args.cases))
    out_manifest = []
    for item in manifest:
        if item["case"] not in chosen:
            continue
        dst = args.out / "input" / item["case"] / Path(item["pdf"]).name
        n = to_scan(Path(item["pdf"]), dst, rng)
        out_manifest.append({**item, "pdf": str(dst.resolve()), "split": "scandev"})
        print(f"{item['case']}/{dst.name}: {n} str.")
    (args.out / "manifest.json").write_text(json.dumps(out_manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Scan-Dev: {len(out_manifest)} dokumentów z {len(chosen)} spraw -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
