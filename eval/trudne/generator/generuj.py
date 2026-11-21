"""Generator syntetycznych spraw KIO z gold JSON (format organizatora UZP).

  python generuj.py --out ../syntetyczne --kio ../kio-orzeczenia

Sprawy synt_01-06: PDF z warstwą tekstową. Sprawy synt_07-12: średnio wyraźne skany (sam obraz).
Sprawy 01-03 i 07-09 są "zwykłe", 04-06 i 10-12 mają trudności (opis w opis.json każdej sprawy).
Część spraw zawiera dokument spoza klas: gold to pusty JSON {}.
Wszystkie numery są fikcyjne (prefiks 999), ale z poprawnymi sumami kontrolnymi.
"""
import argparse
import io
import json
import random
import shutil
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

FONTS = "/System/Library/Fonts/Supplemental/"
for name, f in [("Arial", "Arial.ttf"), ("Arial-B", "Arial Bold.ttf"),
                ("Times", "Times New Roman.ttf"), ("Times-B", "Times New Roman Bold.ttf")]:
    pdfmetrics.registerFont(TTFont(name, FONTS + f))

POWODY = {1: "Decyzja o odrzuceniu oferty", 2: "Ogłoszenie wyboru oferty",
          3: "Decyzja o wykluczeniu wykonawcy", 4: "Publikacja specyfikacji warunków zamówienia (SWZ)",
          5: "Modyfikacja treści SWZ", 6: "Odpowiedzi/wyjaśnienia do SWZ",
          7: "Zaniechanie odrzucenia oferty", 8: "Zaniechanie wykluczenia wykonawcy",
          9: "Decyzja o unieważnieniu postępowania", 10: "Zaniechanie unieważnienia postępowania",
          11: "Opis przedmiotu zamówienia (OPZ)", 12: "Projektowane postanowienia umowy"}
# zdanie o czynności (pierwszy zarzut) dla każdego powodu
CZYNNOSC = {1: "poinformował Odwołującego o odrzuceniu jego oferty",
            2: "zawiadomił o wyborze jako najkorzystniejszej oferty złożonej przez innego wykonawcę",
            3: "poinformował o wykluczeniu Odwołującego z postępowania",
            4: "opublikował ogłoszenie o zamówieniu wraz ze specyfikacją warunków zamówienia (SWZ)",
            5: "dokonał modyfikacji treści specyfikacji warunków zamówienia",
            6: "udzielił odpowiedzi na pytania wykonawców dotyczące treści SWZ",
            7: "zaniechał odrzucenia oferty wykonawcy, który złożył ofertę z rażąco niską ceną",
            8: "zaniechał wykluczenia wykonawcy, który nie wykazał spełniania warunków udziału",
            9: "unieważnił postępowanie o udzielenie zamówienia",
            10: "zaniechał unieważnienia postępowania obarczonego niemożliwą do usunięcia wadą",
            11: "udostępnił opis przedmiotu zamówienia (OPZ) zawierający wymagania naruszające uczciwą konkurencję",
            12: "udostępnił projektowane postanowienia umowy (załącznik nr 4 do SWZ) przewidujące nieproporcjonalne kary umowne"}

MIESIACE = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
            "września", "października", "listopada", "grudnia"]

# (mianownik, biernik) - pełnomocnicy w tekście bywają w przypadku zależnym
OSOBY = [("Anna Kowalska", "Annę Kowalską"), ("Piotr Nowak", "Piotra Nowaka"),
         ("Katarzyna Wiśniewska", "Katarzynę Wiśniewską"), ("Tomasz Zieliński", "Tomasza Zielińskiego"),
         ("Magdalena Lewandowska", "Magdalenę Lewandowską"), ("Michał Dąbrowski", "Michała Dąbrowskiego"),
         ("Agnieszka Wójcik", "Agnieszkę Wójcik"), ("Paweł Kamiński", "Pawła Kamińskiego"),
         ("Joanna Kaczmarek", "Joannę Kaczmarek"), ("Krzysztof Pawlak", "Krzysztofa Pawlaka"),
         ("Ewa Michalska", "Ewę Michalską"), ("Grzegorz Król", "Grzegorza Króla"),
         ("Monika Jankowska", "Monikę Jankowską"), ("Jakub Wróblewski", "Jakuba Wróblewskiego"),
         ("Barbara Górecka", "Barbarę Górecką"), ("Łukasz Sikora", "Łukasza Sikorę"),
         ("Dorota Baran", "Dorotę Baran"), ("Marcin Szczepański", "Marcina Szczepańskiego"),
         ("Zofia Adamczyk", "Zofię Adamczyk"), ("Robert Mazurek", "Roberta Mazurka")]

FIRMY_A = ["Velstor", "Brontex", "Aldomet", "Kerbud", "Nordima", "Trimex", "Solvana", "Medikor",
           "Polsan", "Gratan", "Interlux", "Wikomed", "Budrex", "Ekoprim", "Datanet", "Termix"]
FIRMY_B = ["Budownictwo", "Serwis", "Technologie", "Medical", "Infrastruktura", "Logistyka",
           "Systemy IT", "Energia", "Facility", "Projekt"]
FORMY = ["Sp. z o.o.", "S.A.", "sp. z o.o.", "Spółka z ograniczoną odpowiedzialnością", "sp.k."]
ZAMAWIAJACY = ["Gmina Miasto Ostrołęka", "Szpital Wojewódzki im. Jana Pawła II w Zamościu",
               "Zarząd Dróg Powiatowych w Kutnie", "Uniwersytet Przyrodniczy w Lublinie",
               "Miejskie Przedsiębiorstwo Wodociągów i Kanalizacji w Pile Sp. z o.o.",
               "Państwowe Gospodarstwo Leśne Lasy Państwowe Nadleśnictwo Biała Podlaska",
               "Centrum Usług Wspólnych Powiatu Gnieźnieńskiego", "Akademia Muzyczna w Bydgoszczy",
               "Komenda Wojewódzka Państwowej Straży Pożarnej w Opolu", "Teatr Miejski w Gliwicach",
               "Powiat Kędzierzyńsko-Kozielski", "Zakład Gospodarki Komunalnej w Koninie Sp. z o.o."]
TYTULY = ["Przebudowa drogi powiatowej nr 2104E na odcinku Krośniewice – Nowe",
          "Dostawa sprzętu komputerowego i oprogramowania dla jednostek oświatowych",
          "Świadczenie usług kompleksowego sprzątania obiektów w latach 2027–2029",
          "Dostawa energii elektrycznej do obiektów Zamawiającego w 2027 roku",
          "Budowa sali gimnastycznej wraz z zapleczem przy Szkole Podstawowej nr 3",
          "Dostawa leków onkologicznych w podziale na 9 pakietów",
          "Pełnienie funkcji inżyniera kontraktu dla zadania „Modernizacja oczyszczalni ścieków”",
          "Odbiór i zagospodarowanie odpadów komunalnych z terenu gminy",
          "Dostawa pojazdu ratowniczo-gaśniczego z napędem 4x4",
          "Wdrożenie zintegrowanego systemu informatycznego klasy ERP"]
MIASTA = [("Warszawa", "00-950"), ("Kraków", "31-155"), ("Poznań", "61-814"), ("Łódź", "90-410"),
          ("Wrocław", "50-077"), ("Gdańsk", "80-831"), ("Lublin", "20-076"), ("Białystok", "15-062"),
          ("Rzeszów", "35-064"), ("Katowice", "40-098"), ("Szczecin", "70-410"), ("Toruń", "87-100")]
ULICE = ["ul. Lipowa", "ul. Kościuszki", "al. Niepodległości", "ul. Polna", "ul. Słowackiego",
         "ul. Ogrodowa", "ul. Mickiewicza", "ul. Przemysłowa", "ul. Wiejska", "ul. Grunwaldzka"]
BANKI = ["Bank Nadwiślański S.A.", "Kredyt Północny", "Bank Spółdzielczy w Wierzbicy", "e-Bank Polska S.A."]
KIO_NRB = "37101010100090482231000000"  # rachunek UZP wg pism, tu tylko jako fikcyjny odbiorca

# ---------------------------------------------------------------- numery z sumą kontrolną

def nip(r):
    while True:
        d = [9, 9, 9] + [r.randint(0, 9) for _ in range(6)]
        c = sum(a * b for a, b in zip(d, [6, 5, 7, 2, 3, 4, 5, 6, 7])) % 11
        if c < 10:
            return "".join(map(str, d + [c]))


def regon(r):
    d = [9, 9, 9] + [r.randint(0, 9) for _ in range(5)]
    c = sum(a * b for a, b in zip(d, [8, 9, 2, 3, 4, 5, 6, 7])) % 11 % 10
    return "".join(map(str, d + [c]))


def krs(r):
    return "999" + "".join(str(r.randint(0, 9)) for _ in range(7))


def nrb(r):
    bban = "".join(str(r.randint(0, 9)) for _ in range(24))
    num = int(bban + "252100")  # P=25, L=21, 00
    return f"{98 - num % 97:02d}" + bban


def pesel(r):
    y, m, dd = r.randint(60, 99), r.randint(1, 12), r.randint(1, 28)
    d = [int(x) for x in f"{y:02d}{m:02d}{dd:02d}"] + [r.randint(0, 9) for _ in range(4)]
    c = (10 - sum(a * b for a, b in zip(d, [1, 3, 7, 9, 1, 3, 7, 9, 1, 3])) % 10) % 10
    return "".join(map(str, d + [c]))


def spaced_nrb(n):
    return n[:2] + " " + " ".join(n[i:i + 4] for i in range(2, 26, 4))


def dashed_nip(n):
    return f"{n[:3]}-{n[3:6]}-{n[6:8]}-{n[8:]}"

# ---------------------------------------------------------------- daty

def iso(d):
    return f"2026-{d[0]:02d}-{d[1]:02d}"


def slownie(d):
    return f"{d[1]} {MIESIACE[d[0] - 1]} 2026 r."


def kropki(d):
    return f"{d[1]:02d}.{d[0]:02d}.2026"

# ---------------------------------------------------------------- dane sprawy

def firma(r, used):
    while True:
        n = f"{r.choice(FIRMY_A)} {r.choice(FIRMY_B)} {r.choice(FORMY)}"
        if n not in used:
            used.add(n)
            return n


def podmiot(r, used, nazwa=None):
    miasto, kod = r.choice(MIASTA)
    return {"nazwa": nazwa or firma(r, used), "krs": krs(r), "nip": nip(r), "regon": regon(r),
            "adres": f"{r.choice(ULICE)} {r.randint(1, 180)}, {kod} {miasto}", "miasto": miasto}


def sprawa(r, cfg):
    used = set()
    osoby = r.sample(OSOBY, 6)
    odw = [podmiot(r, used) for _ in range(2 if cfg.get("konsorcjum") else 1)]
    if cfg.get("osoba_fizyczna"):
        imie = osoby[5][0]
        odw[0].update(nazwa=f"{r.choice(FIRMY_A)} Usługi {imie}", krs=None, wlasciciel=imie)
    zam_names = r.sample(ZAMAWIAJACY, 2)
    zam = [podmiot(r, used, zam_names[0])]
    if cfg.get("dwoch_zamawiajacych"):
        zam.append(podmiot(r, used, zam_names[1]))
    if cfg.get("zam_bez_krs"):
        zam[0]["krs"] = None
    powod = cfg["powod"]
    m = r.randint(3, 9)
    czyn = (m, r.randint(1, 18))
    data_odw = (m, czyn[1] + r.randint(5, 10))
    przelew = (m, data_odw[1] - r.randint(0, 2))
    kanc_nazwisko = osoby[0][0].split()[1]
    kancelaria = r.choice([f"Kancelaria Radcy Prawnego {osoby[0][0]}",
                           f"{kanc_nazwisko} i Wspólnicy Kancelaria Prawna sp.k.",
                           "Kancelaria Adwokacka Lex Publica sp.p."])
    domena = kanc_nazwisko.lower().replace("ł", "l").replace("ń", "n").replace("ś", "s") \
        .replace("ż", "z").replace("ź", "z").replace("ó", "o").replace("ą", "a").replace("ę", "e") \
        .replace("ć", "c")
    nr_post = r.choice([f"ZP.271.{r.randint(10, 99)}.2026", f"DZP/{r.randint(100, 999)}/26",
                        f"SZP-{r.randint(1, 60)}/2026", f"IZ.272.{r.randint(1, 30)}.2026.AK"])
    bzp = ted = None
    if cfg.get("ted"):
        ted_n = r.randint(100000, 999999)
        ted = f"{ted_n}-2026"
        ted_txt = f"2026/S {r.randint(100, 230)}-{ted_n}"
    else:
        bzp_n = f"{r.randint(0, 999999):08d}"
        korekta = "/01" if cfg.get("bzp_korekta") else ""
        bzp = f"2026/BZP{bzp_n}{korekta}"
        bzp_txt = f"2026/BZP {bzp_n}{korekta}" if cfg.get("bzp_spacja") else bzp
    return dict(cfg=cfg, odw=odw, zam=zam, powod=powod, czyn=czyn, data_odw=data_odw,
                przelew=przelew, osoby=osoby, kancelaria=kancelaria,
                mail=f"biuro@{domena}-kancelaria.example", nr_post=nr_post,
                tytul=r.choice(TYTULY), bzp=bzp, ted=ted,
                bzp_txt=None if ted else bzp_txt, ted_txt=ted_txt if ted else None,
                kwota=r.choice([7500.0, 10000.0, 15000.0, 20000.0]),
                z_rach=nrb(r), na_rach=nrb(r), bank=r.choice(BANKI),
                trans=None if cfg.get("bez_numeru_transakcji") else
                f"TRX{r.randint(10**11, 10**12 - 1)}",
                pesel_pel=pesel(r) if cfg.get("pesel") else None)

# ---------------------------------------------------------------- gold

def gold_odwolanie(s):
    c = s["cfg"]
    lider = s["odw"][0]
    pel_nom = s["osoby"][0][0]
    return {
        "OdwolanieKIO": {
            "data": None if c.get("data_na_koncu") else iso(s["data_odw"]),
            "czynnosc_dzien": iso(s["czyn"]),
            "czynnosc_powod_id": s["powod"],
            "czynnosc_opis": POWODY[s["powod"]],
            "miejscowosc": None if c.get("data_na_koncu") else s["odw"][0]["miasto"],
        },
        "Odwolujacy": [{
            "krs": lider["krs"], "nazwa": lider["nazwa"], "nip": lider["nip"], "regon": lider["regon"],
            "przez-pelnomocnika": 1,
            "pelnomocnik": {"imie_nazwisko": pel_nom, "nazwa": s["kancelaria"], "mail": s["mail"]},
        }],
        "Zamawiajacy": [{
            "krs": z["krs"], "nazwa": z["nazwa"], "nip": z["nip"], "regon": z["regon"],
            "prowadzacy_postepowanie": (1 if i == 0 else 0) if len(s["zam"]) > 1 else None,
        } for i, z in enumerate(s["zam"])],
        "ZamowieniePubliczne": {"numer_bzp": s["bzp"], "numer_postepowania": s["nr_post"],
                                "numer_ted": s["ted"], "tytul": s["tytul"]},
    }


def gold_pelnomocnictwo(s):
    moc = []
    for i, o in enumerate(s["odw"]):
        fiz = "wlasciciel" in o
        podp = [s["osoby"][2 + i][0]] if not fiz else [o["wlasciciel"]]
        moc.append({"data": {"imie_nazwisko": o["wlasciciel"] if fiz else None, "krs": o["krs"],
                             "nazwa": o["nazwa"], "nip": o["nip"],
                             "typ": "osoba_fizyczna" if fiz else "osoba_prawna"},
                    "podpisujacy": [{"imie_nazwisko": p} for p in podp]})
    return {"mocodawca": moc,
            "pelnomocnicy": [{"imie_nazwisko": s["osoby"][0][0], "pesel": s["pesel_pel"]},
                             {"imie_nazwisko": s["osoby"][1][0], "pesel": None}]}


def tytul_przelewu(s):
    return (f"Wpis od odwołania - {s['zam'][0]['nazwa']}, postępowanie nr {s['nr_post']}"
            if not s["cfg"].get("dlugi_tytul") else
            f"WPIS OD ODWOŁANIA DO PREZESA KIO, ODWOŁUJĄCY: {s['odw'][0]['nazwa'].upper()}, "
            f"ZAMAWIAJĄCY: {s['zam'][0]['nazwa'].upper()}, NR {s['nr_post']}")


def gold_przelew(s):
    return {"przelew_bankowy": {"data_operacji": iso(s["przelew"]), "kwota": s["kwota"],
                                "na_rachunek": s["na_rach"], "numer_transakcji": s["trans"],
                                "tytul": tytul_przelewu(s), "z_rachunku": s["z_rach"]}}

# ---------------------------------------------------------------- PDF

def styles(font):
    b = font + "-B"
    return {"n": ParagraphStyle("n", fontName=font, fontSize=10.5, leading=14, alignment=TA_JUSTIFY),
            "l": ParagraphStyle("l", fontName=font, fontSize=10.5, leading=14),
            "r": ParagraphStyle("r", fontName=font, fontSize=10.5, leading=14, alignment=TA_RIGHT),
            "h": ParagraphStyle("h", fontName=b, fontSize=15, leading=20, alignment=TA_CENTER,
                                spaceBefore=8, spaceAfter=8),
            "b": ParagraphStyle("b", fontName=b, fontSize=10.5, leading=14),
            "s": ParagraphStyle("s", fontName=font, fontSize=8, leading=10, textColor=colors.grey)}


def podpis(canvas, x, y, r):
    """Odręczny podpis: kilka krzywych."""
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#1b2a6b"))
    canvas.setLineWidth(1.1)
    p = canvas.beginPath()
    p.moveTo(x, y)
    for _ in range(4):
        p.curveTo(x + r.uniform(5, 20), y + r.uniform(-8, 14), x + r.uniform(20, 35),
                  y + r.uniform(-10, 10), x + r.uniform(30, 45), y + r.uniform(-3, 5))
        x += r.uniform(25, 40)
    canvas.drawPath(p)
    canvas.restoreState()


def pieczatka(canvas, x, y, tekst):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#2b4fa8"))
    canvas.setFillColor(colors.HexColor("#2b4fa8"))
    canvas.setLineWidth(1.5)
    canvas.roundRect(x, y, 62 * mm, 16 * mm, 3 * mm)
    canvas.setFont("Arial-B", 8)
    canvas.drawCentredString(x + 31 * mm, y + 10 * mm, tekst[:42])
    canvas.setFont("Arial", 7)
    canvas.drawCentredString(x + 31 * mm, y + 5 * mm, "WPŁYNĘŁO / dziennik podawczy")
    canvas.restoreState()


def build(path, story, r, font="Arial", sign_pages=(), stamp=None, footer=True):
    def on_page(canvas, doc):
        if footer:
            canvas.setFont(font, 8)
            canvas.drawCentredString(A4[0] / 2, 12 * mm, f"Strona {doc.page}")
        if doc.page in sign_pages or (sign_pages == "last"):
            pass
        if stamp and doc.page == 1:
            pieczatka(canvas, A4[0] - 80 * mm, A4[1] - 32 * mm, stamp)

    def on_last(canvas, doc):
        on_page(canvas, doc)

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=20 * mm, bottomMargin=22 * mm)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


class Sign(Spacer):
    """Miejsce na podpis z odręczną kreską."""

    def __init__(self, r):
        super().__init__(1, 16 * mm)
        self.r = r

    def draw(self):
        podpis(self.canv, 95 * mm, 6 * mm, self.r)


ZARZUT_TEKST = (
    "Zamawiający naruszył zasadę uczciwej konkurencji i równego traktowania wykonawców, o której mowa "
    "w art. 16 Pzp, a także art. 99 ust. 1 i 4 Pzp, poprzez sformułowanie wymagań w sposób, który "
    "nie wynika z obiektywnych potrzeb Zamawiającego. Odwołujący ma interes w uzyskaniu zamówienia "
    "i może ponieść szkodę w wyniku naruszenia przez Zamawiającego przepisów ustawy.")


def blok_podmiotu(p, st, sep=", ", nip_fmt=str):
    lines = [f"<b>{p['nazwa']}</b>", p["adres"]]
    ids = []
    if p.get("krs"):
        ids.append(f"KRS: {p['krs']}")
    ids += [f"NIP: {nip_fmt(p['nip'])}", f"REGON: {p['regon']}"]
    lines.append(sep.join(ids))
    return [Paragraph(x, st["l"]) for x in lines]


def odwolanie_pdf(path, s, r):
    c = s["cfg"]
    font = "Times" if c.get("times") else "Arial"
    st = styles(font)
    nip_fmt = dashed_nip if c.get("nip_myslniki") else str
    S = []
    pel1, pel2 = s["osoby"][0], s["osoby"][1]
    if c.get("kancelaria_naglowek"):
        S += [Paragraph(f"<b>{s['kancelaria'].upper()}</b>", st["l"]),
              Paragraph(f"{r.choice(ULICE)} {r.randint(1, 90)}, {r.choice(MIASTA)[1]} {s['odw'][0]['miasto']}"
                        f" · tel. 000 000 000 · sekretariat@lex-{r.randint(1, 99)}.example", st["s"]),
              Spacer(1, 8)]
    naglowek = f"{s['odw'][0]['miasto']}, dnia {slownie(s['data_odw']) if c.get('data_slownie') else kropki(s['data_odw'])}"
    if not c.get("data_na_koncu"):
        S += [Paragraph(naglowek, st["r"]), Spacer(1, 6)]
    S += [Paragraph("<b>Prezes Krajowej Izby Odwoławczej</b>", st["l"]),
          Paragraph("ul. Postępu 17A, 02-676 Warszawa", st["l"]), Spacer(1, 8)]

    def odwolujacy_blok():
        out = []
        if c.get("konsorcjum"):
            out.append(Paragraph("<b>Odwołujący:</b> Konsorcjum wykonawców wspólnie ubiegających się "
                                 "o udzielenie zamówienia w składzie:", st["l"]))
            for i, o in enumerate(s["odw"]):
                out.append(Paragraph(("1) Lider Konsorcjum:" if i == 0 else "2) Partner Konsorcjum:"), st["l"]))
                out += blok_podmiotu(o, st, nip_fmt=nip_fmt)
        else:
            out.append(Paragraph("<b>Odwołujący:</b>", st["l"]))
            out += blok_podmiotu(s["odw"][0], st, nip_fmt=nip_fmt)
            if "wlasciciel" in s["odw"][0]:
                out.append(Paragraph(f"przedsiębiorca: {s['odw'][0]['wlasciciel']}, wpisany do CEIDG", st["l"]))
        if c.get("odmiana"):
            out.append(Paragraph(f"reprezentowanego przez r. pr. {pel1[1]} oraz adw. {pel2[1]}", st["l"]))
        else:
            out.append(Paragraph(f"reprezentowany przez: r. pr. {pel1[0]}, adw. {pel2[0]}", st["l"]))
        out.append(Paragraph(f"adres do korespondencji: {s['kancelaria']}, e-mail: {s['mail']}", st["l"]))
        return out

    def zamawiajacy_blok():
        out = []
        if len(s["zam"]) > 1:
            out.append(Paragraph("<b>Zamawiający</b> (wspólnie przeprowadzający postępowanie, art. 38 ust. 1 Pzp):", st["l"]))
            for i, z in enumerate(s["zam"]):
                out.append(Paragraph("1) Zamawiający – Lider, prowadzący postępowanie:" if i == 0
                                     else "2) Zamawiający – Partner:", st["l"]))
                out += blok_podmiotu(z, st, nip_fmt=nip_fmt)
        else:
            out.append(Paragraph("<b>Zamawiający:</b>", st["l"]))
            out += blok_podmiotu(s["zam"][0], st, nip_fmt=nip_fmt)
        return out

    if c.get("tabela"):
        t = Table([[zamawiajacy_blok(), odwolujacy_blok()]], colWidths=[80 * mm, 86 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
        S += [t, Spacer(1, 8)]
    else:
        first, second = (odwolujacy_blok, zamawiajacy_blok) if c.get("odwolujacy_pierwszy") else \
            (zamawiajacy_blok, odwolujacy_blok)
        S += first() + [Spacer(1, 6)] + second() + [Spacer(1, 6)]

    ogl = (f"ogłoszenie w Dzienniku Urzędowym UE nr {s['ted_txt']}" if s["ted"] else
           f"ogłoszenie o zamówieniu w Biuletynie Zamówień Publicznych nr {s['bzp_txt']}")
    S += [Paragraph(f"<b>dotyczy:</b> postępowania o udzielenie zamówienia publicznego pn. „{s['tytul']}”, "
                    f"nr referencyjny: {s['nr_post']}, {ogl}", st["n"]),
          Paragraph(f"Wpis od odwołania: {s['kwota']:,.2f} zł".replace(",", " ").replace(".", ","), st["l"]),
          Paragraph("ODWOŁANIE", st["h"])]
    S.append(Paragraph(
        "Działając w imieniu Odwołującego, na podstawie pełnomocnictwa załączonego do niniejszego "
        "odwołania, na podstawie art. 505 ust. 1 i art. 513 pkt 1 i 2 ustawy z dnia 11 września 2019 r. "
        "– Prawo zamówień publicznych (Dz. U. z 2024 r. poz. 1320 ze zm.), wnoszę odwołanie wobec "
        "czynności i zaniechań Zamawiającego opisanych poniżej.", st["n"]))
    if c.get("zarzut_na_2_stronie"):
        S.append(Paragraph("<b>I. Wprowadzenie</b>", st["b"]))
        for _ in range(6):
            S.append(Paragraph(ZARZUT_TEKST + " " + ZARZUT_TEKST, st["n"]))
        S.append(PageBreak())
    dzien = slownie(s["czyn"]) if c.get("data_slownie") else kropki(s["czyn"])
    S += [Spacer(1, 4), Paragraph("<b>Zarzuty</b>", st["b"]),
          Paragraph(f"Zamawiający w dniu {dzien} {CZYNNOSC[s['powod']]}. Odwołujący zarzuca Zamawiającemu:", st["n"]),
          Paragraph(f"1. naruszenie art. 16 pkt 1 Pzp w zw. z czynnością opisaną powyżej. {ZARZUT_TEKST}", st["n"]),
          Paragraph(f"2. naruszenie art. 99 ust. 4 Pzp. {ZARZUT_TEKST}", st["n"]),
          Paragraph("<b>Żądania</b>", st["b"]),
          Paragraph("Wnoszę o uwzględnienie odwołania w całości, nakazanie Zamawiającemu unieważnienia "
                    "zaskarżonej czynności oraz zasądzenie kosztów postępowania odwoławczego.", st["n"]),
          Paragraph("<b>Uzasadnienie</b>", st["b"])]
    for _ in range(3):
        S.append(Paragraph(ZARZUT_TEKST, st["n"]))
    if c.get("data_na_koncu"):
        S += [Spacer(1, 8), Paragraph(f"Sporządzono {kropki(s['data_odw'])}", st["l"])]
    S += [Spacer(1, 6), Paragraph("W imieniu Odwołującego:", st["r"]), Sign(r),
          Paragraph(f"r. pr. {pel1[0]}", st["r"]),
          Paragraph("Załączniki: 1) pełnomocnictwo, 2) dowód uiszczenia wpisu, 3) dowód przekazania "
                    "odwołania Zamawiającemu.", st["s"])]
    build(path, S, r, font=font, stamp="KRAJOWA IZBA ODWOŁAWCZA" if c.get("pieczatka") else None)


def pelnomocnictwo_pdf(path, s, r):
    c = s["cfg"]
    font = "Times" if c.get("times") else "Arial"
    st = styles(font)
    pel1, pel2 = s["osoby"][0], s["osoby"][1]
    S = [Paragraph(f"{s['odw'][0]['miasto']}, {kropki(s['data_odw'])}", st["r"]),
         Paragraph("PEŁNOMOCNICTWO", st["h"])]
    opisy = []
    for o in s["odw"]:
        if "wlasciciel" in o:
            opisy.append(f"{o['wlasciciel']}, prowadzący działalność gospodarczą pod firmą {o['nazwa']}, "
                         f"{o['adres']}, NIP {o['nip']}, REGON {o['regon']}")
        else:
            opisy.append(f"{o['nazwa']}, {o['adres']}, KRS {o['krs']}, NIP {o['nip']}, REGON {o['regon']}")
    if len(opisy) > 1:
        kto = "Wykonawcy wspólnie ubiegający się o udzielenie zamówienia (Konsorcjum): " + \
              "; ".join(f"{i + 1}) {x}" for i, x in enumerate(opisy)) + " (dalej łącznie: „Mocodawca”)"
    else:
        kto = opisy[0] + " (dalej: „Mocodawca”)"
    pesel_txt = f", PESEL {s['pesel_pel']}" if s["pesel_pel"] else ""
    S += [Paragraph(f"{kto} udziela pełnomocnictwa: r. pr. {pel1[0]}{pesel_txt} (nr wpisu WA-{r.randint(1000, 9999)}) "
                    f"oraz adw. {pel2[0]} (nr wpisu KR/Adw/{r.randint(100, 999)}).", st["n"]),
          Spacer(1, 6),
          Paragraph(f"Pełnomocnictwo obejmuje reprezentowanie Mocodawcy w postępowaniu o udzielenie zamówienia "
                    f"publicznego pn. „{s['tytul']}”, nr {s['nr_post']}, prowadzonym przez {s['zam'][0]['nazwa']}, "
                    "w tym do wniesienia odwołania do Prezesa Krajowej Izby Odwoławczej, jego cofnięcia, "
                    "zastępowania Mocodawcy na posiedzeniach i rozprawach oraz wniesienia skargi do sądu "
                    "zamówień publicznych. Pełnomocnicy działają samodzielnie.", st["n"]),
          Spacer(1, 14)]
    for i, o in enumerate(s["odw"]):
        podp = o["wlasciciel"] if "wlasciciel" in o else s["osoby"][2 + i][0]
        funkcja = "właściciel" if "wlasciciel" in o else r.choice(["Prezes Zarządu", "Członek Zarządu", "Prokurent"])
        S += [Paragraph(f"W imieniu {o['nazwa']}:", st["l"]), Sign(r),
              Paragraph(f"{podp} – {funkcja}", st["l"]), Spacer(1, 6)]
    S.append(Paragraph("Opłata skarbowa od pełnomocnictwa w kwocie 17 zł została uiszczona.", st["s"]))
    build(path, S, r, font=font, footer=False)


def przelew_pdf(path, s, r):
    c = s["cfg"]
    st = styles("Arial")
    kw = f"{s['kwota']:,.2f}".replace(",", " ").replace(".", ",")
    if c.get("kwota_pln"):
        kw = f"{s['kwota']:,.2f}".replace(",", ".")
        kw = kw[:-3] + "," + kw[-2:] + " PLN"
    else:
        kw += " zł"
    rach = spaced_nrb if c.get("rachunek_spacje") else (lambda x: x)
    data = slownie(s["przelew"]) if c.get("data_slownie") else iso(s["przelew"])
    rows = [["Płatnik", f"{s['odw'][0]['nazwa']}\n{s['odw'][0]['adres']}\n{rach(s['z_rach'])}"],
            ["Odbiorca", f"Urząd Zamówień Publicznych\nul. Postępu 17A, 02-676 Warszawa\n{rach(s['na_rach'])}"],
            ["Kwota", kw], ["Data operacji", data]]
    if s["trans"]:
        rows.append(["Numer transakcji", s["trans"]])
    rows += [["Tytuł", Paragraph(tytul_przelewu(s), st["l"])], ["Status", "Zrealizowana"]]
    t = Table(rows, colWidths=[42 * mm, 120 * mm])
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Arial"), ("FONTSIZE", (0, 0), (-1, -1), 10),
                           ("FONTNAME", (0, 0), (0, -1), "Arial-B"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey)]))
    S = [Paragraph(f"<b>{s['bank']}</b>", st["l"]),
         Paragraph(f"Potwierdzenie wykonania przelewu · wygenerowano {kropki(s['przelew'])}", st["s"]),
         Spacer(1, 10), Paragraph("POTWIERDZENIE PRZELEWU", st["h"]), t, Spacer(1, 12),
         Paragraph("Dokument wygenerowany elektronicznie, nie wymaga podpisu ani pieczęci.", st["s"])]
    build(path, S, r, footer=False)

# ---------------------------------------------------------------- dokumenty spoza klas (gold: {})

def negatyw_pdf(path, s, r, rodzaj):
    st = styles("Arial")
    z, o = s["zam"][0], s["odw"][0]
    S = [Paragraph(f"{z['miasto']}, {kropki(s['czyn'])}", st["r"]), Paragraph(f"<b>{z['nazwa']}</b>", st["l"]),
         Paragraph(z["adres"], st["l"]), Paragraph(f"Znak sprawy: {s['nr_post']}", st["l"]), Spacer(1, 8)]
    if rodzaj == "wybor":
        S += [Paragraph("ZAWIADOMIENIE O WYBORZE NAJKORZYSTNIEJSZEJ OFERTY", st["h"]),
              Paragraph(f"Działając na podstawie art. 253 ust. 1 Pzp, Zamawiający informuje, że w postępowaniu "
                        f"pn. „{s['tytul']}” jako najkorzystniejszą wybrano ofertę złożoną przez "
                        f"{firma(r, set())}. Oferta wykonawcy {o['nazwa']} (NIP {o['nip']}) otrzymała "
                        f"{r.randint(60, 95)},00 pkt. Na czynności Zamawiającego przysługuje odwołanie do Prezesa "
                        "Krajowej Izby Odwoławczej w terminie 10 dni.", st["n"])]
    elif rodzaj == "wezwanie":
        S += [Paragraph("WEZWANIE DO ZŁOŻENIA WYJAŚNIEŃ RAŻĄCO NISKIEJ CENY", st["h"]),
              Paragraph(f"Zamawiający, działając na podstawie art. 224 ust. 1 Pzp, wzywa wykonawcę {o['nazwa']}, "
                        f"KRS {o['krs']}, do złożenia wyjaśnień dotyczących wyliczenia ceny oferty w postępowaniu "
                        f"„{s['tytul']}”, w terminie do {slownie(s['data_odw'])}. Brak wyjaśnień skutkuje "
                        "odrzuceniem oferty.", st["n"])]
    elif rodzaj == "przystapienie":
        S = [Paragraph(f"Warszawa, {kropki(s['data_odw'])}", st["r"]),
             Paragraph("<b>Prezes Krajowej Izby Odwoławczej</b>", st["l"]),
             Paragraph("ul. Postępu 17A, 02-676 Warszawa", st["l"]), Spacer(1, 8),
             Paragraph(f"<b>Odwołujący:</b> {o['nazwa']}, KRS {o['krs']}", st["l"]),
             Paragraph(f"<b>Zamawiający:</b> {z['nazwa']}", st["l"]),
             Paragraph(f"<b>Przystępujący:</b> {firma(r, set())}, NIP {nip(r)}", st["l"]),
             Paragraph("ZGŁOSZENIE PRZYSTĄPIENIA DO POSTĘPOWANIA ODWOŁAWCZEGO po stronie Zamawiającego", st["h"]),
             Paragraph(f"Na podstawie art. 525 ust. 1 Pzp zgłaszam przystąpienie do postępowania odwoławczego "
                       f"wywołanego odwołaniem wniesionym przez {o['nazwa']} w postępowaniu nr {s['nr_post']} "
                       f"pn. „{s['tytul']}”. Przystępujący ma interes w rozstrzygnięciu odwołania na korzyść "
                       "Zamawiającego, ponieważ jego oferta została wybrana jako najkorzystniejsza. "
                       "Kopię zgłoszenia przekazano Zamawiającemu i Odwołującemu.", st["n"])]
    elif rodzaj == "odpowiedz":
        S += [Paragraph("ODPOWIEDŹ NA ODWOŁANIE", st["h"]),
              Paragraph(f"Zamawiający, w odpowiedzi na odwołanie wniesione przez {o['nazwa']} w dniu "
                        f"{slownie(s['data_odw'])}, wnosi o oddalenie odwołania w całości. Zarzuty Odwołującego "
                        f"są bezzasadne. {ZARZUT_TEKST}", st["n"])]
    elif rodzaj == "faktura":
        S = [Paragraph(f"FAKTURA VAT nr FV/{r.randint(1, 300)}/2026", st["h"]),
             Paragraph(f"Sprzedawca: {s['kancelaria']}, NIP {nip(r)}", st["l"]),
             Paragraph(f"Nabywca: {o['nazwa']}, NIP {o['nip']}", st["l"]),
             Paragraph(f"Data wystawienia: {kropki(s['data_odw'])} · Termin płatności: 14 dni", st["l"]),
             Paragraph(f"Usługa: sporządzenie odwołania do KIO w sprawie {s['nr_post']} – 8 000,00 zł netto, "
                       "VAT 23% – 1 840,00 zł, brutto 9 840,00 zł. Przelew na rachunek "
                       f"{spaced_nrb(nrb(r))}.", st["n"])]
    S += [Spacer(1, 12), Sign(r), Paragraph("podpis osoby upoważnionej", st["s"])]
    build(path, S, r)

# ---------------------------------------------------------------- skan

def zeskanuj(src, dst, r):
    """Średnio wyraźny skan: 150 dpi, szarość, lekki obrót, rozmycie, szum, JPEG."""
    pdf = pdfium.PdfDocument(str(src))
    pages = []
    for page in pdf:
        img = page.render(scale=150 / 72).to_pil().convert("L")
        img = img.rotate(r.uniform(-1.4, 1.4), resample=Image.BICUBIC, expand=True, fillcolor=255)
        img = img.filter(ImageFilter.GaussianBlur(r.uniform(0.5, 0.85)))
        a = np.asarray(img).astype(np.float32)
        a = a * r.uniform(0.82, 0.9) + r.uniform(18, 32)              # wyblakły kontrast, szare tło
        a += np.random.default_rng(r.randint(0, 10**6)).normal(0, r.uniform(7, 11), a.shape)
        rng = np.random.default_rng(r.randint(0, 10**6))
        mask = rng.random(a.shape) < 0.0008                            # kropki z szyby skanera
        a[mask] = rng.uniform(40, 120, mask.sum())
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=r.randint(45, 60))
        pages.append(Image.open(io.BytesIO(buf.getvalue())).convert("L"))
    pages[0].save(dst, "PDF", save_all=True, append_images=pages[1:], resolution=150)

# ---------------------------------------------------------------- konfiguracja spraw

SPRAWY = {
    # zwykłe
    1: dict(powod=1, data_slownie=True),
    2: dict(powod=2, ted=True),
    3: dict(powod=5, dwoch_zamawiajacych=True, negatyw="wezwanie"),
    # trudne
    4: dict(powod=12, konsorcjum=True, odmiana=True, kancelaria_naglowek=True, data_na_koncu=True,
            times=True, negatyw="przystapienie", dlugi_tytul=True),
    5: dict(powod=11, tabela=True, nip_myslniki=True, bzp_spacja=True, bzp_korekta=True,
            osoba_fizyczna=True, kwota_pln=True, rachunek_spacje=True, zam_bez_krs=True,
            negatyw="faktura", kio=0),
    6: dict(powod=7, zarzut_na_2_stronie=True, pesel=True, bez_numeru_transakcji=True,
            odwolujacy_pierwszy=True, data_slownie=True, dlugi_tytul=True),
    # skany zwykłe
    7: dict(powod=3, skan=True, kio=1),
    8: dict(powod=4, skan=True, ted=True, data_slownie=True),
    9: dict(powod=9, skan=True, negatyw="wybor"),
    # skany trudne
    10: dict(powod=6, skan=True, konsorcjum=True, odmiana=True, pieczatka=True, bzp_spacja=True,
             rachunek_spacje=True),
    11: dict(powod=10, skan=True, dwoch_zamawiajacych=True, ted=True, tabela=True, times=True,
             negatyw="odpowiedz", kwota_pln=True),
    12: dict(powod=8, skan=True, osoba_fizyczna=True, data_na_koncu=True, zarzut_na_2_stronie=True,
             pesel=True, bez_numeru_transakcji=True, nip_myslniki=True, pieczatka=True),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--kio", type=Path, help="folder z orzeczeniami KIO (dokumenty spoza klas)")
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    kio = sorted(a.kio.glob("*postanowienie*.pdf")) if a.kio else []
    if a.out.exists():
        shutil.rmtree(a.out)
    tmp = a.out / "_tekst"
    for nr, cfg in SPRAWY.items():
        r = random.Random(a.seed * 100 + nr)
        s = sprawa(r, cfg)
        name = f"synt_{nr:02d}"
        inp, gold, src = a.out / "input" / name, a.out / "gold" / name, tmp / name
        for d in (inp, gold, src):
            d.mkdir(parents=True, exist_ok=True)
        docs = {"odwolanie": (odwolanie_pdf, gold_odwolanie(s)),
                "pelnomocnictwo": (pelnomocnictwo_pdf, gold_pelnomocnictwo(s)),
                "przelew": (przelew_pdf, gold_przelew(s))}
        for stem, (fn, g) in docs.items():
            fn(src / f"{stem}.pdf", s, r)
            (gold / f"{stem}.json").write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
        negs = []
        if cfg.get("negatyw"):
            stem = {"wezwanie": "wezwanie_do_wyjasnien", "przystapienie": "przystapienie",
                    "faktura": "faktura_kancelarii", "wybor": "zawiadomienie_o_wyborze",
                    "odpowiedz": "odpowiedz_na_odwolanie"}[cfg["negatyw"]]
            negatyw_pdf(src / f"{stem}.pdf", s, r, cfg["negatyw"])
            negs.append(stem)
        if "kio" in cfg and kio:
            k = kio[cfg["kio"] % len(kio)]
            shutil.copy(k, src / "postanowienie_kio.pdf")
            negs.append("postanowienie_kio")
        for stem in negs:
            (gold / f"{stem}.json").write_text("{}", encoding="utf-8")
        for pdf in sorted(src.glob("*.pdf")):
            if cfg.get("skan"):
                zeskanuj(pdf, inp / pdf.name, r)
            else:
                shutil.copy(pdf, inp / pdf.name)
        cechy = {k: v for k, v in cfg.items() if k not in ("powod",)}
        (gold / "opis.json").write_text(json.dumps(
            {"rodzaj": "skan" if cfg.get("skan") else "tekst",
             "poziom": "trudna" if nr in (4, 5, 6, 10, 11, 12) else "zwykła",
             "powod_id": cfg["powod"], "cechy": cechy, "dokumenty_spoza_klas": negs},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(name, "skan" if cfg.get("skan") else "tekst", sorted(p.name for p in inp.iterdir()))
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
