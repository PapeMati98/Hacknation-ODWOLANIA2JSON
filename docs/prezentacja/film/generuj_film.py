"""Film ok. 45 s z okładki i slajdów prezentacji, z lektorem (macOS `say`, głos Zosia).

python generuj_film.py okladka.png prezentacja.pdf film.mp4 [folder_z_nagraniami]
Bez folderu tekst czyta syntezator macOS (Zosia); z folderem bierze nagranie_0 … nagranie_6.
Wymaga: macOS (say), pypdfium2, pillow, imageio-ffmpeg.
"""
import re, subprocess, sys, wave, tempfile
from pathlib import Path

import imageio_ffmpeg
import pypdfium2
from PIL import Image

FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1920, 1080
FADE = 0.5
PAD_PRZED, PAD_PO = 0.35, 0.55
RATE = "185"  # słów/min

# Tekst do czytania (pisownia fonetyczna dla syntezatora) — jeden fragment na klatkę:
# klatka 0 = okładka, 1..6 = slajdy.
SCENARIUSZ = [
    "Dżejson, ja tu tylko parsuję. Projekt drużyny: Nie wiem, ale wygeneruję, dla Urzędu Zamówień Publicznych.",
    "Sprawa przed Krajową Izbą Odwoławczą to kilka plików pe de ef. Nasza aplikacja sama odczytuje z nich dane, z pomocą polskiego modelu językowego Synaps.",
    "Wgrywasz pliki sprawy, a dla każdego dokumentu dostajesz gotowy plik dżejson. Pola niepewne trafiają do sprawdzenia przez człowieka.",
    "Na trzydziestu skanach Urzędu wynik F jeden przekracza zero przecinek dziewięćdziesiąt dziewięć.",
    "Nowy rodzaj dokumentu dodajesz jednym plikiem konfiguracyjnym, bez programowania.",
    "Jury uruchamia ocenę całej partii jednym poleceniem.",
    "Wszystkie składniki są otwarte. Dżejson, ja tu tylko parsuję.",
]


def run(*a):
    subprocess.run(a, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def klatki(okladka, pdf, tmp):
    out = []
    bg = Image.new("RGB", (W, H), "white")
    ok = Image.open(okladka).convert("RGB")
    k = H / ok.height
    ok = ok.resize((round(ok.width * k), H), Image.LANCZOS)
    im = bg.copy(); im.paste(ok, ((W - ok.width) // 2, 0))
    p = tmp / "k0.png"; im.save(p); out.append(p)
    doc = pypdfium2.PdfDocument(str(pdf))
    for i in range(len(doc)):
        im = doc[i].render(scale=W / doc[i].get_width()).to_pil().convert("RGB").resize((W, H), Image.LANCZOS)
        p = tmp / f"k{i + 1}.png"; im.save(p); out.append(p)
    return out


def glos(tmp):
    pliki, dl = [], []
    for i, t in enumerate(SCENARIUSZ):
        a = tmp / f"g{i}.wav"
        run("say", "-v", "Zosia", "-r", RATE, "--file-format=WAVE", "--data-format=LEI16@22050", "-o", str(a), t)
        with wave.open(str(a)) as f:
            dl.append(f.getnframes() / f.getframerate())
        pliki.append(a)
    return pliki, dl


def czas_pliku(p):
    """Długość nagrania w sekundach (dowolny format obsługiwany przez ffmpeg)."""
    r = subprocess.run([FF, "-i", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        sys.exit(f"Nie mogę odczytać długości: {p}")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def nagrania(folder):
    """Własne nagrania lektora: nagranie_0 … nagranie_6 (.wav/.mp3/.m4a/.aac/.aiff)."""
    pliki, dl = [], []
    for i in range(len(SCENARIUSZ)):
        found = sorted(Path(folder).glob(f"nagranie_{i}.*"))
        if not found:
            sys.exit(f"Brak pliku nagranie_{i}.* w {folder}")
        pliki.append(found[0]); dl.append(czas_pliku(found[0]))
    return pliki, dl


def main(okladka, pdf, wyj, folder_nagran=None):
    tmp = Path(tempfile.mkdtemp())
    img = klatki(okladka, pdf, tmp)
    aud, dl = nagrania(folder_nagran) if folder_nagran else glos(tmp)
    assert len(img) == len(aud)
    czasy = [max(d + PAD_PRZED + PAD_PO, 5.0) for d in dl]
    starty, t = [], 0.0
    for c in czasy:
        starty.append(t); t += c - FADE
    calosc = t + FADE
    args = [FF, "-y"]
    for p, c in zip(img, czasy):
        args += ["-loop", "1", "-t", f"{c:.3f}", "-i", str(p)]
    for a in aud:
        args += ["-i", str(a)]
    n = len(img); f = []
    for i in range(n):
        f.append(f"[{i}:v]fps=30,format=yuv420p,setsar=1[v{i}]")
    prev = "v0"
    for i in range(1, n):
        f.append(f"[{prev}][v{i}]xfade=transition=fade:duration={FADE}:offset={starty[i]:.3f}[x{i}]")
        prev = f"x{i}"
    for i in range(n):
        ms = round((starty[i] + PAD_PRZED) * 1000)
        f.append(f"[{n + i}:a]aresample=48000,aformat=channel_layouts=mono,adelay={ms}|{ms}[a{i}]")
    f.append("".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad,atrim=0:{calosc:.3f}[a]")
    args += ["-filter_complex", ";".join(f), "-map", f"[{prev}]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", f"{calosc:.3f}", str(wyj)]
    r = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        print(r.stderr[-3000:]); sys.exit(1)
    print("długości mowy:", [round(d, 1) for d in dl])
    print(f"film: {calosc:.1f} s -> {wyj}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
