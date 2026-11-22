"""Test odporności na budowę pliku, nie na jakość obrazu.

Warianty (każdy zachowuje ścieżkę względną pliku, więc ocenia je ten sam manifest):
  blank-first       pusta strona przed dokumentem (odwrócona kartka w podajniku)
  junk-first        strona innego pisma przed dokumentem (załącznik spięty na wierzchu)
  textlayer-garbage skan z warstwą tekstową złożoną ze śmieci (zepsuty OCR skanera)
  textlayer-ascii   skan z warstwą tekstową bez polskich znaków i z pomyłkami 0/O, 1/l (słaby OCR skanera)

Użycie:
  python tools/stress_structure.py --input ../dane/.../skany --out ../eval/stress/struktura/blank-first --mode blank-first
"""
from __future__ import annotations

import argparse
import ctypes
import io
import sys
import unicodedata
import zlib
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as raw
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DPI = 200


def page_images(path: Path, max_pages: int) -> list[Image.Image]:
    pdf = pdfium.PdfDocument(str(path))
    return [pdf[i].render(scale=DPI / 72).to_pil().convert("L") for i in range(min(len(pdf), max_pages))]


def save_images(pages: list[Image.Image], dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:], resolution=DPI, quality=85)
    dst.write_bytes(buf.getvalue())


def blank_page(size, rng) -> Image.Image:
    arr = np.clip(248 + rng.normal(0, 4, (size[1], size[0])), 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def spoil(text: str, rng) -> str:
    """Tekst taki, jaki zostawia słaby OCR skanera: bez znaków diakrytycznych, z pomyłkami podobnych znaków."""
    text = text.replace("ł", "l").replace("Ł", "L")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    swaps = {"0": "O", "O": "0", "1": "l", "l": "1", "5": "S", "8": "B", "rn": "m"}
    out = []
    for ch in text:
        out.append(swaps[ch] if ch in swaps and rng.random() < 0.04 else ch)
    return "".join(out).encode("ascii", "replace").decode("ascii")


def garbage(rng, lines: int = 40) -> str:
    alphabet = np.array(list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,;:-/|!~^' "))
    return "\n".join("".join(rng.choice(alphabet, int(rng.integers(30, 80)))) for _ in range(lines))


def add_text_layer(src_images: list[Image.Image], texts: list[str], dst: Path) -> None:
    """PDF: obraz strony + drobny tekst (jak warstwa OCR w „przeszukiwalnym” skanie)."""
    buf = io.BytesIO()
    src_images[0].save(buf, format="PDF", save_all=True, append_images=src_images[1:], resolution=DPI, quality=85)
    pdf = pdfium.PdfDocument(buf.getvalue())
    for i, text in enumerate(texts):
        page = pdf[i]
        height = page.get_height()
        for n, line in enumerate(text.splitlines()[:110]):
            if not line.strip():
                continue
            obj = raw.FPDFPageObj_NewTextObj(pdf.raw, b"Helvetica", 6.0)
            data = (line[:160] + "\x00").encode("utf-16-le")
            raw.FPDFText_SetText(obj, ctypes.cast(ctypes.create_string_buffer(data), raw.FPDF_WIDESTRING))
            # Warstwa OCR skanera jest niewidoczna: obraz strony zostaje nietknięty.
            raw.FPDFTextObj_SetTextRenderMode(obj, raw.FPDF_TEXTRENDERMODE_INVISIBLE)
            raw.FPDFPageObj_Transform(obj, 1, 0, 0, 1, 40.0, float(height - 40 - 7 * n))
            raw.FPDFPage_InsertObject(page.raw, obj)
        raw.FPDFPage_GenerateContent(page.raw)
    dst.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(str(dst))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mode", required=True, choices=("blank-first", "junk-first", "textlayer-garbage", "textlayer-ascii"))
    ap.add_argument("--junk", type=Path, help="PDF, którego pierwsza strona trafia na początek (junk-first)")
    ap.add_argument("--max-pages", type=int, default=2)
    ap.add_argument("--only", help="tylko pliki, których ścieżka zawiera jeden z fragmentów (po przecinku)")
    args = ap.parse_args()
    only = [s for s in (args.only or "").split(",") if s]
    junk = page_images(args.junk, 1)[0] if args.junk else None
    count = 0
    for src in sorted(args.input.rglob("*.pdf")):
        rel = src.relative_to(args.input)
        if only and not any(s in rel.as_posix() for s in only):
            continue
        rng = np.random.default_rng(zlib.crc32(f"{rel.as_posix()}|{args.mode}".encode("utf-8")))
        pages = page_images(src, args.max_pages)
        if args.mode == "blank-first":
            save_images([blank_page(pages[0].size, rng)] + pages, args.out / rel)
        elif args.mode == "junk-first":
            if junk is None:
                ap.error("junk-first wymaga --junk")
            save_images([junk.resize(pages[0].size)] + pages, args.out / rel)
        elif args.mode == "textlayer-garbage":
            add_text_layer(pages, [garbage(rng) for _ in pages], args.out / rel)
        else:
            from odwolania2json import pdfio
            doc = pdfio.load(str(src), max_pages=args.max_pages)
            add_text_layer(pages, [spoil(p.text, rng) for p in doc.pages[:len(pages)]], args.out / rel)
        count += 1
    print(f"{args.mode}: {count} dokumentów -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
