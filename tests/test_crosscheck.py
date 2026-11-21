"""Testy kontroli krzyżowej, dopasowania do tekstu i parsera formularza."""
from pathlib import Path

from odwolania2json.config import load_classes
from odwolania2json.crosscheck import (apply_field_rules, case_findings, get_values, load_rules, resolve_duplicates,
                                       review_entries)
from odwolania2json.extract import needs_second_read, parse_sheet, value_in_text, verify_text
from odwolania2json.textmatch import person_in, second_read, snap_span
from odwolania2json.validators import norm_person, norm_text

APP = Path(__file__).resolve().parent.parent
CLASSES = {c.name: c for c in load_classes(APP / "configs" / "classes")}
RULES = load_rules(APP / "configs" / "cross_checks.yaml")


def test_person_titles_removed():
    assert norm_person("adw. Jan Kowalski").value == "Jan Kowalski"
    assert norm_person("r. pr. Anna Nowak").value == "Anna Nowak"
    assert norm_person("Jan Kowalski, radca prawny").value == "Jan Kowalski"
    assert norm_person("Ewa Kowalska-Nowak").value == "Ewa Kowalska-Nowak"


def test_person_matches_inflected_text():
    text = "udzielam pełnomocnictwa adw. Janowi Kowalskiemu oraz Annie Nowak"
    assert person_in("Jan Kowalski", text) and person_in("Anna Nowak", text)
    assert not person_in("Piotr Lis", text)


def test_value_replaced_by_literal_fragment():
    text = "Kancelaria Lex Nova spółka z ograniczoną odpowiedzialnością, z siedzibą w Warszawie"
    assert snap_span("Kancelaria Lex Nova spółka z ograniczoną odpowiedzialność", text) == \
        "Kancelaria Lex Nova spółka z ograniczoną odpowiedzialnością"
    assert snap_span("Zupełnie Inna Firma S.A.", text) is None
    assert verify_text("Zupełnie Inna Firma S.A.", text, "text", "ok", "")[0] is None


def test_repeated_key_starts_new_list_item():
    sheet = "## mocodawca 1\ndata.nazwa: ACME S.A.\n## pelnomocnicy 1\nimie_nazwisko: Adam Nowak\npesel: -\n" \
            "imie_nazwisko: Anna Kot\npesel: 90010112345"
    raw = parse_sheet(sheet, CLASSES["pelnomocnictwo"])
    assert [p["imie_nazwisko"] for p in raw["pelnomocnicy"]] == ["Adam Nowak", "Anna Kot"]


def test_second_ocr_read():
    primary, alt_same, alt_diff = "KRS: 0000123456 z dnia 16.06.2025", "KRS 0000123456, 16.06.2025", "KRS: 0000128456"
    assert second_read("0000123456", primary, alt_same) == "zgodne"
    assert second_read("0000123456", primary, alt_diff) == "rozbiezne"
    assert second_read("0000123456", primary, "zupełnie inna linia tekstu") == "brak"    # linia nieodczytana
    assert second_read("0000123456", primary, "KRS: OOOO123456") == "zgodne"            # O zamiast 0 to ten sam odczyt
    assert second_read("9999999999", primary, alt_same) is None      # wartości nie ma w odczycie głównym
    assert needs_second_read("krs", "0000123456", "ok") and needs_second_read("date", "16.06.2025", "ok")
    assert not needs_second_read("nip", "5260250274", "ok")           # poprawna suma kontrolna wystarcza
    assert not needs_second_read("person", "Jan Kowalski", "ok")


def test_duplicate_identifier_kept_only_near_its_name():
    cls = CLASSES["odwolanie"]
    text = ("Odwołujący: ALFA Sp. z o.o., KRS 0000111111, NIP 5260250274\n" + "x " * 400 +
            "Zamawiający: Gmina Beta, NIP 1132853869")
    data = {"Odwolujacy": [{"nazwa": "ALFA Sp. z o.o.", "nip": "5260250274", "krs": "0000111111"}],
            "Zamawiajacy": [{"nazwa": "Gmina Beta", "nip": "5260250274"}]}
    trace = [{"pole": "Odwolujacy[0].nip", "status": "ok"}, {"pole": "Zamawiajacy[0].nip", "status": "ok"}]
    resolve_duplicates(cls, data, trace, text)
    assert data["Odwolujacy"][0]["nip"] == "5260250274"
    assert data["Zamawiajacy"][0]["nip"] is None
    assert trace[1]["status"] == "niezweryfikowane"


def test_same_account_in_both_fields_is_rejected():
    cls = CLASSES["przelew"]
    nrb = "61109010140000071219812874"
    data = {"przelew_bankowy": {"z_rachunku": nrb, "na_rachunek": nrb, "tytul": "wpis od odwołania"}}
    trace = [{"pole": "przelew_bankowy.z_rachunku", "status": "ok"}, {"pole": "przelew_bankowy.na_rachunek", "status": "ok"}]
    resolve_duplicates(cls, data, trace, f"Z rachunku {nrb} na rachunek {nrb}")
    assert data["przelew_bankowy"]["z_rachunku"] is None and data["przelew_bankowy"]["na_rachunek"] is None
    assert len(review_entries("przelew.pdf", [dict(t, surowa=nrb) for t in trace])) == 2


def test_cross_document_rules():
    odw = {"OdwolanieKIO": {"data": "2025-06-16", "czynnosc_dzien": "2025-06-20"},
           "Odwolujacy": [{"nazwa": "ALFA Sp. z o.o.", "krs": "0000111111", "nip": "5260250274",
                           "pelnomocnik": {"imie_nazwisko": "Jan Kowalski"}}]}
    pel = {"mocodawca": [{"data": {"nazwa": "ALFA spółka z o.o.", "krs": "0000222222", "nip": "5260250274"}}],
           "pelnomocnicy": [{"imie_nazwisko": "Jan Kowalski"}, {"imie_nazwisko": "Anna Kot"}]}
    prz = {"przelew_bankowy": {"kwota": 15500.0, "data_operacji": "2025-06-15"}}
    assert get_values(pel, "pelnomocnicy[].imie_nazwisko") == ["Jan Kowalski", "Anna Kot"]
    found = {f["regula"] for f in case_findings(RULES, [("o.pdf", "odwolanie", odw), ("p.pdf", "pelnomocnictwo", pel),
                                                        ("t.pdf", "przelew", prz)])}
    assert found == {"odwolujacy-mocodawca-krs", "czynnosc-przed-odwolaniem"}
    # brak drugiego dokumentu = reguły między dokumentami są pomijane
    assert {f["regula"] for f in case_findings(RULES, [("o.pdf", "odwolanie", odw)])} == {"czynnosc-przed-odwolaniem"}
    amount = [{"id": "kwota", "kind": "one_of", "field": "przelew:przelew_bankowy.kwota", "values": [7500, 15000]}]
    assert len(case_findings(amount, [("t.pdf", "przelew", prz)])) == 1


def test_value_must_be_present_in_document():
    text = "Rzeszów, dnia 5 czerwca 2026 roku. Wpis w kwocie 15 000,00 PLN. Ogłoszenie nr 2026/BZP 00123456."
    assert value_in_text("date", "5 czerwca 2026 roku", "2026-06-05", text)
    assert value_in_text("date", "05.06.2026", "2026-06-05", text)             # inny zapis tej samej daty
    assert not value_in_text("date", "16 czerwca 2025 r.", "2025-06-16", text)  # data przepisana z instrukcji
    assert value_in_text("amount", "15000 zł", 15000.0, text)
    assert not value_in_text("amount", "7 500,00", 7500.0, text)
    assert value_in_text("bzp", "2026/BZP00123456", "2026/BZP00123456", text)


def test_field_rules_from_yaml():
    odw = {"OdwolanieKIO": {"data": None, "miejscowosc": "Warszawa", "czynnosc_dzien": None, "czynnosc_powod_id": 1}}
    trace = [{"pole": "OdwolanieKIO.miejscowosc", "status": "ok", "surowa": "Warszawa"}]
    apply_field_rules(CLASSES["odwolanie"], odw, trace)
    assert odw["OdwolanieKIO"]["miejscowosc"] is None and trace[0]["status"] == "niezweryfikowane"

    pel = {"mocodawca": [{"data": {"nazwa": "ALFA"}, "podpisujacy": [{"imie_nazwisko": "Halina Mazur"},
                                                                    {"imie_nazwisko": "Cezary Walczak"}]}],
           "pelnomocnicy": [{"imie_nazwisko": "Cezary Walczak", "pesel": None}]}
    apply_field_rules(CLASSES["pelnomocnictwo"], pel, [])
    assert pel["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Halina Mazur"}]
    assert pel["pelnomocnicy"] == [{"imie_nazwisko": "Cezary Walczak", "pesel": None}]


def test_quotes_are_not_part_of_names():
    assert norm_text('BIOARCUS"Spółka z o.o.').value == "BIOARCUS Spółka z o.o."
    assert norm_text("„ALFA” S.A.").value == "ALFA S.A."


def _scan(line: str, conf: float, alt: str):
    """Jednostronicowy skan z jedną linią odczytu głównego i gotowymi odczytami alternatywnymi."""
    from odwolania2json.pdfio import ALT_DPIS, Document, Line, Page
    return Document("", [Page(1, "ocr", line, [Line(line, conf, 0.5)], 0, {dpi: alt for dpi in ALT_DPIS})])


def test_bad_checksum_number_kept_only_with_high_confidence():
    from odwolania2json import extract
    bad = "9998031631"                                   # NIP ze złą sumą kontrolną, bez jednoznacznej poprawki
    line = f"NIP: {bad}"
    check = lambda doc: extract.cross_check_ocr(doc, "nip", bad, doc.text(None), None, "nieczytelne", "nip: zła suma")
    value, status, _, conf = check(_scan(line, 0.99, line))
    assert (value, status, conf["poziom"]) == (bad, "ostrzezenie", "wysoka")       # pewna linia + zgodny inny odczyt
    value, status, _, conf = check(_scan(line, 0.90, line))
    assert (value, status, conf["poziom"]) == (None, "nieczytelne", "srednia")     # linia mało pewna
    from odwolania2json.validators import nip_ok
    other = next(v for v in (bad[:6] + d + bad[7:] for d in "0123456789") if v != bad and not nip_ok(v))
    value, status, _, conf = check(_scan(line, 0.99, f"NIP: {other}"))
    assert (value, status, conf["poziom"]) == (None, "nieczytelne", "niska")       # inny odczyt daje inną wartość
    extract.CHECKSUM_POLICY = "strict"
    try:
        assert check(_scan(line, 0.99, line))[0] is None
    finally:
        extract.CHECKSUM_POLICY = "confidence"


def test_value_without_checksum_follows_confidence():
    from odwolania2json import extract
    line = "KRS: 0000123456"
    check = lambda doc: extract.cross_check_ocr(doc, "krs", "0000123456", doc.text(None), "0000123456", "ok", "")
    assert check(_scan(line, 0.99, line))[1] == "ok"
    assert check(_scan(line, 0.90, line))[1] == "ostrzezenie"                      # zostaje, ale do sprawdzenia
    assert check(_scan(line, 0.99, "zupełnie inna linia"))[1] == "ostrzezenie"     # inny odczyt nie zawiera linii
    assert check(_scan(line, 0.99, "KRS: 0000128456"))[0] is None                  # sprzeczne odczyty


def test_layout_puts_margin_label_before_its_block_and_marks_redactions():
    from odwolania2json.pdfio import REDACTED, Line, layout_text
    lines = [Line("Spółka z o.o.", 0.99, 0.268, (0.37, 0.261, 0.69, 0.276)),
             Line("Warszawa", 0.99, 0.282, (0.47, 0.275, 0.55, 0.290)),
             Line("Odwołujący:", 0.99, 0.290, (0.11, 0.282, 0.22, 0.299)),
             Line("KRS:", 0.99, 0.297, (0.25, 0.289, 0.31, 0.305)),
             Line("tel.", 0.99, 0.313, (0.25, 0.305, 0.29, 0.321)),
             Line("fax.", 0.99, 0.314, (0.44, 0.307, 0.47, 0.320)),
             Line("Zamawiający: Gmina Beta", 0.99, 0.418, (0.11, 0.411, 0.60, 0.426))]
    text = layout_text(lines, [(0.25, 0.259, 0.37, 0.276), (0.30, 0.292, 0.40, 0.305)])
    assert text.splitlines()[:5] == ["Odwołujący:", f"{REDACTED} Spółka z o.o.", "Warszawa", f"KRS: {REDACTED}", "tel. fax."]
    assert text.split("\n\n")[1] == "Zamawiający: Gmina Beta"


def test_fragment_next_to_redaction_is_not_a_value():
    from odwolania2json.extract import only_beside_redaction
    text = "KANCELARIA PRAWNA [ZAKRYTE]\nWarszawa, dnia 16 czerwca 2025 r.\nKancelaria Prawna [ZAKRYTE] – Radca Prawny\n" \
           "Zamawiający:\nGmina Beta\n[ZAKRYTE] Warszawa"
    assert only_beside_redaction("Kancelaria Prawna", text)
    assert not only_beside_redaction("Warszawa", text)          # jest też czyste wystąpienie w nagłówku
    assert not only_beside_redaction("Gmina Beta", text)
    assert verify_text("Kancelaria Prawna", text, "text", "ok", "")[0] is None


def test_fragment_after_redaction_is_not_a_value():
    from odwolania2json.extract import only_beside_redaction
    assert only_beside_redaction("Spółka z o.o.", "Odwołujący:\n[ZAKRYTE] Spółka z o.o.\n[ZAKRYTE] Warszawa")


def test_visual_reader_confirms_only_a_whole_number_fragment():
    from odwolania2json.vision import adjust, judge
    assert judge("krs", "0000123456", "KRS: 0000123456, NIP: 521-300-12-34") == "zgodne"
    assert judge("nip", "5213001234", "KRS: 0000123456, NIP: 521-300-12-34") == "zgodne"
    assert judge("krs", "0000123456", "KRS: 00001234567") == "inne"          # podciąg dłuższego numeru nie potwierdza
    assert judge("krs", "0000123456", "KRS: 0000128456") == "inne"
    assert judge("krs", "0000123456", "Sąd Rejonowy w Warszawie") == "niezwiazane"
    assert judge("krs", "0000123456", "0000123456 5213001234") == "niezwiazane"   # dwa numery rozdzielone samą spacją
    assert judge("nrb", "61109010140000071219812874", "61 1090 1014 0000 0712 1981 2874") == "zgodne"
    assert judge("date", "2025-06-16", "Warszawa, dnia 16 czerwca 2025 r.") == "zgodne"
    assert judge("date", "2025-06-16", "Warszawa, dnia 18 czerwca 2025 r.") == "inne"
    assert judge("text", "KIO 1234/25", "Sygn. akt: KIO 1234/25") == "zgodne"
    assert judge("text", "KIO 1234/25", "Sygn. akt: KIO 1284/25") == "inne"
    assert judge("text", "KIO 1234/25", "Sygn. akt KIO 1234/25, Warszawa") == "zgodne"
    assert judge("text", "KIO 1234", "Sygn. akt: KIO 1234/25") == "inne"     # obcięta wartość nie jest zgodnością
    assert judge("text", "ZP.271", "nr referencyjny sprawy ZP.271.5.2026") != "zgodne"
    assert judge("text", "KIO 1234/25", "Prezes Krajowej Izby Odwoławczej") == "niezwiazane"
    assert judge("text", "ZP.271.5.2026", "(postępowanie nr ZP.271.5.2026)") == "zgodne"
    assert adjust("srednia", "zgodne") == "wysoka" and adjust("niska", "zgodne") == "srednia"
    assert adjust("srednia", "inne") is None and adjust("srednia", "niezwiazane") == "srednia"


def test_dark_share_detects_a_black_box():
    import numpy as np
    from odwolania2json.vision import DARK_SHARE, dark_share
    page = np.full((40, 400), 255, dtype=np.uint8)
    page[14:26:3, 10:390:7] = 0                      # rzadki "tekst"
    assert dark_share(page) < DARK_SHARE
    page[8:32, 100:300] = 0                          # czarny prostokąt
    assert dark_share(page) > DARK_SHARE


def test_visual_reader_confirms_or_vetoes_but_never_writes_a_value():
    from odwolania2json import extract

    class Fake:
        def __init__(self, verdict):
            self.verdict, self.asked = verdict, 0

        def check(self, doc, line, kind, value):
            self.asked += 1
            return self.verdict, "odczyt testowy"

    line = "KRS: 0000123456"
    check = lambda doc: extract.cross_check_ocr(doc, "krs", "0000123456", doc.text(None), "0000123456", "ok", "")
    bad = "9998031631"
    check_bad = lambda doc: extract.cross_check_ocr(doc, "nip", bad, doc.text(None), None, "nieczytelne", "nip: zła suma")
    try:
        extract.VISUAL_READER = reader = Fake("zgodne")
        value, status, _, conf = check(_scan(line, 0.90, line))                 # średnia -> wysoka
        assert (value, status, conf["poziom"]) == ("0000123456", "ok", "wysoka")
        value, status, _, conf = check(_scan(line, 0.99, "KRS: 0000128456"))    # niska -> średnia: zostaje z ostrzeżeniem
        assert (value, status, conf["poziom"]) == ("0000123456", "ostrzezenie", "srednia")
        check(_scan(line, 0.99, line))                                          # wysoka: czytelnik nie jest pytany
        assert reader.asked == 2
        value, status, _, conf = check_bad(_scan(f"NIP: {bad}", 0.90, f"NIP: {bad}"))
        assert value is None and reader.asked == 2                              # zła suma + null: zgodność niczego nie uchyla
        extract.VISUAL_READER = Fake("inne")
        assert check(_scan(line, 0.90, line))[0] is None                        # weto
        value, status, note, _ = check_bad(_scan(f"NIP: {bad}", 0.99, f"NIP: {bad}"))
        assert (value, status) == (bad, "ostrzezenie") and "odczyt testowy" in note   # reguła właściciela bez zmian
        extract.VISUAL_READER = Fake("zakryte")
        assert check(_scan(line, 0.90, line))[0] is None
        extract.VISUAL_READER = Fake("niezwiazane")
        assert check(_scan(line, 0.90, line))[1] == "ostrzezenie"               # bez zmian
    finally:
        extract.VISUAL_READER = None


def test_visual_text_agreement_wins_over_similar_neighbour():
    from odwolania2json.vision import judge
    assert judge("text", "KIO 100/25", "KIO 100/25 i KIO 200/25") == "zgodne"


def test_header_date_must_stand_in_its_own_line():
    import yaml
    from pathlib import Path
    from odwolania2json.extract import line_context_ok
    spec = yaml.safe_load((Path(__file__).resolve().parent.parent / "configs/classes/odwolanie.yaml").read_text(encoding="utf-8"))
    patterns = spec["output"]["OdwolanieKIO"]["data"]["line_pattern"]
    text = ("Warszawa, dnia 16 czerwca 2025 r.\nOdwołujący:\nAlfa sp. z o.o.\n"
            "Zamawiający w dniu 10 czerwca 2025 roku poinformował o odrzuceniu oferty.\n"
            "Na podstawie ustawy z dnia 11 września\n2019 r. wnoszę odwołanie.")
    assert line_context_ok(patterns, "date", "2025-06-16", text)
    assert not line_context_ok(patterns, "date", "2025-06-10", text)       # data ze zdania w treści
    assert not line_context_ok(patterns, "date", "2019-09-11", text)       # data rozbita między linie
    assert line_context_ok(patterns, "date", "2025-06-16", "Zielona Góra, 16.06.2025")
    assert line_context_ok(patterns, "date", "2025-06-16", "16 czerwca 2025 r.")


def test_named_action_decides_dictionary_entry():
    import yaml
    from pathlib import Path
    from odwolania2json.extract import decide_from_text
    spec = yaml.safe_load((Path(__file__).resolve().parent.parent / "configs/classes/odwolanie.yaml").read_text(encoding="utf-8"))
    rule = spec["output"]["OdwolanieKIO"]["czynnosc_powod_id"]["decide"]
    pick = lambda text: (decide_from_text(rule, text) or (None,))[0]
    assert pick("Zamawiający w dniu 3 lipca 2026 roku opublikował Specyfikację\nWarunków Zamówienia. Zarzut nr 1: Opis Przedmiotu Zamówienia jest niepełny.") == 4
    assert pick("Zamawiający w dniu 3 lipca 2026 roku udostępnił Opis Przedmiotu Zamówienia.") == 11
    assert pick("Zamawiający w dniu 3 lipca 2026 roku nie odrzucił oferty złożonej przez wykonawcę Beta.") == 7
    assert pick("Zamawiający w dniu 3 lipca 2026 roku poinformował o odrzuceniu oferty złożonej przez Odwołującego.") == 1
    assert pick("Zamawiający w dniu 3 lipca 2026 roku opublikował dokumenty, w tym Opis Przedmiotu Zamówienia do SWZ.") is None   # dwie pozycje
    assert pick("Odwołujący wnosi o uwzględnienie odwołania.") is None


def test_visual_reader_tolerates_spacing_and_crops_around_the_value():
    from odwolania2json.vision import judge, value_span
    assert judge("bzp", "2025/BZP00270698", "Nr ogłoszenia w BZP: 2025/BZP 00270698 z dnia 10 czerwca 2025 r.") == "zgodne"
    assert judge("bzp", "2025/BZP 00270698", "Nr ogłoszenia w BZP: 2025/BZP 00270598 z dnia") == "inne"
    assert judge("text", "BZP00270698", "2025/BZP 00270698") != "zgodne"            # fragment wyrazu nie potwierdza
    line = "Krajowego Rejestru Sądowego pod numerem KRS 9993682204, posiadającej NIP 9999142626 oraz"
    left, right = value_span(line, "krs", "9993682204")
    assert left < line.index("9993682204") / len(line) and right > (line.index("9993682204") + 10) / len(line)
    assert right - left < 0.5
    assert value_span("KRS: 0000123456", "krs", "0000123456") is None               # krótka linia: w całości
    assert value_span("Warszawa, dnia 16 czerwca 2025 r. oraz dalszy długi tekst tej samej linii pisma", "date", "2025-06-16")[0] < 0.1


def test_first_listed_action_decides_kind_and_day():
    import yaml
    from odwolania2json.extract import decide_from_text, value_from_scope
    spec = yaml.safe_load((APP / "configs/classes/odwolanie.yaml").read_text(encoding="utf-8"))["output"]["OdwolanieKIO"]
    text = ("Poznań, dnia 11 września 2026 roku\nna podstawie ustawy z dnia 11 września 2019 r. wnoszę odwołanie\nwobec:\n"
            "1. projektowanych postanowień umowy (PPU), stanowiących załącznik nr 4 do SWZ, opublikowanych w\n"
            "dniu 14.03.2026 r.;\n2. zaniechania odrzucenia oferty wykonawcy Beta;\n"
            "Informacja o zaskarżonej czynności została przekazana Odwołującemu w dniu 15.03.2026 r.")
    assert decide_from_text(spec["czynnosc_powod_id"]["decide"], text)[0] == 12          # liczy się punkt pierwszy
    assert value_from_scope(spec["czynnosc_dzien"]["decide"], text, "date")[0] == "14.03.2026"
    other = text.replace("1. projektowanych postanowień umowy (PPU), stanowiących załącznik nr 4 do SWZ, opublikowanych w\ndniu 14.03.2026 r.;",
                         "1. zaniechania wykluczenia wykonawcy Gamma;")
    assert decide_from_text(spec["czynnosc_powod_id"]["decide"], other)[0] == 8
    assert value_from_scope(spec["czynnosc_dzien"]["decide"], other, "date")[0] == "15.03.2026"   # zdanie o terminie
    assert value_from_scope(spec["czynnosc_dzien"]["decide"], "Zamawiający w dniu 3 lipca 2026 roku odrzucił ofertę.", "date") is None


def test_skewed_scan_is_laid_out_in_straightened_coordinates():
    import math
    from odwolania2json.pdfio import Line, fix_ocr, layout_text, skew_angle, straighten
    width, height, angle = 1654, 2339, math.radians(-1.5)

    def poly(x0, y0, x1, h=30):                      # linia tekstu na stronie obróconej o `angle`
        dy = (x1 - x0) * math.tan(angle)
        return [(x0, y0), (x1, y0 + dy), (x1, y0 + dy + h), (x0, y0 + h)]

    rows = [("1. pierwszy punkt wyliczenia, który zajmuje całą szerokość strony i kończy się w", poly(140, 200, 1450)),
            ("dniu 14.03.2026 r.;", poly(175, 236, 420)),
            ("2. drugi punkt wyliczenia, równie długi jak pierwszy, na całą szerokość strony;", poly(140, 272, 1450)),
            ("3. trzeci punkt wyliczenia, również długi, sięgający prawego marginesu strony;", poly(140, 308, 1450))]
    found = skew_angle([p for _, p in rows], width)
    assert abs(math.degrees(found) + 1.5) < 0.1
    lines = []
    for text, p in rows:
        xs, ys = [x for x, _ in p], [y for _, y in p]
        box = (min(xs) / width, min(ys) / height, max(xs) / width, max(ys) / height)
        lay = straighten(p, found, width, height)
        lines.append(Line(text, 0.99, (lay[1] + lay[3]) / 2, box, lay=lay))
    assert layout_text(lines, []).splitlines() == [t for t, _ in rows]
    crooked = [Line(l.text, l.conf, (l.box[1] + l.box[3]) / 2, l.box) for l in lines]      # bez prostowania linie się mieszają
    assert layout_text(crooked, []).splitlines() != [t for t, _ in rows]
    assert fix_ocr("Kalinex Logistyka Sp. z 0.o.") == "Kalinex Logistyka Sp. z o.o."
    assert fix_ocr("Sp. z o.o. z 0.5 udziału") == "Sp. z o.o. z 0.5 udziału"


def test_two_margin_labels_stay_with_their_own_rows():
    from odwolania2json.pdfio import Line, layout_text
    lines = [Line("Odwołujący:", 0.99, 0.250, (0.18, 0.243, 0.30, 0.258)),
             Line("Alfa sp. k.", 0.99, 0.249, (0.33, 0.241, 0.59, 0.257)),
             Line("ul. Polna 1", 0.99, 0.264, (0.33, 0.257, 0.53, 0.272)),
             Line("Zamawiający:", 0.99, 0.280, (0.18, 0.273, 0.30, 0.288)),
             Line("Gmina Beta", 0.99, 0.279, (0.33, 0.272, 0.60, 0.287)),
             Line("ul. Leśna 2", 0.99, 0.294, (0.33, 0.287, 0.53, 0.302))]
    assert layout_text(lines, []).splitlines() == ["Odwołujący: Alfa sp. k.", "ul. Polna 1", "Zamawiający: Gmina Beta", "ul. Leśna 2"]


def test_spelling_follows_the_majority_of_reads_and_known_places():
    from odwolania2json.textmatch import majority_spelling, restore_known
    reads = ["reprezentowana przez: Lukasz Sosnowski – Prezes Zarządu\nŁukasz Sosnowski – Prezes Zarządu",
             "reprezentowana przez: Łukasz Sosnowski\nŁukasz Sosnowski"]
    assert majority_spelling("Lukasz Sosnowski", reads) == "Łukasz Sosnowski"
    assert majority_spelling("Szymon Zawadżki", ["Szymon Zawadżki – Prokurent\nSzymon Zawadzki", "Szymon Zawadzki\nSzymon Zawadzki"]) == "Szymon Zawadzki"
    assert majority_spelling("Jan Lis", ["Jan Lis", "Jan Liś"]) == "Jan Lis"                    # remis: bez zmian
    assert majority_spelling("KRZYSZTOF JODLOWSKI", ["Krzysztof Jodłowski", "Krzysztof Jodłowski, KRZYSZTOF JODLOWSKI"]) == "KRZYSZTOF JODŁOWSKI"
    assert restore_known("Lódź", ["Łódź", "Warszawa"]) == "Łódź"
    assert restore_known("Zielonków", ["Łódź", "Warszawa"]) == "Zielonków"


def test_dates_and_numbers_in_bank_printouts():
    from odwolania2json.pdfio import fix_ocr
    from odwolania2json.validators import norm_amount, norm_date
    assert norm_date("2026.07.15").value == "2026-07-15"
    assert norm_date("20 04 2026").value == "2026-04-20"
    assert norm_date("DA.ZP.242.13.2026").value is None
    assert norm_amount("-17,00 PLN").value == 17.0 and norm_amount("-10 000,00 PLN").value == 10000.0
    assert fix_ocr("KRS: 9994328o29, Kraków (3o-799)") == "KRS: 9994328029, Kraków (30-799)"


def test_representative_fields_need_the_flag_one_level_up():
    odw = {"OdwolanieKIO": {"data": "2026-06-05"},
           "Odwolujacy": [{"nazwa": "Alfa Sp. z o.o.", "przez-pelnomocnika": 0,
                           "pelnomocnik": {"imie_nazwisko": None, "nazwa": None, "mail": "biuro@alfa.example"}},
                          {"nazwa": "Beta S.A.", "przez-pelnomocnika": 1,
                           "pelnomocnik": {"imie_nazwisko": "Jan Kowalski", "nazwa": None, "mail": "jan@kancelaria.example"}}]}
    apply_field_rules(CLASSES["odwolanie"], odw, [])
    assert odw["Odwolujacy"][0]["pelnomocnik"]["mail"] is None
    assert odw["Odwolujacy"][1]["pelnomocnik"]["mail"] == "jan@kancelaria.example"


def test_comma_inside_an_email_address_is_a_dot():
    from odwolania2json.pdfio import fix_ocr
    assert fix_ocr("e-mail: a,wrobel@wrobel-kancelaria.example, tel. 22") == "e-mail: a.wrobel@wrobel-kancelaria.example, tel. 22"
    assert fix_ocr("jan@alfa.example, anna@beta.example") == "jan@alfa.example, anna@beta.example"


def test_label_or_other_kind_of_data_is_not_a_value():
    import re
    import yaml
    prz = yaml.safe_load((APP / "configs/classes/przelew.yaml").read_text(encoding="utf-8"))["output"]["przelew_bankowy"]
    pel = yaml.safe_load((APP / "configs/classes/pelnomocnictwo.yaml").read_text(encoding="utf-8"))["output"]
    hit = lambda spec, value: any(re.fullmatch(p, value, flags=re.IGNORECASE) for p in spec["reject"])
    assert hit(prz["tytul"], "Szczegóły płatności") and hit(prz["tytul"], "Szczegóły zlecenia") and hit(prz["tytul"], "Tytułem")
    assert not hit(prz["tytul"], "Wpis od odwołania, ZP/12/2026, REGIONALNE CENTRUM ZDROWIA")
    assert not hit(prz["tytul"], "opłata skarbowa od pełnomocnictwa dla adw. Rafał Malinowski")
    assert hit(prz["numer_transakcji"], "WPIS OD ODW., ZAM: KOMENDA WOJEWÓDZKA, PN/58/2026/DOS") and hit(prz["numer_transakcji"], "Opis")
    assert not hit(prz["numer_transakcji"], "CEN9057564440515") and not hit(prz["numer_transakcji"], "305494")
    person = pel["pelnomocnicy"][0]["imie_nazwisko"]
    assert hit(person, "Kancelaria Radcy Prawnego Aleksandra Rybak") and hit(person, "Prezes Zarządu") and hit(person, "Jan Kowalski 2")
    assert not hit(person, "Żaneta Rybak") and not hit(person, "Ewa Kowalska-Nowak") and not hit(person, "Jan Prezesowski")


def test_numbered_principals_set_the_expected_list_length():
    from odwolania2json.extract import expected_items
    cls = {c.name: c for c in load_classes(Path(__file__).resolve().parent.parent / "configs" / "classes")}["pelnomocnictwo"]
    consortium = ("PEŁNOMOCNICTWO\nWykonawcy wspólnie ubiegający się o udzielenie zamówienia (Konsorcjum): 1) Alfa sp. z o.o., "
                  "KRS 9995540127; 2) Beta sp.j., KRS 9997108834 (dalej łącznie: „Mocodawca”), udzielają pełnomocnictwa: "
                  "1. Jan Kowalski, 2. Anna Nowak")
    assert expected_items(cls, consortium) == {"mocodawca": 2}
    # jeden mocodawca, pełnomocnicy wyliczeni po zdaniu udzielającym pełnomocnictwa - reguła niczego nie wymusza
    single = "PEŁNOMOCNICTWO\nAlfa sp. z o.o., KRS 9995540127, udziela pełnomocnictwa:\n1) Jan Kowalski,\n2) Anna Nowak"
    assert expected_items(cls, single) == {}
    # wyliczenie członków zarządu przed zdaniem udzielającym pełnomocnictwa to nie lista mocodawców
    board = ("PEŁNOMOCNICTWO\nAlfa sp. z o.o., KRS 9995540127, NIP 9992284611, reprezentowana przez: 1) Jan Kowalski - Prezes "
             "Zarządu, 2) Anna Nowak - Prokurent, udziela pełnomocnictwa: adw. Piotr Zalewski")
    assert expected_items(cls, board) == {}


def test_model_review_only_flags_or_vetoes_and_never_writes_a_value():
    from odwolania2json.sanity import accept_correction, review

    class Backend:
        def __init__(self):
            self.asked = []

        def say(self, prompt, max_tokens=48):
            self.asked.append(prompt)
            return "NIE" if "Szczegóły płatności" in prompt else "TAK"

    spec = {"przelew": {"tytul": {"type": "string", "check": "treść tytułu przelewu"},
                        "kwota": {"type": "string"}}}
    text = "Szczegóły płatności\nopłata skarbowa od pełnomocnictwa\nKwota 17,00 PLN"
    for veto, kept in ((False, "Szczegóły płatności"), (True, None)):
        data = {"przelew": {"tytul": "Szczegóły płatności", "kwota": "17,00"}}
        trace = [{"pole": "przelew.tytul", "wartosc": "Szczegóły płatności", "status": "ok"}]
        backend = Backend()
        assert review(backend, text, spec, data, trace, veto=veto) == 1      # pytane są tylko pola z `check`
        assert data["przelew"] == {"tytul": kept, "kwota": "17,00"}
        assert trace[0]["status"] == ("niezweryfikowane" if veto else "ostrzezenie")
    # korekta zapisu: tylko znaki mylone przez OCR, nigdy inne słowo ani inna forma prawna
    assert accept_correction("Lukasz Sosnowski", "Łukasz Sosnowski")
    assert accept_correction("Alfa sp. z 0.o.", "Alfa sp. z o.o.")
    assert not accept_correction("Arkomed Serwis spolka akcyjna", "Arkomed Serwis sp. z o.o.")
    assert not accept_correction("Kancelaria Bak sp.p.", "Kancelaria Bak sp. o. o.")


def test_name_ends_before_seat_and_registry_details():
    spec = CLASSES["pelnomocnictwo"].output["mocodawca"][0]["data"]["nazwa"]
    text = ("PEŁNOMOCNICTWO\nArkomed Serwis spółka akcyjna z siedzibą w Białystok (15-629), ul. Kwiatowa 116/31, "
            "wpisana do rejestru pod numerem KRS: 9991022552")
    from odwolania2json.extract import check_leaf
    from odwolania2json.pdfio import Document, Page
    doc = Document("", [Page(1, "text", text)])
    for raw in ("Arkomed Serwis spółka akcyjna z siedzibą w Białystok (15-629), ul. Kwiatowa 116/31",
                "Arkomed Serwis spółka akcyjna, ul. Kwiatowa 116/31", "Arkomed Serwis spółka akcyjna"):
        assert check_leaf(spec, raw, doc, [], "mocodawca[0].data.nazwa") == "Arkomed Serwis spółka akcyjna"


def test_named_action_fills_the_dictionary_entry_the_model_left_empty():
    from odwolania2json.extract import check_leaf
    from odwolania2json.pdfio import Document, Page
    spec = CLASSES["odwolanie"].output["OdwolanieKIO"]["czynnosc_powod_id"]
    text = ("ODWOŁANIE\nwnoszę odwołanie wobec:\n1. zaniechania odrzucenia oferty wykonawcy Alfa S.A., pomimo że oferta ta "
            "podlega odrzuceniu;\n2. wyboru oferty najkorzystniejszej.")
    doc = Document("", [Page(1, "text", text)])
    assert check_leaf(spec, None, doc, [], "OdwolanieKIO.czynnosc_powod_id") == 7
    assert check_leaf(spec, None, Document("", [Page(1, "text", "ODWOŁANIE\nbez wskazania czynności")]), [], "x") is None


def test_several_people_in_one_list_item_become_separate_items():
    raw = parse_sheet("## mocodawca 1\ndata.nazwa: Alfa sp. j.\npodpisujacy: Jan Kowalski | Anna Nowak\n"
                      "## pelnomocnicy 1\nimie_nazwisko: Piotr Zalewski | Ewa Lis\npesel: -", CLASSES["pelnomocnictwo"])
    assert [p["imie_nazwisko"] for p in raw["pelnomocnicy"]] == ["Piotr Zalewski", "Ewa Lis"]
    assert len(raw["mocodawca"]) == 1 and len(raw["mocodawca"][0]["podpisujacy"]) == 2


def test_ted_number_written_into_the_bzp_field_moves_to_its_own_field():
    data = {"ZamowieniePubliczne": {"numer_bzp": None, "numer_ted": None}}
    trace = [{"pole": "ZamowieniePubliczne.numer_bzp", "surowa": "2026/S189-999923", "wartosc": None, "status": "nieczytelne",
              "zrodlo": "warstwa_tekstowa"},
             {"pole": "ZamowieniePubliczne.numer_ted", "surowa": None, "wartosc": None, "status": "brak", "zrodlo": "warstwa_tekstowa"}]
    apply_field_rules(CLASSES["odwolanie"], data, trace, "nr referencyjny sprawy: SWZ.613.2026, TED: 2026/S189-999923")
    assert data["ZamowieniePubliczne"] == {"numer_bzp": None, "numer_ted": "999923-2026"}
    assert trace[1]["status"] == "dopasowano"


def test_api_backend_fills_the_form_line_by_line_like_the_local_model():
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from odwolania2json.llm import OpenAIBackend

    script = iter([" Alfa sp. z o.o.", " -", "## strona 2", " Beta S.A.", " 9990000000", "", " -17,00 PLN"])
    prompts = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            prompts.append(body["prompt"])
            assert self.headers["Authorization"] == "Bearer klucz-testowy" and body["stop"][0] == "\n"
            data = _json.dumps({"choices": [{"text": next(script)}], "usage": {"completion_tokens": 3}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        backend = OpenAIBackend(f"http://127.0.0.1:{server.server_port}/v1", "model", "klucz-testowy")
        answer = backend.fill("system", "opis\n", "tekst dokumentu", [("strona", True, ["nazwa", "krs"]), ("przelew", False, ["kwota"])],
                              signed=frozenset({"kwota"}))
    finally:
        server.shutdown()
    assert answer == ("## strona 1\nnazwa: Alfa sp. z o.o.\nkrs: -\n## strona 2\nnazwa: Beta S.A.\nkrs: 9990000000\n"
                      "## przelew\nkwota: -17,00 PLN")
    assert prompts[0].endswith("</think>\n\n## strona 1\nnazwa:")
    assert prompts[1].endswith("## strona 1\nnazwa: Alfa sp. z o.o.\nkrs:")
    assert prompts[3].endswith("krs: -\n## strona 2\nnazwa:")          # nagłówek podany przez model zostaje w kontekście
    assert backend.last_stats["zapytania"] == 7


def test_ocr_po_api(tmp_path, monkeypatch):
    """Usługa OCR: klient dostaje linie, odczyty alternatywne i prostokąty; zły klucz kończy się odczytem lokalnym."""
    import threading
    from odwolania2json import ocr_server, pdfio

    def fake_read(data, indices):
        assert data == b"%PDF-test"
        return {"pages": {str(i): {"lines": [["Sygn. akt KIO 12/26", 0.97, 0.1, (0.1, 0.09, 0.5, 0.11), (0.1, 0.09, 0.5, 0.11), 0.0]],
                                   "reads": {"150": "Sygn. akt KIO 12/26", "250": "Sygn. akt KIO 12/26"},
                                   "redactions": [(0.2, 0.3, 0.4, 0.32)]} for i in indices}}

    monkeypatch.setattr(ocr_server, "read_pdf", fake_read)
    server = ocr_server.make_server("127.0.0.1", 0, "tajny-klucz")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pdf = tmp_path / "skan.pdf"
    pdf.write_bytes(b"%PDF-test")
    monkeypatch.setenv("O2J_OCR_BASE", f"http://127.0.0.1:{server.server_address[1]}")
    try:
        monkeypatch.setenv("O2J_OCR_KEY", "tajny-klucz")
        pages = pdfio.remote_ocr(str(pdf), [0, 1])
        lines, reads, redactions = pages[1]
        assert lines[0].text == "Sygn. akt KIO 12/26" and lines[0].box == (0.1, 0.09, 0.5, 0.11)
        assert reads == {150: "Sygn. akt KIO 12/26", 250: "Sygn. akt KIO 12/26"} and redactions == [(0.2, 0.3, 0.4, 0.32)]
        monkeypatch.setenv("O2J_OCR_KEY", "inny")
        assert pdfio.remote_ocr(str(pdf), [0]) is None
    finally:
        server.shutdown()
