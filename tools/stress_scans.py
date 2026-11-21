"""Test odporności: psuje strony PDF tak, jak psuje je biuro (ksero, faks, telefon, pieczęcie, plamy).

Każda strona jest renderowana do obrazu 200 DPI, przechodzi przez wybrane zniekształcenia na poziomie 1-3
i wraca do PDF z samymi obrazami, pod tą samą ścieżką względną - wyniki ocenia się tym samym manifestem.
Generator jest deterministyczny (ziarno zależy od nazwy pliku, profilu i numeru strony).

Użycie:
  python tools/stress_scans.py --input ../dane/.../skany --out ../eval/stress/ksero --profile ksero
  python tools/stress_scans.py --input ... --out ... --effects skew:3,grain:2
  python tools/stress_scans.py --list
"""
from __future__ import annotations

import argparse
import io
import zlib
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image

DPI = 200
WHITE = (255, 255, 255)


def _lv(values, level: int):
    return values[max(1, min(3, level)) - 1]


def skew(img, rng, lv):
    """Przekos kartki w podajniku."""
    angle = float(rng.choice([-1, 1]) * _lv((0.8, 2.0, 4.0), lv) * rng.uniform(0.7, 1.0))
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=WHITE)


def shift(img, rng, lv):
    """Kartka przesunięta na szybie: część treści wychodzi poza kadr."""
    frac = _lv((0.015, 0.035, 0.06), lv)
    h, w = img.shape[:2]
    dx, dy = (float(rng.choice([-1, 1]) * frac * s * rng.uniform(0.6, 1.0)) for s in (w, h))
    return cv2.warpAffine(img, np.float32([[1, 0, dx], [0, 1, dy]]), (w, h), borderValue=WHITE)


def grain(img, rng, lv):
    """Ziarno matrycy i kurz: szum gaussowski oraz pojedyncze czarne i białe punkty."""
    out = img.astype(np.float32) + rng.normal(0, _lv((8, 18, 30), lv), img.shape[:2])[..., None]
    out = np.clip(out, 0, 255).astype(np.uint8)
    dots = rng.random(img.shape[:2])
    frac = _lv((0.0005, 0.003, 0.01), lv)
    out[dots < frac / 2] = 0
    out[dots > 1 - frac / 2] = 255
    return out


def blur(img, rng, lv):
    """Nieostrość (kartka nie przylega do szyby, drgnięcie)."""
    return cv2.GaussianBlur(img, (0, 0), _lv((0.7, 1.2, 1.8), lv))


def lowres(img, rng, lv):
    """Skan w niskiej rozdzielczości, potem powiększony."""
    scale = _lv((150, 110, 85), lv) / DPI
    h, w = img.shape[:2]
    small = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def jpeg(img, rng, lv):
    """Mocna kompresja JPEG."""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, _lv((40, 22, 10), lv)])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def fade(img, rng, lv):
    """Wyblakły toner: czerń staje się szarością, pasami słabiej."""
    floor = _lv((60, 105, 145), lv)
    out = floor + img.astype(np.float32) * (255 - floor) / 255
    if lv >= 2:                                  # nierówny toner: pionowe pasy jeszcze bledsze
        w = img.shape[1]
        band = 1 + 0.5 * np.clip(np.sin(np.linspace(0, rng.uniform(2, 5) * np.pi, w) + rng.uniform(0, 6)), 0, 1)
        out = 255 - (255 - out) / band[None, :, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def shadow(img, rng, lv):
    """Nierówne oświetlenie i cień zgięcia kartki."""
    amp = _lv((0.15, 0.30, 0.45), lv)
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = rng.uniform(0, 2 * np.pi)
    ramp = (np.cos(ang) * xx / w + np.sin(ang) * yy / h)
    ramp = (ramp - ramp.min()) / (ramp.max() - ramp.min())
    light = 1 - amp * ramp
    fold = int(h * rng.uniform(0.3, 0.7))        # zgięcie w poprzek strony
    light *= 1 - 0.8 * amp * np.exp(-((yy - fold) / (h * 0.006)) ** 2)
    return np.clip(img.astype(np.float32) * light[..., None], 0, 255).astype(np.uint8)


def streaks(img, rng, lv):
    """Pionowe smugi brudnej szyby skanera i wypadające linie."""
    out = img.copy()
    h, w = img.shape[:2]
    for _ in range(_lv((1, 3, 6), lv)):
        x, width = int(rng.integers(int(w * 0.08), int(w * 0.92))), int(rng.integers(1, 4))
        out[:, x:x + width] = (out[:, x:x + width] * rng.uniform(0.15, 0.5)).astype(np.uint8)
    for _ in range(_lv((0, 2, 4), lv)):
        x, width = int(rng.integers(int(w * 0.08), int(w * 0.92))), int(rng.integers(1, 3))
        out[:, x:x + width] = 255
    return out


def smudge(img, rng, lv):
    """Plamy i maźnięcia na treści."""
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.float32)
    for _ in range(_lv((2, 5, 9), lv)):
        center = (int(rng.integers(int(w * 0.1), int(w * 0.9))), int(rng.integers(int(h * 0.08), int(h * 0.92))))
        axes = (int(w * rng.uniform(0.03, 0.12)), int(w * rng.uniform(0.006, 0.025)))
        cv2.ellipse(mask, center, axes, float(rng.uniform(0, 180)), 0, 360, float(rng.uniform(0.35, 0.7)), -1)
    mask = cv2.GaussianBlur(mask, (0, 0), w * 0.004)
    return np.clip(img.astype(np.float32) * (1 - mask[..., None]), 0, 255).astype(np.uint8)


def stamp(img, rng, lv):
    """Pieczęć wpływu albo firmowa odbita na tekście (kolorowy tusz, półprzezroczysta)."""
    out = img.astype(np.float32)
    h, w = img.shape[:2]
    for _ in range(_lv((1, 2, 3), lv)):
        size = int(w * rng.uniform(0.16, 0.26))
        layer = np.zeros((size, size), np.uint8)
        if rng.random() < 0.5:
            cv2.circle(layer, (size // 2, size // 2), size // 2 - 4, 255, max(3, size // 40))
            cv2.circle(layer, (size // 2, size // 2), size // 3, 255, 2)
        else:
            cv2.rectangle(layer, (4, size // 4), (size - 4, 3 * size // 4), 255, max(3, size // 45))
        for i, text in enumerate(("WPLYNELO", f"{rng.integers(1, 28):02d}.{rng.integers(1, 12):02d}.2026", f"L.dz. {rng.integers(100, 9999)}")):
            cv2.putText(layer, text, (size // 7, size // 2 - size // 10 + i * size // 9), cv2.FONT_HERSHEY_SIMPLEX,
                        size / 420, 255, max(1, size // 140), cv2.LINE_AA)
        m = cv2.getRotationMatrix2D((size / 2, size / 2), float(rng.uniform(-25, 25)), 1.0)
        layer = cv2.warpAffine(layer, m, (size, size)).astype(np.float32) / 255 * rng.uniform(0.55, 0.8)
        x, y = int(rng.integers(int(w * 0.05), w - size - int(w * 0.05))), int(rng.integers(int(h * 0.03), int(h * 0.6)))
        ink = np.float32(((150, 40, 40), (40, 40, 160), (120, 30, 110))[int(rng.integers(0, 3))])     # BGR: niebieski, czerwony, fiolet
        region = out[y:y + size, x:x + size]
        out[y:y + size, x:x + size] = region * (1 - layer[..., None]) + np.minimum(region, ink) * layer[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def highlight(img, rng, lv):
    """Zakreślacz na wierszach tekstu (po kserowaniu szare pasy)."""
    out = img.astype(np.float32)
    h, w = img.shape[:2]
    for _ in range(_lv((2, 5, 9), lv)):
        y, height = int(rng.integers(int(h * 0.08), int(h * 0.9))), int(h * rng.uniform(0.010, 0.016))
        x0, x1 = int(w * rng.uniform(0.08, 0.4)), int(w * rng.uniform(0.55, 0.92))
        tint = np.float32(((90, 240, 250), (140, 250, 150), (200, 150, 250))[int(rng.integers(0, 3))]) / 255   # żółty, zielony, różowy
        out[y:y + height, x0:x1] *= tint
    return np.clip(out, 0, 255).astype(np.uint8)


def perspective(img, rng, lv):
    """Zdjęcie telefonem: perspektywa, ciemne tło biurka wokół kartki."""
    frac = _lv((0.012, 0.03, 0.05), lv)
    h, w = img.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src + np.float32(rng.uniform(0, frac, (4, 2)) * [w, h]) * np.float32([[1, 1], [-1, 1], [-1, -1], [1, -1]])
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=(70, 80, 95))


def bleed(img, rng, lv):
    """Prześwit druku z drugiej strony cienkiej kartki."""
    alpha = _lv((0.08, 0.15, 0.25), lv)
    back = cv2.GaussianBlur(img[:, ::-1], (0, 0), 1.2).astype(np.float32)
    return np.clip(img.astype(np.float32) - alpha * (255 - back), 0, 255).astype(np.uint8)


def fax(img, rng, lv):
    """Faks: niska rozdzielczość, obraz czarno-biały, postrzępione litery i kropki."""
    scale = _lv((150, 120, 100), lv) / DPI
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    small = small.astype(np.float32) + rng.normal(0, _lv((6, 12, 18), lv), small.shape)
    binary = np.where(small > rng.uniform(150, 175), 255, 0).astype(np.uint8)
    return cv2.cvtColor(cv2.resize(binary, (w, h), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)


def rot180(img, rng, lv):
    """Kartka włożona do skanera do góry nogami."""
    return np.ascontiguousarray(img[::-1, ::-1])


def rot90(img, rng, lv):
    """Strona zeskanowana bokiem."""
    return np.ascontiguousarray(np.rot90(img, 1 if rng.random() < 0.5 else 3))


EFFECTS = {f.__name__: f for f in (skew, shift, grain, blur, lowres, jpeg, fade, shadow, streaks, smudge, stamp,
                                   highlight, perspective, bleed, fax, rot180, rot90)}

# Profile: złożenia, które spotyka się w praktyce kancelaryjnej.
PROFILES = {
    "biuro": "skew:1,grain:1,jpeg:1",                                   # zwykły skaner biurowy
    "ksero": "fade:2,grain:2,blur:1,streaks:2,skew:2,jpeg:2",           # kopia kopii, brudna szyba
    "telefon": "perspective:2,shadow:2,blur:1,grain:1,jpeg:2",          # zdjęcie telefonem
    "faks": "skew:1,fax:2",                                             # faks albo skan 1-bitowy
    "brudny": "stamp:2,smudge:2,highlight:2,skew:1,grain:1,jpeg:1",     # pieczęcie, plamy, zakreślacz
    "ciezki": "skew:3,shift:2,fade:2,grain:3,blur:2,lowres:2,smudge:2,shadow:2,jpeg:3",   # wszystko naraz
    "obrot180": "rot180:1,grain:1",
    "obrot90": "rot90:1,grain:1",
}


def parse_effects(spec: str) -> list[tuple[str, int]]:
    out = []
    for item in filter(None, (s.strip() for s in spec.split(","))):
        name, _, level = item.partition(":")
        if name not in EFFECTS:
            raise SystemExit(f"Nieznane zniekształcenie: {name}. Dostępne: {', '.join(EFFECTS)}")
        out.append((name, int(level or 2)))
    return out


def degrade_pdf(src: Path, dst: Path, effects: list[tuple[str, int]], tag: str, max_pages: int) -> int:
    pdf = pdfium.PdfDocument(str(src))
    pages = []
    for i in range(min(len(pdf), max_pages) if max_pages else len(pdf)):
        rng = np.random.default_rng(zlib.crc32(f"{src.parent.name}/{src.name}|{tag}|{i}".encode("utf-8")))
        img = cv2.cvtColor(np.asarray(pdf[i].render(scale=DPI / 72).to_pil().convert("RGB")), cv2.COLOR_RGB2BGR)
        for name, level in effects:
            img = EFFECTS[name](img, rng, level)
        pages.append(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
    dst.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:], resolution=DPI, quality=85)
    dst.write_bytes(buf.getvalue())
    return len(pages)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--profile", choices=sorted(PROFILES))
    ap.add_argument("--effects", help="np. skew:3,grain:2 (poziomy 1-3)")
    ap.add_argument("--max-pages", type=int, default=3, help="ile pierwszych stron dokumentu zostaje (0 = wszystkie)")
    ap.add_argument("--only", help="tylko pliki, których ścieżka zawiera jeden z fragmentów (po przecinku)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        for name, func in EFFECTS.items():
            print(f"{name:12} {func.__doc__}")
        for name, spec in PROFILES.items():
            print(f"profil {name:9} {spec}")
        return 0
    spec = PROFILES[args.profile] if args.profile else args.effects
    if not (args.input and args.out and spec):
        ap.error("podaj --input, --out oraz --profile albo --effects")
    effects = parse_effects(spec)
    only = [s for s in (args.only or "").split(",") if s]
    count = pages = 0
    for src in sorted(args.input.rglob("*.pdf")):
        rel = src.relative_to(args.input)
        if only and not any(s in rel.as_posix() for s in only):
            continue
        pages += degrade_pdf(src, args.out / rel, effects, spec, args.max_pages)
        count += 1
    print(f"{spec}: {count} dokumentów, {pages} stron -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
