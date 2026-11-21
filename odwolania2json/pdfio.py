"""Wczytanie PDF: warstwa tekstowa, a gdy jej brak - OCR wieloskalowy z pewnością linii.

OCR (RapidOCR / PP-OCR ONNX, CPU):
  1. odczyt w skali bazowej,
  2. jeśli któraś linia ma pewność < LOW_CONF, cała strona jest czytana ponownie w skalach
     alternatywnych; dla każdej linii wybierany jest odczyt o najwyższej pewności
     (dopasowanie linii po pozycji w pionie),
  3. linie, które nadal mają niską pewność, są oznaczane jako nieczytelne i nie trafiają
     do tekstu przekazywanego modelowi jako fakt (zastępuje je znacznik [NIECZYTELNE]),
  Układ strony: linie są składane w wiersze (od lewej do prawej) i bloki; etykieta stojąca na marginesie
  obok bloku (np. "Odwołujący:" przy kilku liniach danych) trafia na początek tego bloku. Czarne
  prostokąty anonimizacji są wykrywane w obrazie i wstawiane do tekstu jako znacznik [ZAKRYTE].
  Strona jest renderowana tak, jakby była kartką A4 - skan zapisany w niższej rozdzielczości nie jest
  sztucznie powiększany.
  4. pierwszy odczyt alternatywny jest wykonywany zawsze i zapamiętywany w całości: to drugi,
     niezależny odczyt strony używany do kontroli krzyżowej wartości (extract.ocr_confirms);
     trzeci odczyt (kolejna rozdzielczość) jest robiony tylko wtedy, gdy dwa pierwsze się różnią.
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
REDACTED = "[ZAKRYTE]"
A4_LONG_INCH = 11.69         # dłuższy bok A4 w calach

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
    box: tuple[float, float, float, float] | None = None   # ramka linii (x0, y0, x1, y1), znormalizowana 0..1
    page: int = 0                                          # numer strony (od 1)


@dataclass
class Page:
    number: int
    source: str                     # "text" | "ocr"
    text: str
    lines: list[Line] = field(default_factory=list)
    unreadable: int = 0
    alt_reads: dict[int, str] = field(default_factory=dict)   # DPI -> pełny tekst odczytu alternatywnego
    redactions: list[tuple[float, float, float, float]] = field(default_factory=list)   # czarne prostokąty


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

    def crop(self, line: Line, dpi: int = BASE_DPI, margin: float = 0.35):
        """Wycinek strony z jedną linią tekstu (obraz PIL) - dla niezależnego czytelnika wizualnego."""
        if line.box is None or not line.page:
            return None
        from PIL import Image
        image = Image.fromarray(_render(pdfium.PdfDocument(self.path)[line.page - 1], dpi))
        w, h = image.size
        x0, y0, x1, y1 = line.box
        pad = margin * (y1 - y0) * h
        return image.crop((max(0, int(x0 * w - pad)), max(0, int(y0 * h - pad)),
                           min(w, int(x1 * w + pad)), min(h, int(y1 * h + pad))))

    def alt_text(self, dpi: int = ALT_DPIS[0]) -> str:
        """Niezależny odczyt OCR stron-skanów w podanej rozdzielczości (brakujący jest wykonywany na żądanie)."""
        missing = [p for p in self.pages if p.source == "ocr" and dpi not in p.alt_reads]
        if missing:
            pdf = pdfium.PdfDocument(self.path)
            for p in missing:
                p.alt_reads[dpi] = _lines_text(_ocr_lines(_render(pdf[p.number - 1], dpi)))
        return "\n".join(p.alt_reads[dpi] for p in self.pages if p.source == "ocr")


def _lines_text(lines: list[Line]) -> str:
    return "\n".join(l.text for l in sorted(lines, key=lambda l: l.y))


def _ocr_lines(img: np.ndarray) -> list[Line]:
    res = _engine()(img)
    h, w = img.shape[:2]
    lines = []
    for box, txt, conf in zip(res.boxes if res.boxes is not None else [], res.txts or [], res.scores or []):
        xs, ys = [pt[0] for pt in box], [pt[1] for pt in box]
        frame = (float(min(xs)) / w, float(min(ys)) / h, float(max(xs)) / w, float(max(ys)) / h)
        lines.append(Line(txt, float(conf), (min(ys) + max(ys)) / 2 / h, frame))
    return lines


def _render(page, dpi: int) -> np.ndarray:
    """Obraz strony w rozdzielczości `dpi` liczonej tak, jakby strona była kartką A4."""
    scale = dpi * A4_LONG_INCH / max(page.get_size())
    return np.array(page.render(scale=scale).to_pil().convert("RGB"))


def find_redactions(img: np.ndarray, line_height: float) -> list[tuple[float, float, float, float]]:
    """Czarne, pełne prostokąty (anonimizacja): ramki znormalizowane 0..1."""
    import cv2
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    count, _, stats, _ = cv2.connectedComponentsWithStats((gray < 60).astype(np.uint8), 8)
    height, width = gray.shape
    min_h = max(6.0, 0.4 * line_height * height)
    out = []
    for x, y, w, h, area in stats[1:count]:
        if h >= min_h and w >= 1.2 * h and area >= 0.85 * w * h and h <= 0.15 * height and w <= 0.95 * width:
            out.append((x / width, y / height, (x + w) / width, (y + h) / height))
    return out


def layout_text(lines: list[Line], redactions: list[tuple[float, float, float, float]]) -> str:
    """Tekst strony z zachowaniem układu: wiersze od lewej do prawej, bloki, etykiety z marginesu przed blokiem."""
    items = [(l.box or (0.0, l.y, 1.0, l.y), l.text if l.conf >= LOW_CONF else UNREADABLE) for l in lines]
    if not items:
        return ""
    heights = sorted(b[3] - b[1] for b, _ in items if b[3] > b[1])
    h = heights[len(heights) // 2] if heights else 0.012
    items += [(box, REDACTED) for box in redactions]
    items.sort(key=lambda it: (it[0][1] + it[0][3]) / 2)

    rows: list[list] = []                       # wiersz = elementy o zbliżonym środku w pionie
    for it in items:
        center = (it[0][1] + it[0][3]) / 2
        if rows and abs(center - sum((b[1] + b[3]) / 2 for b, _ in rows[-1]) / len(rows[-1])) <= 0.5 * h:
            rows[-1].append(it)
        else:
            rows.append([it])

    blocks: list[list[list]] = []               # blok = wiersze bez większego odstępu w pionie
    for row in rows:
        top = min(b[1] for b, _ in row)
        if blocks and top - max(b[3] for r in blocks[-1] for b, _ in r) <= 0.8 * h:
            blocks[-1].append(row)
        else:
            blocks.append([row])

    out = []
    for block in blocks:
        everything = [it for row in block for it in row]
        label = None
        if len(everything) >= 3:
            for it in sorted(everything, key=lambda it: it[0][0]):
                box, text = it
                others = [o for o in everything if o is not it]
                if text.rstrip().endswith(":") and len(text.split()) <= 3 and text != REDACTED and \
                        sum(box[2] <= o[0][0] + 0.005 for o in others) >= 0.8 * len(others):
                    label = it
                    break
        if label is not None and not (block[0] == [label]):
            block = [[label]] + [[it for it in row if it is not label] for row in block]
        for row in block:
            if not row:
                continue
            text = " ".join(t for _, t in sorted(row, key=lambda it: it[0][0]))
            while f"{REDACTED} {REDACTED}" in text:
                text = text.replace(f"{REDACTED} {REDACTED}", REDACTED)
            out.append(text)
        out.append("")
    return "\n".join(out).strip()


def ocr_page(page) -> tuple[list[Line], dict[int, str], list]:
    """Zwraca (linie odczytu głównego po scaleniu skal, teksty odczytów alternatywnych wg DPI, czarne prostokąty)."""
    image = _render(page, BASE_DPI)
    lines = _ocr_lines(image)
    heights = sorted(l.box[3] - l.box[1] for l in lines if l.box)
    redactions = find_redactions(image, heights[len(heights) // 2] if heights else 0.012)
    reads: dict[int, str] = {}
    for dpi in ALT_DPIS:
        alt = _ocr_lines(_render(page, dpi))
        reads[dpi] = _lines_text(alt)
        for i, line in enumerate(lines):
            if line.conf >= LOW_CONF:
                continue
            # najbliższa w pionie linia alternatywna (tolerancja ~ pół wysokości wiersza)
            best = min(alt, key=lambda a: abs(a.y - line.y), default=None)
            if best and abs(best.y - line.y) < 0.006 and best.conf > line.conf:
                lines[i] = best
        if all(l.conf >= LOW_CONF for l in lines):
            break
    for i, line in enumerate(lines):            # ostatnia próba: sama linia w innych powiększeniach
        if line.conf < LOW_CONF:
            lines[i] = _reread_line(image, line)
    return lines, reads, redactions


def _reread_line(image: np.ndarray, line: Line) -> Line:
    """Ponowny odczyt jednej linii z wycinka w kilku powiększeniach (pogrubienia i podkreślenia bywają
    czytelne tylko w określonej skali). Zwraca lepszy odczyt albo linię bez zmian."""
    import cv2
    if line.box is None:
        return line
    height, width = image.shape[:2]
    x0, y0, x1, y1 = line.box
    pad = 0.5 * (y1 - y0) * height
    crop = image[max(0, int(y0 * height - pad)): int(y1 * height + pad), max(0, int(x0 * width - pad)): int(x1 * width + pad)]
    best = line
    for zoom in (1.5, 2.0, 0.75):
        parts = _ocr_lines(cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC))
        if not parts:
            continue
        parts.sort(key=lambda p: p.box[0] if p.box else 0)
        conf = min(p.conf for p in parts)
        if conf > best.conf:
            best = Line(" ".join(p.text for p in parts), conf, line.y, line.box, line.page)
        if best.conf >= LOW_CONF:
            break
    return best


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
        lines, reads, redactions = ocr_page(pg)
        for line in lines:
            line.page = i + 1
        bad = sum(1 for l in lines if l.conf < LOW_CONF)
        pages.append(Page(i + 1, "ocr", layout_text(lines, redactions), lines, bad, reads, redactions))
    return Document(path, pages)
