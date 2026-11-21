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
