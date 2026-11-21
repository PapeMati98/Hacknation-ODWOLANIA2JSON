from odwolania2json.validators import (check_number, nip_ok, norm_amount, norm_bzp, norm_date, norm_ted, nrb_ok,
                                      pesel_ok, regon_ok)

# Prawdziwe, publiczne numery z przykładu w schemacie UZP.
NIP_ZAMAWIAJACEGO = "5540240549"
REGON_ZAMAWIAJACEGO = "000279077"


def test_checksums_real_numbers():
    assert nip_ok(NIP_ZAMAWIAJACEGO)
    assert regon_ok(REGON_ZAMAWIAJACEGO)
    assert pesel_ok("44051401359")
    assert nrb_ok("61109010140000071219812874")


def test_text_layer_keeps_bad_checksum():
    c = check_number("nip", "9999284065", from_ocr=False)
    assert c.value == "9999284065" and c.status in ("ok", "ostrzezenie")


def test_ocr_letter_confusion_fixed():
    c = check_number("nip", "554-O24-O5-49", from_ocr=True)
    assert c.value == NIP_ZAMAWIAJACEGO and c.status == "ok"


def test_ocr_one_digit_repair_or_unreadable():
    broken = NIP_ZAMAWIAJACEGO[:4] + "8" + NIP_ZAMAWIAJACEGO[5:]  # 0 -> 8
    c = check_number("nip", broken, from_ocr=True)
    assert c.value in (NIP_ZAMAWIAJACEGO, None)
    assert c.status in ("naprawiono", "nieczytelne")


def test_ocr_garbage_is_unreadable_not_guessed():
    c = check_number("nip", "ana a nn", from_ocr=True)
    assert c.value is None and c.status == "nieczytelne"


def test_ocr_wrong_length_unreadable():
    assert check_number("regon", "12345", from_ocr=True).value is None


def test_dates():
    assert norm_date("Warszawa, dnia 16 czerwca 2025 r.").value == "2025-06-16"
    assert norm_date("13.10.2025").value == "2025-10-13"
    assert norm_date("2025-02-31").value is None


def test_bzp_ted_amount():
    assert norm_bzp("2025/BZP 00270698").value == "2025/BZP00270698"
    assert norm_ted("2025/S 123-363730").value == "363730-2025"
    assert norm_ted("641651-2025").value == "641651-2025"
    assert norm_amount("10 000,00 PLN").value == 10000.0
    assert norm_amount("17,00 zł").value == 17.0
