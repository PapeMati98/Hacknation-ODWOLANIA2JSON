"""Okładka projektu „JSON, ja tu tylko parsuję” (800×600) do HackTribe.

Styl instytucjonalny: białe tło, akcenty w gradiencie kolorów Synaptivo
(#3a90df → #7364df → #ac38df) i granatowy tekst (#0f1637).

Uruchomienie: python generuj_okladke.py  ->  okladka.pdf, okladka.png, okladka@2x.png
Wymaga: reportlab, pypdfium2. Fonty Arial i Courier New z macOS.
"""
from pathlib import Path

import pypdfium2
from reportlab.lib.colors import Color, HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

TU = Path(__file__).parent
F = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("Arial", F + "Arial.ttf"))
pdfmetrics.registerFont(TTFont("ArialB", F + "Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("ArialBlack", F + "Arial Black.ttf"))
pdfmetrics.registerFont(TTFont("Mono", F + "Courier New Bold.ttf"))

W, H = 800, 600
NAVY = HexColor("#0f1637")
BLUE, INDIGO, VIOLET = HexColor("#3a90df"), HexColor("#7364df"), HexColor("#ac38df")
BRAND = [BLUE, INDIGO, VIOLET]
WHITE = HexColor("#ffffff")
SOFT = HexColor("#f5f6fb")
LINE = HexColor("#d5d9e6")
MUTED = HexColor("#5c6283")
LABEL = HexColor("#4a5075")

c = canvas.Canvas(str(TU / "okladka.pdf"), pagesize=(W, H))


def gradient(path, x0, x1, colors=BRAND, y0=0, y1=0):
    """Wypełnia ścieżkę gradientem (domyślnie poziomym)."""
    c.saveState(); c.clipPath(path, stroke=0, fill=0)
    c.linearGradient(x0, y0, x1, y1, colors, extend=True)
    c.restoreState()


def ramka(x, y, w, h, r, grub, wnetrze=WHITE):
    """Zaokrąglony prostokąt z obramowaniem w gradiencie marki."""
    p = c.beginPath(); p.roundRect(x, y, w, h, r); gradient(p, x, x + w)
    c.setFillColor(wnetrze); c.roundRect(x + grub, y + grub, w - 2 * grub, h - 2 * grub, max(r - grub, 0), stroke=0, fill=1)


# ---- tło: białe, cienka ramka w gradiencie, pasek u góry ----
c.setFillColor(WHITE); c.rect(0, 0, W, H, stroke=0, fill=1)
ramka(14, 14, W - 28, H - 28, 10, 2)
c.saveState(); q = c.beginPath(); q.roundRect(14, 14, W - 28, H - 28, 10); c.clipPath(q, stroke=0, fill=0)
p = c.beginPath(); p.rect(14, H - 22, W - 28, 8); gradient(p, 14, W - 14)
c.restoreState()

# ---- układ środkowy: dokument → strzałka → JSON, wyśrodkowany ----
dw, gap, aw, jw, h = 180, 28, 74, 306, 236
x0 = (W - (dw + gap + aw + gap + jw)) / 2
y0 = 250

# dokument PDF
dx, dy, fold = x0, y0, 40
p = c.beginPath()
p.moveTo(dx, dy); p.lineTo(dx + dw, dy); p.lineTo(dx + dw, dy + h - fold)
p.lineTo(dx + dw - fold, dy + h); p.lineTo(dx, dy + h); p.close()
gradient(p, dx, dx + dw)
g = 2.5
p = c.beginPath()
p.moveTo(dx + g, dy + g); p.lineTo(dx + dw - g, dy + g); p.lineTo(dx + dw - g, dy + h - fold - g * 0.4)
p.lineTo(dx + dw - fold - g * 0.4, dy + h - g); p.lineTo(dx + g, dy + h - g); p.close()
c.setFillColor(SOFT); c.drawPath(p, stroke=0, fill=1)
p = c.beginPath()
p.moveTo(dx + dw - fold, dy + h); p.lineTo(dx + dw - fold, dy + h - fold); p.lineTo(dx + dw, dy + h - fold); p.close()
gradient(p, dx + dw - fold, dx + dw, [INDIGO, VIOLET])
# etykieta PDF
p = c.beginPath(); p.roundRect(dx + 18, dy + h - 62, 66, 28, 6); gradient(p, dx + 18, dx + 84)
c.setFillColor(WHITE); c.setFont("ArialBlack", 16); c.drawCentredString(dx + 51, dy + h - 55, "PDF")
# wiersze tekstu; odczytane pola podświetlone
rows = [0.82, 0.60, ("hl", 0.88), 0.52, ("hl", 0.70), 0.84, 0.46]
yy = dy + h - 92
for r in rows:
    if isinstance(r, tuple):
        frac = r[1]
        c.setFillColor(Color(0.45, 0.39, 0.87, alpha=0.13)); c.roundRect(dx + 14, yy - 6, (dw - 28) * frac + 8, 17, 4, stroke=0, fill=1)
        p = c.beginPath(); p.roundRect(dx + 18, yy, (dw - 36) * frac, 5, 2.5); gradient(p, dx + 18, dx + 18 + (dw - 36) * frac)
    else:
        c.setFillColor(LINE); c.roundRect(dx + 18, yy, (dw - 36) * r, 5, 2.5, stroke=0, fill=1)
    yy -= 20
# pieczątka „KIO” – nawiązanie do skanów
c.saveState(); c.translate(dx + dw - 44, dy + 34); c.rotate(-14)
c.setStrokeColor(INDIGO); c.setLineWidth(2); c.circle(0, 0, 21, stroke=1, fill=0)
c.setFillColor(INDIGO); c.setFont("ArialB", 11); c.drawCentredString(0, -4, "KIO")
c.restoreState()

# strzałka
ax, ay = x0 + dw + gap, y0 + h / 2
p = c.beginPath()
p.moveTo(ax, ay - 4); p.lineTo(ax + aw - 26, ay - 4); p.lineTo(ax + aw - 26, ay - 16); p.lineTo(ax + aw, ay)
p.lineTo(ax + aw - 26, ay + 16); p.lineTo(ax + aw - 26, ay + 4); p.lineTo(ax, ay + 4); p.close()
gradient(p, ax, ax + aw)

# panel JSON: biały, obramowanie w gradiencie
jx = ax + aw + gap
ramka(jx, y0, jw, h, 14, 2.5)
c.setFont("Mono", 54)
c.setFillColor(BLUE); c.drawString(jx + 16, y0 + h - 60, "{")
c.setFillColor(VIOLET); c.drawRightString(jx + jw - 16, y0 + 16, "}")
lines = [
    ('"odwolujacy"', ': {…},'),
    ('"nip"', ': "9990…",'),
    ('"data"', ': "2026-11-22",'),
    ('"kwota"', ': 20000.0,'),
    ('"do_sprawdzenia"', ': null'),
]
c.setFont("Mono", 15.5)
ly = y0 + h - 88
for k, v in lines:
    c.setFillColor(INDIGO); c.drawString(jx + 40, ly, k)
    c.setFillColor(NAVY); c.drawString(jx + 40 + pdfmetrics.stringWidth(k, "Mono", 15.5), ly, v)
    ly -= 26

# ---- podpis, wyśrodkowany ----
c.setFillColor(NAVY); c.setFont("ArialBlack", 38)
c.drawCentredString(W / 2, 160, "JSON, ja tu tylko parsuję")
p = c.beginPath(); p.roundRect(W / 2 - 70, 141, 140, 4, 2); gradient(p, W / 2 - 70, W / 2 + 70)
c.setFillColor(LABEL); c.setFont("ArialB", 18)
c.drawCentredString(W / 2, 108, "Dokumenty spraw KIO  →  dane JSON dla UZP")
c.setFillColor(INDIGO); c.setFont("ArialB", 16)
c.drawCentredString(W / 2, 74, "Drużyna „Nie wiem, ale wygeneruję”")
c.setFillColor(MUTED); c.setFont("Arial", 13)
c.drawCentredString(W / 2, 44, "HackNation 2026  ·  Urząd Zamówień Publicznych  ·  Odwołania2JSON")
c.save()

pdf = pypdfium2.PdfDocument(str(TU / "okladka.pdf"))
pdf[0].render(scale=2).to_pil().save(TU / "okladka@2x.png")
pdf[0].render(scale=1).to_pil().save(TU / "okladka.png")
print("ok")
