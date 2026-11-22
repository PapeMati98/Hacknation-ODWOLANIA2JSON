"""Testy odporności: obrót strony, niewiarygodna warstwa tekstowa, wartości złamane na dwie linie,
zaskarżona czynność opisana dopiero na dalszych stronach."""
from pathlib import Path

from odwolania2json import pdfio
from odwolania2json.config import load_classes
from odwolania2json.extract import CONTINUED, Extractor, extend_wrapped
from odwolania2json.pdfio import Document, Line, Page

APP = Path(__file__).resolve().parent.parent
CLASSES = {c.name: c for c in load_classes(APP / "configs" / "classes")}

PISMO = ("Działając w imieniu Odwołującego, na podstawie pełnomocnictwa załączonego do niniejszego odwołania, "
         "wnoszę odwołanie wobec czynności Zamawiającego polegającej na odrzuceniu oferty. ") * 3


def test_warstwa_tekstowa_zwykla_i_zepsuta():
    assert pdfio.text_layer_ok(PISMO)
    assert pdfio.text_layer_ok(PISMO, page_is_image=True)
    # Zepsute kodowanie fontu: obce znaki zamiast liter.
    assert not pdfio.text_layer_ok("ΩЖ♦♣◊∆∑∏ " * 40)
    # Śmieci po OCR skanera: "słowa" bez samogłosek, przypadkowa wielkość liter.
    assert not pdfio.text_layer_ok("xKqrT bnMMp zzRtk LpQw trWqz mnBv kLpTr QwRtz PlKm NbVc " * 6)
    # Słaby OCR skanera gubi polskie znaki: na stronie będącej obrazem czytamy sami, zwykły PDF zostaje.
    ascii_only = PISMO.translate(str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ"))
    assert not pdfio.text_layer_ok(ascii_only, page_is_image=True)
    assert pdfio.text_layer_ok(ascii_only)


def _line(conf: float, box: tuple[float, float, float, float]) -> Line:
    return Line("tekst linii", conf, (box[1] + box[3]) / 2, box)


def test_podejrzenie_obrotu_strony():
    wide = [_line(0.97, (0.1, 0.1 + 0.03 * i, 0.9, 0.12 + 0.03 * i)) for i in range(12)]
    short = [_line(0.98, (0.1, 0.6 + 0.03 * i, 0.3, 0.62 + 0.03 * i)) for i in range(12)]
    assert pdfio._rotations_to_try(wide + short, 1654, 2339) == ()
    # Strona bokiem: ramki linii wysokie i wąskie.
    tall = [_line(0.9, (0.1 + 0.03 * i, 0.1, 0.12 + 0.03 * i, 0.9)) for i in range(10)]
    assert pdfio._rotations_to_try(tall, 1654, 2339) == (90, 270)
    # Strona do góry nogami: krótkie linie silnik odwraca sam, długie czyta źle.
    bad_wide = [_line(0.70, l.box) for l in wide]
    assert pdfio._rotations_to_try(bad_wide + short, 1654, 2339) == (180,)
    assert pdfio._rotations_to_try([_line(0.6, l.box) for l in wide + short], 1654, 2339) == (180,)


def test_tytul_przelewu_zlamany_na_dwie_linie():
    text = "Tytuł: Wpis od odwołania, sygn. ZP.271.5.2026,\nwykonawca Budimex S.A.\nKwota: 15 000,00 PLN"
    assert (extend_wrapped("Wpis od odwołania, sygn. ZP.271.5.2026", text, [r"kwota\b.*"])
            == "Wpis od odwołania, sygn. ZP.271.5.2026, wykonawca Budimex S.A.")
    # Następna linia to kolejna rubryka: bez zmian.
    text = "Tytuł: Wpis od odwołania\nKwota: 15 000,00 PLN"
    assert extend_wrapped("Wpis od odwołania", text, [r"kwota\b.*"]) == "Wpis od odwołania"


def test_tytul_zamowienia_zlamany_w_cudzyslowie():
    closing = CLASSES["odwolanie"].output["ZamowieniePubliczne"]["tytul"]["wraps"]["closing"]
    text = ("dotyczy: postępowania o udzielenie zamówienia publicznego pn. „Dostawa leków onkologicznych\n"
            "w podziale na 9 pakietów”, nr referencyjny: DZP/138/26, ogłoszenie w Dzienniku Urzędowym UE")
    assert (extend_wrapped("Dostawa leków onkologicznych", text, [], closing)
            == "Dostawa leków onkologicznych w podziale na 9 pakietów")
    # Tytuł zamknięty w pierwszej linii albo cudzysłów w następnej linii ma własne otwarcie: bez zmian.
    text = "pn. „Dostawa leków onkologicznych”,\nw postępowaniu nr „DZP/138/26” prowadzonym w trybie"
    assert extend_wrapped("Dostawa leków onkologicznych", text, [], closing) == "Dostawa leków onkologicznych"
    text = "dotyczy: Dostawa leków onkologicznych\nw postępowaniu nr „DZP/138/26” prowadzonym w trybie"
    assert extend_wrapped("Dostawa leków onkologicznych", text, [], closing) == "Dostawa leków onkologicznych"
    text = "dotyczy: Dostawa leków onkologicznych\nnr referencyjny: DZP/138/26"
    assert extend_wrapped("Dostawa leków onkologicznych", text, [], closing) == "Dostawa leków onkologicznych"


class _Backend:
    """Model: na dwóch pierwszych stronach nie znajduje czynności, na dalszych - znajduje."""
    def __init__(self):
        self.calls = []

    def fill(self, system, static_user, doc_text, sections, **kwargs):
        self.calls.append((doc_text, sections))
        if len(self.calls) == 1:
            return "## OdwolanieKIO\ndata: 11 września 2026 r.\nczynnosc_dzien: -\nczynnosc_powod_id: -\nmiejscowosc: Lublin"
        return "## OdwolanieKIO\nczynnosc_dzien: 3 września 2026 r.\nczynnosc_powod_id: 7"


class _Loaded(Document):
    """Dokument wczytany w całości: nie ma pliku, z którego dałoby się doczytać strony."""
    def ensure_pages(self, count: int) -> None:
        pass


def _doc(pages: list[str]) -> Document:
    return _Loaded("brak.pdf", [Page(i + 1, "text", text) for i, text in enumerate(pages)])


def test_czynnosc_opisana_na_dalszych_stronach():
    cls = CLASSES["odwolanie"]
    pages = ["Lublin, dnia 11 września 2026 r.\nPrezes Krajowej Izby Odwoławczej\nODWOŁANIE", "I. Wprowadzenie",
             "Zarzuty\nZamawiający w dniu 3 września 2026 r. zaniechał odrzucenia oferty wykonawcy.", "Uzasadnienie"]
    backend = _Backend()
    data, _, answer = Extractor(backend).run(_doc(pages), cls)
    assert len(backend.calls) == 2 and CONTINUED in answer
    text, sections = backend.calls[1]
    assert "strona 3" in text and "strona 1" not in text
    assert sections == [("OdwolanieKIO", False, ["czynnosc_dzien", "czynnosc_powod_id"])]
    assert data["OdwolanieKIO"]["czynnosc_dzien"] == "2026-09-03"
    assert data["OdwolanieKIO"]["czynnosc_opis"] == "Zaniechanie odrzucenia oferty"
    assert data["OdwolanieKIO"]["data"] == "2026-09-11"
    # Dokument dwustronicowy: nie ma czego doczytać, model nie jest pytany drugi raz.
    backend = _Backend()
    Extractor(backend).run(_doc(pages[:2]), cls)
    assert len(backend.calls) == 1
