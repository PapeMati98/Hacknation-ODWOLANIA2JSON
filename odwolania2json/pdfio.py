"""Wczytanie PDF: warstwa tekstowa, a gdy jej brak - OCR wieloskalowy z pewnością linii.

OCR (RapidOCR / PP-OCR ONNX, CPU):
  1. odczyt w skali bazowej,
  2. jeśli któraś linia ma pewność < LOW_CONF, cała strona jest czytana ponownie w skalach
     alternatywnych; dla każdej linii wybierany jest odczyt o najwyższej pewności
     (dopasowanie linii po pozycji w pionie),
  3. linie, które nadal mają niską pewność, są oznaczane jako nieczytelne i nie trafiają
     do tekstu przekazywanego modelowi jako fakt (zastępuje je znacznik [NIECZYTELNE]).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pypdfium2 as pdfium

MIN_TEXT_CHARS = 80          # mniej znaków na stronie = strona traktowana jak skan
LOW_CONF = 0.80
BASE_DPI = 200
ALT_DPIS = (150, 250)
UNREADABLE = "[NIECZYTELNE]"

_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        from rapidocr import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


@dataclass
class Line:
    text: str
    conf: float
    y: float  # środek linii w pionie, znormalizowany 0..1


@dataclass
class Page:
    number: int
    source: str                     # "text" | "ocr"
    text: str
    lines: list[Line] = field(default_factory=list)
    unreadable: int = 0


@dataclass
class Document:
    path: str
    pages: list[Page]

    @property
    def is_scan(self) -> bool:
        return any(p.source == "ocr" for p in self.pages)

    def text(self, max_pages: int | None = None) -> str:
        pages = self.pages if max_pages is None else self.pages[:max_pages]
        return "\n\n".join(f"--- strona {p.number} ---\n{p.text}" for p in pages)


def _ocr_lines(img: np.ndarray) -> list[Line]:
    res = _engine()(img)
    h = img.shape[0]
    lines = []
    for box, txt, conf in zip(res.boxes if res.boxes is not None else [], res.txts or [], res.scores or []):
        ys = [pt[1] for pt in box]
        lines.append(Line(txt, float(conf), (min(ys) + max(ys)) / 2 / h))
    return lines


def _render(page, dpi: int) -> np.ndarray:
    return np.array(page.render(scale=dpi / 72).to_pil().convert("RGB"))


def ocr_page(page) -> list[Line]:
    lines = _ocr_lines(_render(page, BASE_DPI))
    if all(l.conf >= LOW_CONF for l in lines):
        return lines
    for dpi in ALT_DPIS:
        alt = _ocr_lines(_render(page, dpi))
        for i, line in enumerate(lines):
            if line.conf >= LOW_CONF:
                continue
            # najbliższa w pionie linia alternatywna (tolerancja ~ pół wysokości wiersza)
            best = min(alt, key=lambda a: abs(a.y - line.y), default=None)
            if best and abs(best.y - line.y) < 0.006 and best.conf > line.conf:
                lines[i] = best
        if all(l.conf >= LOW_CONF for l in lines):
            break
    return lines


def load(path: str, max_pages: int | None = None) -> Document:
    pdf = pdfium.PdfDocument(path)
    pages = []
    n = len(pdf) if max_pages is None else min(max_pages, len(pdf))
    for i in range(n):
        pg = pdf[i]
        text = pg.get_textpage().get_text_range().replace("\r\n", "\n").strip()
        if len(text) >= MIN_TEXT_CHARS:
            pages.append(Page(i + 1, "text", text))
            continue
        lines = ocr_page(pg)
        bad = sum(1 for l in lines if l.conf < LOW_CONF)
        body = "\n".join(l.text if l.conf >= LOW_CONF else UNREADABLE for l in sorted(lines, key=lambda l: l.y))
        pages.append(Page(i + 1, "ocr", body, lines, bad))
    return Document(path, pages)
