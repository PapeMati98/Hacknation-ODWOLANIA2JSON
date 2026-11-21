"""Testy backendu Web UI (upload PDF, kolejka zadań, JSON/ZIP, klasy YAML, błędy i bezpieczeństwo)."""
from __future__ import annotations

import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from odwolania2json.pdfio import Document, Page
from odwolania2json.web import (
    WebAppState,
    _make_mock_backend,
    create_server,
    parse_class_yaml,
    sanitize_case_name,
    sanitize_pdf_filename,
)

CLASSES_SRC = Path(__file__).resolve().parent.parent / "configs" / "classes"
CROSS_CHECKS_SRC = Path(__file__).resolve().parent.parent / "configs" / "cross_checks.yaml"


def _multipart(fields: dict[str, str], files: list[tuple[str, str, bytes]]) -> tuple[str, bytes]:
    boundary = "----O2JTestBoundary7MA4YWxkTrZu0gW"
    buf = io.BytesIO()
    for name, val in fields.items():
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        buf.write(val.encode("utf-8") + b"\r\n")
    for field_name, filename, content in files:
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n".encode("utf-8")
        )
        buf.write(content + b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", buf.getvalue()


def _fake_pdf_loader(path: str, max_pages: int) -> Document:
    name = Path(path).name.lower()
    if "ted" in name or "obcy" in name:
        text = "Dziennik Urzędowy Unii Europejskiej — Ogłoszenie o zamówieniu 2025/S 100-123456"
    elif "przelew" in name:
        text = "Potwierdzenie przelewu bankowego. Data operacji: 2025-06-15. Kwota: 17,00 PLN. Tytuł: Opłata skarbowa."
    else:
        text = (
            "ODWOŁANIE\n"
            "Do Prezesa Krajowej Izby Odwoławczej\n"
            "Warszawa, dnia 16.06.2025\n"
            "Odwołujący: Test Sp. z o.o. NIP: 5540240549\n"
            "Zamawiający: Urząd Testowy\n"
            "Wnoszę odwołanie wobec treści SWZ. Zarzut naruszenia art. 99 Pzp."
        )
    return Document(path=path, pages=[Page(number=1, source="text", text=text)])


@pytest.fixture()
def web_server(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("O2J_WEB_QUIET", "1")
    classes_dir = tmp_path / "classes"
    classes_dir.mkdir()
    for src in CLASSES_SRC.glob("*.yaml"):
        (classes_dir / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    state = WebAppState(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        trace_dir=tmp_path / "trace",
        classes_dir=classes_dir,
        cross_checks_path=CROSS_CHECKS_SRC,
        model_path=str(tmp_path / "missing.gguf"),
        threads=2,
        backend_factory=_make_mock_backend,
        pdf_loader=_fake_pdf_loader,
        enable_test_seam=True,
    )
    server = create_server("127.0.0.1", 0, state)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", state
    finally:
        server.shutdown()
        server.server_close()


def _req(url: str, method: str = "GET", data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as err:
        return err.code, err.read(), dict(err.headers)


def test_sanitizers_and_yaml_validator():
    assert sanitize_case_name("sprawa 01") == "sprawa 01"
    assert sanitize_pdf_filename(r"C:\fakepath\odwolanie_1.pdf") == "odwolanie_1.pdf"
    with pytest.raises(ValueError):
        sanitize_pdf_filename("plik.txt")
    with pytest.raises(ValueError):
        parse_class_yaml("name: zla\n")


def test_status_and_empty_cases(web_server):
    base, _ = web_server
    code, raw, _ = _req(f"{base}/api/status")
    assert code == 200
    body = json.loads(raw)
    assert body["status"] == "ok"
    assert body["classes_count"] == 3
    assert set(body["class_names"]) == {"odwolanie", "pelnomocnictwo", "przelew"}
    assert body["visual_reader_available"] is False
    assert body["visual_reader_default"] == "off"

    code, raw, _ = _req(f"{base}/api/cases")
    assert code == 200
    assert json.loads(raw)["cases"] == []


def test_upload_validation_rejects_bad_files(web_server):
    base, _ = web_server
    ctype, body = _multipart({"case_name": "zla_sprawa"}, [("files", "not_pdf.txt", b"hello")])
    code, raw, _ = _req(f"{base}/api/cases/run", "POST", body, {"Content-Type": ctype})
    assert code == 400
    assert ".pdf" in json.loads(raw)["error"]

    ctype, body = _multipart({"case_name": "zla_sprawa"}, [("files", "fake.pdf", b"not a real pdf header")])
    code, raw, _ = _req(f"{base}/api/cases/run", "POST", body, {"Content-Type": ctype})
    assert code == 400
    assert "%PDF-" in json.loads(raw)["error"]

    ctype, body = _multipart(
        {"case_name": "zla_opcja", "visual_reader": "invalid"},
        [("files", "odwolanie.pdf", b"%PDF-1.7\n%mock")],
    )
    code, raw, _ = _req(f"{base}/api/cases/run", "POST", body, {"Content-Type": ctype})
    assert code == 400
    assert "visual_reader" in json.loads(raw)["error"]


def test_upload_extract_zip_and_foreign_empty_json(web_server):
    base, _ = web_server
    ctype, body = _multipart(
        {"case_name": "sprawa_test_1", "ocr_checksum": "confidence", "visual_reader": "off"},
        [
            ("files", "odwolanie.pdf", b"%PDF-1.7\n%mock-odwolanie"),
            ("files", "ogloszenie_ted_obcy.pdf", b"%PDF-1.7\n%mock-ted"),
        ],
    )
    code, raw, _ = _req(f"{base}/api/cases/run", "POST", body, {"Content-Type": ctype})
    assert code == 202
    job_id = json.loads(raw)["job_id"]

    for _ in range(80):
        code, raw, _ = _req(f"{base}/api/jobs/{job_id}")
        assert code == 200
        job = json.loads(raw)
        if job["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(0.05)

    assert job["status"] == "done", job
    assert job["processed_files"] == 2
    assert job["visual_reader"] == "off"

    code, raw, _ = _req(f"{base}/api/cases")
    assert code == 200
    c_row = json.loads(raw)["cases"][0]
    assert c_row["json_count"] == 1
    assert c_row["total_json_count"] == 2
    assert c_row["skipped_count"] == 1

    code, raw, _ = _req(f"{base}/api/cases/sprawa_test_1")
    assert code == 200
    detail = json.loads(raw)
    by_stem = {d["stem"]: d for d in detail["documents"]}
    assert by_stem["odwolanie"]["klasa"] == "odwolanie"
    assert by_stem["odwolanie"]["data"]["OdwolanieKIO"]["czynnosc_powod_id"] == 4
    assert by_stem["odwolanie"]["data"]["Odwolujacy"][0]["nip"] == "5540240549"
    # Kontrakt UZP (Q-021): dokument spoza klas otrzymuje pusty obiekt JSON {}.
    assert by_stem["ogloszenie_ted_obcy"]["skipped"] is True
    assert by_stem["ogloszenie_ted_obcy"]["has_json_file"] is True
    assert by_stem["ogloszenie_ted_obcy"]["data"] == {}

    # Pobranie pojedynczego JSON (sklasyfikowanego i obcego {}) oraz archiwum ZIP
    code, raw, _ = _req(f"{base}/api/cases/sprawa_test_1/files/odwolanie.json/json")
    assert code == 200
    assert json.loads(raw)["OdwolanieKIO"]["czynnosc_powod_id"] == 4

    code, raw, _ = _req(f"{base}/api/cases/sprawa_test_1/files/ogloszenie_ted_obcy.json/json")
    assert code == 200
    assert json.loads(raw) == {}

    code, zip_bytes, _ = _req(f"{base}/api/cases/sprawa_test_1/download.zip")
    assert code == 200
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert sorted(zf.namelist()) == [
            "sprawa_test_1/odwolanie.json",
            "sprawa_test_1/ogloszenie_ted_obcy.json",
        ]
        assert json.loads(zf.read("sprawa_test_1/ogloszenie_ted_obcy.json")) == {}


def test_yaml_classes_validate_create_and_conflict(web_server):
    base, _ = web_server
    sample_yaml = (
        "name: decyzja\n"
        "description: Decyzja administracyjna\n"
        "pages: 2\n"
        "classify:\n"
        "  title: ['decyzja']\n"
        "  keywords:\n"
        "    decyzja: 3\n"
        "    orzekam: 2\n"
        "  min_score: 4\n"
        "output:\n"
        "  Decyzja:\n"
        "    numer: { type: string, validator: text, verify_in_text: true }\n"
        "    data: { type: string, validator: date }\n"
    )
    code, raw, _ = _req(
        f"{base}/api/classes/validate",
        "POST",
        json.dumps({"yaml": sample_yaml}).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    assert code == 200
    val = json.loads(raw)
    assert val["valid"] is True
    assert val["summary"]["name"] == "decyzja"

    # Zapis nowej klasy
    code, raw, _ = _req(
        f"{base}/api/classes",
        "POST",
        json.dumps({"filename": "decyzja", "yaml": sample_yaml, "overwrite": False}).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    assert code == 201
    assert len(json.loads(raw)["classes"]) == 4

    # Konflikt bez overwrite=True
    code, raw, _ = _req(
        f"{base}/api/classes",
        "POST",
        json.dumps({"filename": "decyzja", "yaml": sample_yaml, "overwrite": False}).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    assert code == 409

    # Nadpisanie z overwrite=True
    code, _, _ = _req(
        f"{base}/api/classes",
        "POST",
        json.dumps({"filename": "decyzja", "yaml": sample_yaml, "overwrite": True}).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    assert code == 201


def test_seam_errors_and_404(web_server):
    base, _ = web_server
    code, raw, _ = _req(f"{base}/api/cases/nie_istnieje")
    assert code == 404

    code, raw, _ = _req(f"{base}/api/cases", headers={"X-Test-Fail": "500"})
    assert code == 500
    assert "500" in json.loads(raw)["error"]

    ctype, body = _multipart({"case_name": "blad_zadania"}, [("files", "odwolanie.pdf", b"%PDF-1.7\n%x")])
    code, raw, _ = _req(f"{base}/api/cases/run", "POST", body, {"Content-Type": ctype, "X-Test-Fail": "job_error"})
    assert code == 202
    job_id = json.loads(raw)["job_id"]
    for _ in range(50):
        _, jraw, _ = _req(f"{base}/api/jobs/{job_id}")
        job = json.loads(jraw)
        if job["status"] == "error":
            break
        time.sleep(0.05)
    assert job["status"] == "error"
    assert "test seam" in (job["error"] or "")


def test_visual_reader_wiring_and_eta(tmp_path: Path, monkeypatch):
    from odwolania2json import extract

    monkeypatch.setenv("O2J_WEB_QUIET", "1")
    classes_dir = tmp_path / "classes"
    classes_dir.mkdir()
    for src in CLASSES_SRC.glob("*.yaml"):
        (classes_dir / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    fake_mmproj = tmp_path / "mmproj-F16.gguf"
    fake_mmproj.write_bytes(b"gguf")

    vision_calls: list[str] = []
    reader_active_during_run: list[bool] = []
    seen_etas: list[float | None] = []

    def _vision_backend_factory():
        base_backend = _make_mock_backend()
        orig_complete = base_backend.complete

        def _enable_vision(path: str):
            vision_calls.append(path)

        def _complete(*args, **kwargs):
            reader_active_during_run.append(extract.VISUAL_READER is not None)
            time.sleep(0.02)
            return orig_complete(*args, **kwargs)

        base_backend.enable_vision = _enable_vision
        base_backend.complete = _complete
        return base_backend

    state = WebAppState(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        trace_dir=tmp_path / "trace",
        classes_dir=classes_dir,
        cross_checks_path=CROSS_CHECKS_SRC,
        model_path=str(tmp_path / "missing.gguf"),
        mmproj_path=str(fake_mmproj),
        threads=2,
        backend_factory=_vision_backend_factory,
        pdf_loader=_fake_pdf_loader,
    )
    server = create_server("127.0.0.1", 0, state)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        ctype, body = _multipart(
            {"case_name": "sprawa_vr", "visual_reader": "on"},
            [
                ("files", "odwolanie.pdf", b"%PDF-1.7\n%1"),
                ("files", "przelew.pdf", b"%PDF-1.7\n%2"),
            ],
        )
        code, raw, _ = _req(f"{base}/api/cases/run", "POST", body, {"Content-Type": ctype})
        assert code == 202
        job_id = json.loads(raw)["job_id"]
        for _ in range(120):
            _, jraw, _ = _req(f"{base}/api/jobs/{job_id}")
            job = json.loads(jraw)
            if job.get("eta_s") is not None:
                seen_etas.append(job["eta_s"])
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.01)
        assert job["status"] == "done", job
        assert job["visual_reader"] == "on"
        assert job["eta_s"] == 0.0
        assert any(e and e > 0 for e in seen_etas) or job["processed_files"] == 2
        assert vision_calls == [str(fake_mmproj)]
        assert reader_active_during_run and all(reader_active_during_run)
        assert extract.VISUAL_READER is None
    finally:
        server.shutdown()
        server.server_close()
