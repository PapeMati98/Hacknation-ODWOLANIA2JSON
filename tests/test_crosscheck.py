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
