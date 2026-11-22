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
  sztucznie powiększany. Skan przekrzywiony (kartka położona krzywo na skanerze) jest prostowany
  rachunkowo: kąt bierzemy z ramek długich linii, a wiersze i bloki układamy we współrzędnych
  wyprostowanych - inaczej długie linie zachodzą w pionie na sąsiednie i tekst się miesza.
  4. odczyt alternatywny jest też drugim, niezależnym odczytem strony do kontroli krzyżowej wartości
     (extract.ocr_confirms). Każdy odczyt strony kosztuje tyle co pierwszy OCR, więc jest wykonywany
     na żądanie i zapamiętywany: dla 1. strony od razu przy wczytaniu, dla dalszych stron i kolejnej
     rozdzielczości dopiero wtedy, gdy wartości nie potwierdził odczyt już wykonany.
"""
from __future__ import annotations

import http.client
import json
import logging
import math
import os
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw

MIN_TEXT_CHARS = 80          # mniej znaków na stronie = strona traktowana jak skan
LOW_CONF = 0.80
BASE_DPI = 200
ALT_DPIS = (150, 250)
UNREADABLE = "[NIECZYTELNE]"
REDACTED = "[ZAKRYTE]"
A4_LONG_INCH = 11.69         # dłuższy bok A4 w calach

_ENGINE = None
_ENGINE_LOCK = threading.RLock()     # jeden odczyt OCR naraz w procesie
OCR_THREADS = 0                      # wątki silnika OCR w tym procesie; 0 = wszystkie rdzenie (jeden proces czyta sam)
OCR_CUDA = False                     # silnik OCR na karcie graficznej (usługa OCR na serwerze)


def _engine():
    global _ENGINE
    if _ENGINE is None:
        # Biblioteka sama ustawia swój dziennik na INFO (przy imporcie i przy tworzeniu silnika), więc zmiana
        # poziomu nie wystarcza: filtr przepuszcza tylko błędy, żeby komunikaty o plikach modeli nie zasłaniały
        # postępu przetwarzania.
        logging.getLogger("RapidOCR").addFilter(lambda record: record.levelno >= logging.ERROR)
        from rapidocr import RapidOCR
        # Kilka procesów czytających równolegle po jednym-dwóch wątkach daje większą przepustowość niż jeden
        # proces na wszystkich rdzeniach (rozpoznawanie krótkich linii słabo skaluje się z liczbą wątków).
        params: dict = {}
        if OCR_THREADS:
            params.update({"EngineConfig.onnxruntime.intra_op_num_threads": OCR_THREADS,
                           "EngineConfig.onnxruntime.inter_op_num_threads": 1})
        if OCR_CUDA:
            params["EngineConfig.onnxruntime.use_cuda"] = True
            # Linie mają różne szerokości: pełne przeszukiwanie algorytmów cuDNN dla każdego nowego kształtu
            # trwałoby dłużej niż sam odczyt.
            params["EngineConfig.onnxruntime.cuda_ep_cfg.cudnn_conv_algo_search"] = "DEFAULT"
        _ENGINE = RapidOCR(params=params or None)
    return _ENGINE


@dataclass
class Line:
    text: str
    conf: float
    y: float  # środek linii w pionie, znormalizowany 0..1
    box: tuple[float, float, float, float] | None = None   # ramka linii (x0, y0, x1, y1), znormalizowana 0..1
    page: int = 0                                          # numer strony (od 1)
    lay: tuple[float, float, float, float] | None = None   # ramka po wyprostowaniu strony - do układu tekstu
    angle: float = 0.0                                     # przekrzywienie strony (radiany)


@dataclass
class Page:
    number: int
    source: str                     # "text" | "ocr"
    text: str
    lines: list[Line] = field(default_factory=list)
    unreadable: int = 0
    alt_reads: dict[int, str] = field(default_factory=dict)   # DPI -> pełny tekst odczytu alternatywnego
    redactions: list[tuple[float, float, float, float]] = field(default_factory=list)   # czarne prostokąty
    rotation: int = 0               # o ile stopni obrócono obraz strony, żeby tekst stał prosto (0, 90, 180, 270)


@dataclass
class Document:
    path: str
    pages: list[Page]
    skipped: int = 0                # ile pustych stron z początku pliku pominięto (odwrócona kartka w podajniku)

    @property
    def is_scan(self) -> bool:
        return any(p.source == "ocr" for p in self.pages)

    def ensure_pages(self, count: int) -> None:
        """Doczytuje kolejne strony, aż dokument ma `count` pierwszych stron (albo wszystkie, jeśli jest krótszy).
        Klasa dokumentu jest znana po pierwszych stronach, a każda strona skanu kosztuje pełny OCR."""
        if count <= len(self.pages):
            return
        pdf = pdfium.PdfDocument(self.path)
        first = self.skipped + len(self.pages)
        self.pages += _read_pages(self.path, pdf, range(first, min(self.skipped + count, len(pdf))))

    def text(self, max_pages: int | None = None) -> str:
        pages = self.pages if max_pages is None else self.pages[:max_pages]
        return "\n\n".join(f"--- strona {p.number} ---\n{p.text}" for p in pages)

    def crop(self, line: Line, dpi: int = BASE_DPI, margin: float = 0.35, span: tuple[float, float] | None = None):
        """Wycinek strony z jedną linią tekstu (obraz PIL) - dla niezależnego czytelnika wizualnego.

        `span` zawęża wycinek do części szerokości linii (0..1), np. do okolicy jednej wartości.
        """
        if line.box is None or not line.page:
            return None
        from PIL import Image
        rotation = next((p.rotation for p in self.pages if p.number == line.page), 0)
        image = Image.fromarray(_render(pdfium.PdfDocument(self.path)[line.page - 1], dpi, rotation))
        w, h = image.size
        x0, y0, x1, y1 = line.box
        if span is not None:
            x0, x1 = x0 + span[0] * (x1 - x0), x0 + span[1] * (x1 - x0)
        pad = margin * (y1 - y0) * h
        return image.crop((max(0, int(x0 * w - pad)), max(0, int(y0 * h - pad)),
                           min(w, int(x1 * w + pad)), min(h, int(y1 * h + pad))))

    def alt_text(self, dpi: int = ALT_DPIS[0], pages: int | None = None) -> str:
        """Niezależny odczyt OCR stron-skanów w podanej rozdzielczości (brakujący jest wykonywany na żądanie).
        `pages` ogranicza odczyt do tylu pierwszych stron dokumentu."""
        chosen = [p for p in (self.pages if pages is None else self.pages[:pages]) if p.source == "ocr"]
        with _ENGINE_LOCK:
            missing = [p for p in chosen if dpi not in p.alt_reads]
            if missing:
                pdf = pdfium.PdfDocument(self.path)
                for p in missing:
                    p.alt_reads[dpi] = _lines_text(_ocr_lines(_render(pdf[p.number - 1], dpi, p.rotation)))
        return "\n".join(p.alt_reads[dpi] for p in chosen)


OCR_FIXES = [
    # „sp. z o.o.” z zerem zamiast litery „o” - pomyłka OCR, która psuje nazwę firmy
    (re.compile(r"(?i)\bz\s?(?:0\.\s?[o0]\.|o\.\s?0\.)"), "z o.o."),
    # litera wewnątrz ciągu cyfr („9994328o29”, „3o-799”) to cyfra odczytana jako litera
    (re.compile(r"(?<=\d)[oO](?=\d|-\d)"), "0"),
    (re.compile(r"(?<=\d)[lI](?=\d)"), "1"),
    # przecinek w adresie e-mail („a,wrobel@kancelaria.example”) to kropka - przecinka w adresie być nie może
    (re.compile(r"[\w.,+-]+@[\w.,-]+"), lambda m: re.sub(r"(?<=\w),(?=\w)", ".", m.group(0))),
]


def fix_ocr(text: str) -> str:
    for pattern, replacement in OCR_FIXES:
        text = pattern.sub(replacement, text)
    return text


def _lines_text(lines: list[Line]) -> str:
    return "\n".join(l.text for l in sorted(lines, key=lambda l: l.y))


def skew_angle(boxes, width: int) -> float:
    """Kąt przekrzywienia strony w radianach: mediana nachylenia górnych krawędzi długich linii."""
    angles = sorted(math.atan2(float(b[1][1]) - float(b[0][1]), float(b[1][0]) - float(b[0][0]))
                    for b in boxes if float(b[1][0]) - float(b[0][0]) > 0.25 * width)
    if len(angles) < 3:
        return 0.0
    angle = angles[len(angles) // 2]
    return angle if 0.003 < abs(angle) < 0.2 else 0.0          # poniżej ~0,2 stopnia nie ma czego prostować


def straighten(points, angle: float, width: int, height: int) -> tuple[float, float, float, float]:
    """Ramka (0..1) wielokąta po obróceniu strony o -angle wokół środka."""
    cx, cy, cos, sin = width / 2, height / 2, math.cos(angle), math.sin(angle)
    xs = [cx + (float(x) - cx) * cos + (float(y) - cy) * sin for x, y in points]
    ys = [cy - (float(x) - cx) * sin + (float(y) - cy) * cos for x, y in points]
    return min(xs) / width, min(ys) / height, max(xs) / width, max(ys) / height


def _ocr_lines(img: np.ndarray, with_angle: bool = False):
    with _ENGINE_LOCK:
        res = _engine()(img)
    h, w = img.shape[:2]
    boxes = list(res.boxes) if res.boxes is not None else []
    angle = skew_angle(boxes, w)
    lines = []
    for box, txt, conf in zip(boxes, res.txts or [], res.scores or []):
        xs, ys = [pt[0] for pt in box], [pt[1] for pt in box]
        frame = (float(min(xs)) / w, float(min(ys)) / h, float(max(xs)) / w, float(max(ys)) / h)
        lay = straighten(box, angle, w, h) if angle else frame
        lines.append(Line(fix_ocr(txt), float(conf), (lay[1] + lay[3]) / 2, frame, lay=lay, angle=angle))
    return (lines, angle) if with_angle else lines


def _render(page, dpi: int, rotation: int = 0) -> np.ndarray:
    """Obraz strony w rozdzielczości `dpi` liczonej tak, jakby strona była kartką A4."""
    scale = dpi * A4_LONG_INCH / max(page.get_size())
    return np.array(page.render(scale=scale, rotation=rotation).to_pil().convert("RGB"))


# Strona, na której niepewna jest większość linii, jest nieczytelna jako całość: ponowne czytanie każdej linii
# z osobna niczego nie odzyskuje, a zajmuje kilkanaście sekund na stronę (limit czasu całej partii).
MAX_LINE_REREADS = 12

ROTATE_CONF = 0.88     # średnia pewność odczytu, poniżej której sprawdzamy, czy strona nie leży do góry nogami
ROTATE_WIDE_CONF = 0.93    # ... albo średnia pewność najdłuższych linii strony (patrz _rotations_to_try)
ROTATE_GAIN = 1.1      # o tyle lepszy musi być odczyt strony obróconej, żeby go przyjąć (strona prosta po
                       # obróceniu daje 0,55-0,8 pierwotnej jakości, odwrócona - 1,2-2,8)
ROTATE_MIN_LINES = 3
ROTATE_SAMPLE = 12     # tyle najdłuższych linii strony bierzemy do oceny


def _quality(lines: list) -> float:
    """Ile czytelnego tekstu dał odczyt: znaki ważone pewnością linii."""
    return sum(l.conf * len(l.text) for l in lines if l.conf >= 0.6)


def _rotations_to_try(lines: list, width: int, height: int) -> tuple[int, ...]:
    """Podejrzenie złej orientacji strony na podstawie odczytu: wysokie, wąskie ramki linii oznaczają stronę
    leżącą bokiem, a niska pewność całej strony - być może stronę do góry nogami. Zwykła strona: brak prób."""
    if len(lines) < ROTATE_MIN_LINES:
        return ()
    tall = sum(1 for l in lines if l.box and (l.box[3] - l.box[1]) * height > 1.5 * (l.box[2] - l.box[0]) * width)
    if tall > len(lines) / 2:
        return (90, 270)
    if sum(l.conf for l in lines) / len(lines) < ROTATE_CONF:
        return (180,)
    # Silnik OCR sam odwraca krótkie linie, więc strona do góry nogami bywa czytana z wysoką średnią pewnością;
    # długie linie zdradzają ją zawsze: na stronie prostej czytają się najlepiej, na odwróconej najgorzej.
    wide = sorted((l for l in lines if l.box), key=lambda l: l.box[2] - l.box[0], reverse=True)[:ROTATE_SAMPLE]
    if wide and sum(l.conf for l in wide) / len(wide) < ROTATE_WIDE_CONF:
        return (180,)
    return ()


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
    items = [(l.lay or l.box or (0.0, l.y, 1.0, l.y), l.text if l.conf >= LOW_CONF else UNREADABLE) for l in lines]
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
        labels = []
        if len(everything) >= 3:
            for it in sorted(everything, key=lambda it: it[0][0]):
                box, text = it
                others = [o for o in everything if o is not it and not any(o is known for known in labels)]
                if text.rstrip().endswith(":") and len(text.split()) <= 3 and text != REDACTED and \
                        sum(box[2] <= o[0][0] + 0.005 for o in others) >= 0.8 * len(others):
                    labels.append(it)
        # Jedna etykieta obok bloku (wyśrodkowana w pionie) należy do całego bloku. Kilka etykiet w jednym
        # bloku stoi przy pierwszych liniach swoich części - zostają w swoich wierszach.
        label = labels[0] if len(labels) == 1 else None
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


def ocr_page(page, all_reads: bool = False) -> tuple[list[Line], dict[int, str], list]:
    """Zwraca (linie odczytu głównego po scaleniu skal, teksty odczytów alternatywnych wg DPI, czarne prostokąty)."""
    return ocr_page_rotated(page, all_reads)[:3]


def ocr_page_rotated(page, all_reads: bool = False) -> tuple[list[Line], dict[int, str], list, int]:
    """Jak `ocr_page`, a dodatkowo obrót strony (0, 90, 180, 270), przy którym tekst stoi prosto.

    Gdy strona ma linie niepewne, jest czytana ponownie w kolejnych rozdzielczościach, a linie, które nadal
    są niepewne - z wycinka samej linii. `all_reads` - od razu komplet odczytów alternatywnych (usługa OCR)."""
    image = _render(page, BASE_DPI)
    lines, angle = _ocr_lines(image, with_angle=True)
    rotation = 0
    turns = _rotations_to_try(lines, image.shape[1], image.shape[0])
    # Strona bokiem nie nadaje się do układu tekstu, więc wybieramy lepszy z dwóch obrotów; stronę podejrzaną
    # o odwrócenie zamieniamy tylko wtedy, gdy odwrócona daje wyraźnie więcej czytelnego tekstu.
    best = _quality(lines) * ROTATE_GAIN if turns == (180,) else -1.0
    for turn in turns:
        turned = _render(page, BASE_DPI, turn)
        turned_lines, turned_angle = _ocr_lines(turned, with_angle=True)
        if _quality(turned_lines) > best:
            best, rotation, image, lines, angle = _quality(turned_lines), turn, turned, turned_lines, turned_angle
    heights = sorted(l.lay[3] - l.lay[1] for l in lines if l.lay)
    redactions = find_redactions(image, heights[len(heights) // 2] if heights else 0.012)
    if angle:                                   # prostokąty w tych samych, wyprostowanych współrzędnych co linie
        height, width = image.shape[:2]
        redactions = [straighten([(x0 * width, y0 * height), (x1 * width, y0 * height), (x1 * width, y1 * height),
                                  (x0 * width, y1 * height)], angle, width, height) for x0, y0, x1, y1 in redactions]
    reads: dict[int, str] = {}
    for dpi in ALT_DPIS:
        if all(l.conf >= LOW_CONF for l in lines):
            break                               # wszystkie linie pewne: kolejny odczyt tylko na żądanie
        alt = _ocr_lines(_render(page, dpi, rotation))
        reads[dpi] = _lines_text(alt)
        for i, line in enumerate(lines):
            if line.conf >= LOW_CONF:
                continue
            # najbliższa w pionie linia alternatywna (tolerancja ~ pół wysokości wiersza)
            best = min(alt, key=lambda a: abs(a.y - line.y), default=None)
            if best and abs(best.y - line.y) < 0.006 and best.conf > line.conf:
                lines[i] = best
    budget = MAX_LINE_REREADS
    for i, line in enumerate(lines):            # ostatnia próba: sama linia w innych powiększeniach
        if line.conf < LOW_CONF and budget > 0:
            lines[i] = _reread_line(image, line)
            budget -= 1
    if all_reads:
        for dpi in ALT_DPIS:
            if dpi not in reads:
                reads[dpi] = _lines_text(_ocr_lines(_render(page, dpi, rotation)))
    return lines, reads, redactions, rotation


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
    if line.angle and line.lay and crop.size:
        # Ramka przekrzywionej linii obejmuje kawałki sąsiednich linii: prostujemy wycinek i zostawiamy
        # tylko pas o wysokości samej linii.
        ch, cw = crop.shape[:2]
        turn = cv2.getRotationMatrix2D((cw / 2, ch / 2), math.degrees(line.angle), 1.0)
        crop = cv2.warpAffine(crop, turn, (cw, ch), borderValue=(255, 255, 255))
        band = (line.lay[3] - line.lay[1]) * height
        crop = crop[max(0, int(ch / 2 - band)): int(ch / 2 + band)]
    best = line
    for zoom in (1.5, 2.0, 0.75):
        parts = _ocr_lines(cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC))
        if not parts:
            continue
        parts.sort(key=lambda p: p.box[0] if p.box else 0)
        conf = min(p.conf for p in parts)
        if conf > best.conf:
            best = Line(fix_ocr(" ".join(p.text for p in parts)), conf, line.y, line.box, line.page, line.lay, line.angle)
        if best.conf >= LOW_CONF:
            break
    return best


def load(path: str, max_pages: int | None = None) -> Document:
    pdf = pdfium.PdfDocument(path)
    pages = []
    n = len(pdf) if max_pages is None else min(max_pages, len(pdf))
    doc = Document(path, _read_pages(path, pdf, range(n)))
    # Pusta strona na początku skanu (odwrócona kartka, okładka): dokument zaczyna się od pierwszej strony z treścią.
    while (doc.pages and doc.skipped < MAX_BLANK_SKIP and _blank(doc.pages[0])
           and (len(doc.pages) > 1 or doc.skipped + len(doc.pages) < len(pdf))):
        doc.pages.pop(0)
        doc.skipped += 1
        doc.pages += _read_pages(path, pdf, range(doc.skipped + len(doc.pages), min(doc.skipped + n, len(pdf))))
    return doc


MAX_BLANK_SKIP = 3


def _blank(page: Page) -> bool:
    """Strona skanu bez treści: OCR nie znalazł na niej nawet 20 znaków."""
    return page.source == "ocr" and sum(len(l.text) for l in page.lines) < 20


_POLISH = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
_PUNCT = set(".,;:()[]{}-–—/\\\"'„”«»’%@&§+°*·•_=#!?<>|~^`$€£№…‚")
_VOWELS = set("aeiouyąęóAEIOUYĄĘÓ")


def text_layer_ok(text: str, page_is_image: bool = False) -> bool:
    """Czy warstwa tekstowa strony nadaje się do użycia. Odrzucamy tekst, który nie wygląda jak pismo:
    obce znaki zamiast liter (zepsute kodowanie fontu), „słowa” bez samogłosek i z przypadkową wielkością liter
    (śmieci po OCR skanera), a na stronie będącej obrazem - także długi tekst bez ani jednego polskiego znaku
    (słaby OCR skanera). Taka strona jest czytana własnym OCR."""
    chars = [c for c in text if not c.isspace()]
    if len(chars) < MIN_TEXT_CHARS:
        return True
    known = sum(1 for c in chars if c.isdigit() or c in _PUNCT or (c.isalpha() and ord(c) < 0x250))
    if known / len(chars) < 0.85:
        return False
    words = re.findall(r"[^\W\d_]{3,}", text)
    if len(words) >= 10:
        plain = sum(1 for w in words if _VOWELS & set(w) and (w.islower() or w.isupper() or w.istitle()))
        if plain / len(words) < 0.6:
            return False
    letters = sum(1 for c in chars if c.isalpha())
    if page_is_image and letters >= 300 and not _POLISH & set(chars):
        return False
    return True


def _is_page_image(page) -> bool:
    """Strona jest skanem: jeden obraz zajmuje co najmniej 70% jej powierzchni (tekst to tylko dodana warstwa)."""
    try:
        width, height = page.get_size()
        for obj in page.get_objects(filter=[pdfium_raw.FPDF_PAGEOBJ_IMAGE], max_depth=1):
            left, bottom, right, top = obj.get_bounds()
            if (right - left) * (top - bottom) >= 0.7 * width * height:
                return True
    except Exception:       # nietypowa budowa strony: traktujemy ją jak zwykły PDF tekstowy
        return False
    return False


def _read_pages(path: str, pdf, indices) -> list[Page]:
    """Strony o podanych indeksach: warstwa tekstowa, a gdy jej brak - OCR (usługa po API albo silnik lokalny)."""
    pages: dict[int, Page] = {}
    scans = []
    for i in indices:
        text = pdf[i].get_textpage().get_text_range().replace("\r\n", "\n").strip()
        if len(text) >= MIN_TEXT_CHARS and text_layer_ok(text, _is_page_image(pdf[i])):
            pages[i] = Page(i + 1, "text", text)
        else:
            scans.append(i)
    remote = remote_ocr(path, scans) if scans and os.environ.get("O2J_OCR_BASE") else None
    for i in scans:
        lines, reads, redactions, rotation = (*remote[i], 0) if remote else ocr_page_rotated(pdf[i])
        for line in lines:
            line.page = i + 1
        bad = sum(1 for l in lines if l.conf < LOW_CONF)
        pages[i] = Page(i + 1, "ocr", layout_text(lines, redactions), lines, bad, reads, redactions, rotation)
    return [pages[i] for i in indices]


_REMOTE_WARNED = False


def remote_ocr(path: str, indices: list[int]) -> dict[int, tuple] | None:
    """OCR stron przez usługę po API (odwolania2json.ocr_server): ten sam kod odczytu co lokalnie, tylko na
    serwerze. Zwraca {indeks strony: (linie, odczyty alternatywne, czarne prostokąty)} albo None, gdy usługa
    nie odpowiada - wtedy strony czyta silnik lokalny (wolniej, wynik ten sam)."""
    global _REMOTE_WARNED
    base = urllib.parse.urlsplit(os.environ["O2J_OCR_BASE"].rstrip("/"))
    key = os.environ.get("O2J_OCR_KEY") or os.environ.get("O2J_API_KEY")
    headers = {"Content-Type": "application/pdf"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    with open(path, "rb") as fh:
        body = fh.read()
    error: Exception | None = None
    for attempt in range(3):
        factory = http.client.HTTPSConnection if base.scheme == "https" else http.client.HTTPConnection
        conn = factory(base.netloc, timeout=180)
        try:
            conn.request("POST", f"{base.path}/ocr?pages={','.join(map(str, indices))}", body=body, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
            if resp.status == 200:
                out = {}
                for index, page in json.loads(payload)["pages"].items():
                    lines = [Line(text, conf, y, tuple(box) if box else None, 0, tuple(lay) if lay else None, angle)
                             for text, conf, y, box, lay, angle in page["lines"]]
                    out[int(index)] = (lines, {int(dpi): text for dpi, text in page["reads"].items()},
                                       [tuple(r) for r in page["redactions"]])
                if all(i in out for i in indices):
                    return out
                error = RuntimeError("odpowiedź bez wszystkich stron")
            else:
                error = RuntimeError(f"HTTP {resp.status}: {payload[:200]!r}")
                if resp.status < 500 and resp.status != 429:
                    break
        except (OSError, http.client.HTTPException, ValueError, KeyError) as exc:
            error = exc
        finally:
            conn.close()
        time.sleep(1.5 * (attempt + 1))
    if not _REMOTE_WARNED:
        _REMOTE_WARNED = True
        print(f"UWAGA: usługa OCR nie odpowiada ({error}) - skany czyta silnik lokalny (wolniej).", flush=True)
    return None
