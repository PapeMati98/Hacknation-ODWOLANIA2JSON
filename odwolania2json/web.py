"""Interfejs webowy Odwołania2json (stdlib Python 3.13, zero zewnętrznych zależności webowych).

Uruchamianie:
  python -m odwolania2json.web --host 127.0.0.1 --port 8080

Zapewnia:
  - upload plików PDF sprawy (multipart/form-data) oraz ponowne uruchomienie spraw z input/,
  - asynchroniczne przetwarzanie w tle z podglądem postępu per dokument i możliwością anulowania,
  - podgląd wynikowego JSON (schemat UZP), śladu ekstrakcji (trace) oraz listy do_sprawdzenia.json,
  - pobieranie pojedynczych plików JSON oraz archiwum ZIP sprawy,
  - przegląd, walidację na żywo i dodawanie nowych klas dokumentów YAML bez zmian w kodzie.
"""
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import re
import threading
import time
import urllib.parse
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

import yaml

from . import extract, pdfio
from .cli import APP_ROOT, CLASSIFY_PAGES, default_threads, write_trace
from .config import DocClass, load_classes
from .crosscheck import case_findings, load_rules, review_entries
from .extract import Extractor, classify
from .llm import LlamaCppBackend, make_backend

ASSETS_DIR = Path(__file__).resolve().parent / "web_assets"
BUILTIN_CLASSES = frozenset({"odwolanie", "pelnomocnictwo", "przelew"})
SAFE_CASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")
SAFE_CLASS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 25


# ---------------------------------------------------------------- walidacja i pomocniki
def sanitize_case_name(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return f"sprawa_{time.strftime('%Y%m%d_%H%M%S')}"
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", text).strip(" .")
    if not cleaned or cleaned in (".", "..") or not SAFE_CASE_RE.fullmatch(cleaned):
        raise ValueError("Nieprawidłowa nazwa sprawy. Użyj liter, cyfr, spacji, myślnika lub podkreślenia.")
    return cleaned


def sanitize_pdf_filename(raw: str) -> str:
    base = Path(raw.replace("\\", "/")).name.strip()
    if not base or base in (".", ".."):
        raise ValueError("Pusta lub nieprawidłowa nazwa pliku.")
    if not base.lower().endswith(".pdf"):
        raise ValueError(f"Plik '{base}' nie ma rozszerzenia .pdf.")
    stem = re.sub(r"[^A-Za-z0-9ĄĆĘŁŃÓŚŹŻąćęłńóśźż._ -]+", "_", Path(base).stem).strip(" .")
    if not stem:
        stem = f"dokument_{uuid.uuid4().hex[:6]}"
    return f"{stem[:90]}.pdf"


def resolve_under(root: Path, *parts: str) -> Path:
    base = root.resolve()
    target = (base.joinpath(*parts)).resolve()
    if target != base and not target.is_relative_to(base):
        base = root.resolve()
        if target != base and not target.is_relative_to(base):
            raise ValueError("Niedozwolona ścieżka pliku.")
    return target


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, str], list[tuple[str, bytes]]]:
    """Parsuje multipart/form-data przy użyciu stdlib email.parser (Python 3.13)."""
    if "multipart/form-data" not in (content_type or "").lower():
        raise ValueError("Oczekiwano żądania multipart/form-data.")
    header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    msg = BytesParser(policy=email_policy).parsebytes(header + body)
    if not msg.is_multipart():
        raise ValueError("Niepoprawne ciało multipart/form-data.")
    fields: dict[str, str] = {}
    files: list[tuple[str, bytes]] = []
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename is not None:
            if filename.strip():
                files.append((filename, payload))
        elif name:
            fields[name] = payload.decode("utf-8", errors="replace").strip()
    return fields, files


def parse_class_yaml(yaml_text: str) -> tuple[DocClass, dict]:
    """Waliduje definicję klasy YAML tą samą logiką co config.load_classes."""
    if not yaml_text or not yaml_text.strip():
        raise ValueError("Treść YAML klasy jest pusta.")
    try:
        raw = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Błąd składni YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Plik klasy musi zawierać obiekt YAML (mapę kluczy).")
    name = str(raw.get("name") or "").strip()
    if not name or not SAFE_CLASS_RE.fullmatch(name):
        raise ValueError("Pole 'name' musi składać się z małych liter, cyfr, '_' lub '-' (1–41 znaków).")
    if not isinstance(raw.get("output"), dict) or not raw["output"]:
        raise ValueError("Brak wymaganej sekcji 'output' definiującej schemat JSON.")
    cls_cfg = raw.get("classify") or {}
    if not isinstance(cls_cfg, dict):
        raise ValueError("Sekcja 'classify' musi być obiektem YAML.")
    exclude_title_raw = cls_cfg.get("exclude_title") or []
    if not isinstance(exclude_title_raw, list) or any(not isinstance(t, str) or not t.strip() for t in exclude_title_raw):
        raise ValueError("Pole 'classify.exclude_title' musi być listą niepustych napisów.")
    continue_raw = raw.get("continue_when_empty") or {}
    if continue_raw:
        if not isinstance(continue_raw, dict) or not isinstance(continue_raw.get("fields"), list) or not continue_raw.get("fields"):
            raise ValueError("Sekcja 'continue_when_empty' musi zawierać listę 'fields' oraz liczbę stron 'pages'.")
        if int(continue_raw.get("pages", 0)) < 1:
            raise ValueError("Pole 'continue_when_empty.pages' musi być dodatnią liczbą całkowitą.")
    doc_class = DocClass(
        name=name,
        description=str(raw.get("description") or "").strip(),
        pages=int(raw.get("pages", 3)),
        keywords={str(k).lower(): float(v) for k, v in (cls_cfg.get("keywords") or {}).items()},
        negative={str(k).lower(): float(v) for k, v in (cls_cfg.get("negative") or {}).items()},
        min_score=float(cls_cfg.get("min_score", 4)),
        title=[str(t) for t in (cls_cfg.get("title") or [])],
        title_weight=float(cls_cfg.get("title_weight", 5)),
        exclude_title=[str(t) for t in exclude_title_raw],
        continue_when_empty=continue_raw,
        output=raw["output"],
        dictionaries={
            str(k): {int(i): str(s) for i, s in d.items()}
            for k, d in (raw.get("dictionaries") or {}).items()
        },
        hints={
            str(k): {int(i): str(s) for i, s in d.items()}
            for k, d in (raw.get("hints") or {}).items()
        },
    )
    sections = doc_class.sections()
    if not sections:
        raise ValueError("Sekcja 'output' nie zawiera żadnych pól do ekstrakcji.")
    for s in sections:
        for f in s.fields:
            if "or_from" in f.spec and (not isinstance(f.spec["or_from"], str) or not f.spec["or_from"].strip()):
                raise ValueError(f"Pole '{f.key}': opcja 'or_from' musi być niepustym napisem (nazwą innego pola).")
    summary = {
        "name": doc_class.name,
        "description": doc_class.description,
        "pages": doc_class.pages,
        "min_score": doc_class.min_score,
        "title": doc_class.title,
        "keywords_count": len(doc_class.keywords),
        "negative_count": len(doc_class.negative),
        "exclude_title_count": len(doc_class.exclude_title),
        "continue_when_empty": (
            {"fields": list(doc_class.continue_when_empty.get("fields") or []), "pages": int(doc_class.continue_when_empty["pages"])}
            if doc_class.continue_when_empty
            else None
        ),
        "dictionaries": list(doc_class.dictionaries.keys()),
        "sections": [
            {
                "name": s.name,
                "is_list": s.is_list,
                "fields": [
                    {
                        "key": f.key,
                        "type": f.spec.get("type", "string"),
                        "validator": f.spec.get("validator"),
                        "verify_in_text": bool(f.spec.get("verify_in_text", False)),
                        "rules": [
                            k for k in (
                                "requires", "not_in", "line_pattern", "decide", "known_values",
                                "reject", "sanity", "or_from", "wraps", "check",
                            )
                            if k in f.spec
                        ],
                        "desc": f.spec.get("desc", ""),
                    }
                    for f in s.fields
                ],
            }
            for s in sections
        ],
    }
    return doc_class, summary


# ---------------------------------------------------------------- stan serwera i zadania w tle
@dataclass
class JobState:
    job_id: str
    case_name: str
    ocr_checksum: str
    total_files: int
    visual_reader: str = "off"
    status: str = "queued"              # queued | running | done | error | cancelled
    stage: str = "oczekiwanie"
    current_file: str | None = None
    processed_files: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    eta_s: float | None = None
    error: str | None = None
    cancel_requested: bool = False
    documents_done: list[dict] = field(default_factory=list)
    review_count: int = 0

    def to_dict(self) -> dict:
        end = self.finished_at if self.finished_at is not None else time.time()
        return {
            "job_id": self.job_id,
            "case_name": self.case_name,
            "ocr_checksum": self.ocr_checksum,
            "visual_reader": self.visual_reader,
            "status": self.status,
            "stage": self.stage,
            "current_file": self.current_file,
            "processed_files": self.processed_files,
            "total_files": self.total_files,
            "elapsed_s": round(max(0.0, end - self.started_at), 1),
            "eta_s": round(self.eta_s, 1) if self.eta_s is not None else None,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "documents_done": list(self.documents_done),
            "review_count": self.review_count,
        }


class WebAppState:
    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        trace_dir: Path,
        classes_dir: Path,
        cross_checks_path: Path,
        model_path: str,
        threads: int,
        mmproj_path: str | None = None,
        default_visual_reader: str = "off",
        backend_factory: Callable[[], object] | None = None,
        pdf_loader: Callable[[str, int], pdfio.Document] | None = None,
        enable_test_seam: bool = False,
    ):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.trace_dir = trace_dir
        self.classes_dir = classes_dir
        self.cross_checks_path = cross_checks_path
        self.model_path = model_path
        self.threads = threads
        self.mmproj_path = mmproj_path or str(APP_ROOT / "models" / "mmproj-F16.gguf")
        self.default_visual_reader = default_visual_reader if default_visual_reader in ("on", "off") else "off"
        self._backend_factory = backend_factory
        self._custom_pdf_loader = pdf_loader is not None
        self._pdf_loader = pdf_loader or (lambda path, max_pages: pdfio.load(path, max_pages=max_pages))
        self.enable_test_seam = enable_test_seam

        self._backend = None
        self._vision_enabled = False
        self._backend_lock = threading.Lock()
        self._pipeline_lock = threading.Lock()
        self._jobs_lock = threading.Lock()
        self._jobs: dict[str, JobState] = {}

        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.trace_dir.mkdir(parents=True, exist_ok=True)

    def visual_reader_available(self) -> bool:
        if self._backend_factory is not None or os.environ.get("O2J_API_BASE"):
            return False
        return Path(self.mmproj_path).is_file() and Path(self.model_path).is_file()

    def get_backend(self):
        with self._backend_lock:
            if self._backend is None:
                if self._backend_factory is not None:
                    self._backend = self._backend_factory()
                else:
                    self._backend = make_backend(self.model_path, self.threads)
            return self._backend

    def backend_summary(self) -> dict:
        api_base = os.environ.get("O2J_API_BASE")
        ocr_mode = "api" if os.environ.get("O2J_OCR_BASE") else "lokalny"
        model_exists = Path(self.model_path).is_file()
        api_model = os.environ.get("O2J_API_MODEL", "default")
        if self._backend_factory is not None:
            mode = "test/mock"
            label = getattr(self._backend, "name", "MockExtractor (test)")
        elif api_base:
            mode = "api"
            label = f"API · {api_model}"
        else:
            mode = "cpu"
            model_file = Path(self.model_path)
            label = f"CPU · {model_file.stem}" + ("" if model_exists else " (brak pliku GGUF)")
        return {
            "mode": mode,
            "label": label,
            "api_model": api_model if mode == "api" else None,
            "model_exists": model_exists,
            "ocr_mode": ocr_mode,
            "model_path": self.model_path,
            "threads": self.threads,
        }

    def list_classes_data(self) -> list[dict]:
        items: list[dict] = []
        for path in sorted(self.classes_dir.glob("*.yaml")):
            text = path.read_text(encoding="utf-8")
            _, summary = parse_class_yaml(text)
            summary["filename"] = path.name
            summary["builtin"] = path.stem in BUILTIN_CLASSES
            summary["yaml"] = text
            items.append(summary)
        return items

    def save_class_yaml(self, yaml_text: str, filename: str | None = None, overwrite: bool = False) -> dict:
        doc_class, summary = parse_class_yaml(yaml_text)
        slug = (filename or doc_class.name).strip()
        if slug.endswith(".yaml"):
            slug = slug[:-5]
        if not SAFE_CLASS_RE.fullmatch(slug):
            raise ValueError("Nazwa pliku klasy może zawierać wyłącznie małe litery, cyfry, '_' i '-'.")
        target = resolve_under(self.classes_dir, f"{slug}.yaml")
        if target.exists() and not overwrite:
            raise FileExistsError(f"Klasa '{slug}.yaml' już istnieje. Zaznacz nadpisanie lub użyj innej nazwy.")
        if slug in BUILTIN_CLASSES and not overwrite:
            raise FileExistsError(f"Klasa wbudowana '{slug}.yaml' wymaga jawnego nadpisania.")
        tmp = target.with_suffix(".yaml.tmp")
        tmp.write_text(yaml_text.rstrip() + "\n", encoding="utf-8")
        tmp.replace(target)
        summary["filename"] = target.name
        summary["builtin"] = slug in BUILTIN_CLASSES
        summary["yaml"] = target.read_text(encoding="utf-8")
        return summary

    def list_cases(self) -> list[dict]:
        names: set[str] = set()
        for base in (self.output_dir, self.trace_dir, self.input_dir):
            if base.is_dir():
                for child in base.iterdir():
                    if child.is_dir() and not child.name.startswith("."):
                        names.add(child.name)
        cases = []
        for name in sorted(names):
            out_dir = self.output_dir / name
            tr_dir = self.trace_dir / name
            in_dir = self.input_dir / name
            jsons = sorted(out_dir.glob("*.json")) if out_dir.is_dir() else []
            traces = sorted(tr_dir.glob("*.trace.json")) if tr_dir.is_dir() else []
            pdfs = sorted(in_dir.glob("*.pdf")) if in_dir.is_dir() else []
            skipped_stems: set[str] = set()
            has_scan = False
            mtimes = [p.stat().st_mtime for p in jsons + traces + pdfs]
            for tr_path in traces:
                try:
                    rec = json.loads(tr_path.read_text(encoding="utf-8"))
                    if rec.get("klasa") is None:
                        skipped_stems.add(tr_path.name[:-len(".trace.json")])
                    if rec.get("skan"):
                        has_scan = True
                except (OSError, json.JSONDecodeError):
                    pass
            review_count = 0
            rev_path = tr_dir / "do_sprawdzenia.json"
            if rev_path.is_file():
                try:
                    review_count = len(json.loads(rev_path.read_text(encoding="utf-8")).get("pozycje", []))
                except (OSError, json.JSONDecodeError):
                    pass
            classified_jsons = sum(1 for j in jsons if j.stem not in skipped_stems)
            cases.append({
                "name": name,
                "json_count": classified_jsons,
                "total_json_count": len(jsons),
                "skipped_count": len(skipped_stems),
                "input_pdf_count": len(pdfs),
                "review_count": review_count,
                "has_output": bool(jsons or traces),
                "has_scan": has_scan,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(max(mtimes))) if mtimes else None,
            })
        cases.sort(key=lambda c: (not c["has_output"], c["name"].casefold()))
        return cases

    def get_case_detail(self, case_name: str) -> dict:
        safe_name = sanitize_case_name(case_name)
        out_dir = resolve_under(self.output_dir, safe_name)
        tr_dir = resolve_under(self.trace_dir, safe_name)
        in_dir = resolve_under(self.input_dir, safe_name)
        if not any(d.is_dir() for d in (out_dir, tr_dir, in_dir)):
            raise FileNotFoundError(f"Sprawa '{safe_name}' nie istnieje.")

        docs_by_stem: dict[str, dict] = {}
        if tr_dir.is_dir():
            for tr_path in sorted(tr_dir.glob("*.trace.json")):
                try:
                    safe_tr = resolve_under(tr_dir, tr_path.name)
                except ValueError:
                    continue
                stem = tr_path.name[:-len(".trace.json")]
                try:
                    rec = json.loads(safe_tr.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    rec = {}
                docs_by_stem[stem] = {
                    "stem": stem,
                    "pdf_name": Path(rec.get("plik", f"{stem}.pdf")).name,
                    "json_name": f"{stem}.json",
                    "has_json_file": False,
                    "klasa": rec.get("klasa"),
                    "skipped": rec.get("klasa") is None,
                    "skan": bool(rec.get("skan", False)),
                    "punkty_klas": rec.get("punkty_klas") or {},
                    "nieczytelne_linie": int(rec.get("nieczytelne_linie") or 0),
                    "czas_wczytania_s": rec.get("czas_wczytania_s"),
                    "czas_ekstrakcji_s": rec.get("czas_ekstrakcji_s"),
                    "model": rec.get("model"),
                    "blad": rec.get("blad"),
                    "trace": rec.get("pola") or [],
                    "data": {} if rec.get("klasa") is None else None,
                }

        if out_dir.is_dir():
            for j_path in sorted(out_dir.glob("*.json")):
                try:
                    safe_j = resolve_under(out_dir, j_path.name)
                except ValueError:
                    continue
                stem = j_path.stem
                try:
                    parsed = json.loads(safe_j.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    parsed = None
                entry = docs_by_stem.setdefault(stem, {
                    "stem": stem,
                    "pdf_name": f"{stem}.pdf",
                    "json_name": j_path.name,
                    "has_json_file": True,
                    "klasa": "nieznana",
                    "skipped": False,
                    "skan": False,
                    "punkty_klas": {},
                    "nieczytelne_linie": 0,
                    "czas_wczytania_s": None,
                    "czas_ekstrakcji_s": None,
                    "model": None,
                    "trace": [],
                    "data": None,
                })
                entry["json_name"] = j_path.name
                entry["has_json_file"] = True
                entry["data"] = parsed

        review = {"sprawa": safe_name, "pozycje": []}
        try:
            rev_path = resolve_under(tr_dir, "do_sprawdzenia.json")
        except ValueError:
            rev_path = None
        if rev_path is not None and rev_path.is_file():
            try:
                review = json.loads(rev_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

        input_files = sorted(p.name for p in in_dir.glob("*.pdf")) if in_dir.is_dir() else []
        ordered_docs = sorted(docs_by_stem.values(), key=lambda d: (bool(d.get("skipped")), d["stem"].casefold()))
        return {
            "name": safe_name,
            "documents": ordered_docs,
            "do_sprawdzenia": review,
            "input_files": input_files,
        }

    def build_case_zip(self, case_name: str) -> bytes:
        safe_name = sanitize_case_name(case_name)
        out_dir = resolve_under(self.output_dir, safe_name)
        if not out_dir.is_dir():
            raise FileNotFoundError(f"Brak wygenerowanych plików JSON dla sprawy '{safe_name}'.")
        jsons = sorted(out_dir.glob("*.json"))
        if not jsons:
            raise FileNotFoundError(f"Brak plików JSON dla sprawy '{safe_name}'.")
        buf = io.BytesIO()
        written = 0
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in jsons:
                try:
                    safe_p = resolve_under(out_dir, p.name)
                except ValueError:
                    continue
                if safe_p.is_file():
                    zf.write(safe_p, arcname=f"{safe_name}/{p.name}")
                    written += 1
        if written == 0:
            raise FileNotFoundError(f"Brak poprawnych plików JSON dla sprawy '{safe_name}'.")
        return buf.getvalue()

    def start_job(
        self,
        case_name: str,
        pdfs: list[Path],
        ocr_checksum: str = "confidence",
        visual_reader: str = "off",
        force_fail: str | None = None,
    ) -> JobState:
        if ocr_checksum not in ("confidence", "strict"):
            raise ValueError("Polityka --ocr-checksum musi mieć wartość 'confidence' lub 'strict'.")
        if visual_reader not in ("off", "on"):
            raise ValueError("Parametr visual_reader musi mieć wartość 'off' lub 'on'.")
        if not pdfs:
            raise ValueError("Sprawa nie zawiera żadnych plików PDF do przetworzenia.")
        job = JobState(
            job_id=uuid.uuid4().hex[:12],
            case_name=case_name,
            ocr_checksum=ocr_checksum,
            total_files=len(pdfs),
            visual_reader=visual_reader,
        )
        with self._jobs_lock:
            self._jobs[job.job_id] = job
        thread = threading.Thread(
            target=self._run_job,
            args=(job, list(pdfs), force_fail),
            daemon=True,
            name=f"o2j-job-{job.job_id}",
        )
        thread.start()
        return job

    def get_job(self, job_id: str) -> JobState | None:
        with self._jobs_lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict]:
        with self._jobs_lock:
            ordered = sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)
            return [j.to_dict() for j in ordered[:20]]

    def cancel_job(self, job_id: str) -> JobState | None:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in ("queued", "running"):
                job.cancel_requested = True
                job.stage = "anulowanie..."
            return job

    def _run_job(self, job: JobState, pdfs: list[Path], force_fail: str | None = None) -> None:
        try:
            with self._pipeline_lock:
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.stage = "anulowano"
                    job.finished_at = time.time()
                    return
                job.status = "running"
                job.stage = "ładowanie klas YAML"
                if force_fail == "job_error":
                    raise RuntimeError("Symulowany błąd silnika ekstrakcji (test seam).")

                classes = load_classes(self.classes_dir)
                by_name = {c.name: c for c in classes}
                extract.CHECKSUM_POLICY = job.ocr_checksum

                case_out = resolve_under(self.output_dir, job.case_name)
                case_out.mkdir(parents=True, exist_ok=True)
                case_trace = resolve_under(self.trace_dir, job.case_name)
                case_trace.mkdir(parents=True, exist_ok=True)

                # Etap 1: wczytanie pierwszych CLASSIFY_PAGES stron (tekst/OCR) + klasyfikacja;
                # dalsze strony doczytujemy tylko dla rozpoznanej klasy (zgodnie z cli.read_document).
                pending = []
                isolate_read_errors = len(pdfs) > 1
                for idx, pdf in enumerate(pdfs):
                    if job.cancel_requested:
                        job.status = "cancelled"
                        job.stage = "anulowano przez użytkownika"
                        job.finished_at = time.time()
                        return
                    job.current_file = pdf.name
                    job.stage = "wczytywanie / OCR i klasyfikacja"
                    rel = Path(job.case_name) / pdf.with_suffix(".json").name
                    t0 = time.perf_counter()
                    try:
                        doc = self._pdf_loader(str(pdf), CLASSIFY_PAGES)
                        cls_name, scores = classify(doc, classes)
                        if cls_name is not None and not self._custom_pdf_loader:
                            with pdfio._ENGINE_LOCK:
                                doc.ensure_pages(by_name[cls_name].pages)
                            doc.alt_text(pdfio.ALT_DPIS[0], 1)
                    except Exception as exc:
                        if not isolate_read_errors:
                            raise
                        err_msg = f"{type(exc).__name__}: {exc}"
                        record = {
                            "plik": str(pdf),
                            "skan": False,
                            "klasa": None,
                            "punkty_klas": {},
                            "nieczytelne_linie": 0,
                            "czas_wczytania_s": round(time.perf_counter() - t0, 2),
                            "blad": err_msg,
                        }
                        out_path = resolve_under(self.output_dir, job.case_name, rel.name)
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_text("{}", encoding="utf-8")
                        resolve_under(self.trace_dir, job.case_name, f"{rel.stem}.trace.json")
                        write_trace(self.trace_dir, rel, record)
                        job.processed_files += 1
                        job.documents_done.append({"file": pdf.name, "klasa": None, "skipped": True, "error": err_msg})
                        continue
                    record = {
                        "plik": str(pdf),
                        "skan": doc.is_scan,
                        "klasa": cls_name,
                        "punkty_klas": scores,
                        "nieczytelne_linie": sum(p.unreadable for p in doc.pages),
                        "czas_wczytania_s": round(time.perf_counter() - t0, 2),
                    }
                    if cls_name is None:
                        # Kontrakt UZP (README, commit 96aea5a): dokument spoza klas dostaje pusty plik JSON {}.
                        out_path = resolve_under(self.output_dir, job.case_name, rel.name)
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_text("{}", encoding="utf-8")
                        resolve_under(self.trace_dir, job.case_name, f"{rel.stem}.trace.json")
                        write_trace(self.trace_dir, rel, record)
                        job.processed_files += 1
                        job.documents_done.append({"file": pdf.name, "klasa": None, "skipped": True})
                    else:
                        pending.append((cls_name, rel, pdf, doc, record))

                # Etap 2: ekstrakcja (w trybie API współbieżnie z ping + fallbackiem; lokalnie sekwencyjnie wg klas)
                case_results: list[tuple[str, str, dict]] = []
                case_review: list[dict] = []
                if pending:
                    job.stage = "inicjalizacja modelu LLM"
                    backend = self.get_backend()
                    if hasattr(backend, "ping"):
                        job.stage = "sprawdzanie połączenia z API modelu"
                        problem = backend.ping()
                        if problem is not None:
                            if self._backend_factory is None and Path(self.model_path).is_file():
                                try:
                                    job.stage = "API niedostępne — przełączanie na model lokalny CPU"
                                    backend = LlamaCppBackend(self.model_path, self.threads)
                                except ImportError:
                                    raise RuntimeError(problem) from None
                            else:
                                raise RuntimeError(problem)
                    extract.VISUAL_READER = None
                    try:
                        if job.visual_reader == "on" and hasattr(backend, "enable_vision") and Path(self.mmproj_path).is_file():
                            from .vision import VisualReader
                            if not self._vision_enabled:
                                backend.enable_vision(self.mmproj_path)
                                self._vision_enabled = True
                            extract.VISUAL_READER = VisualReader(backend)
                        extractor = Extractor(backend)
                        t_extract = time.perf_counter()
                        total_pending = len(pending)
                        parallel = max(1, int(getattr(backend, "parallel", 1)))
                        isolate_doc_errors = total_pending > 1

                        if parallel > 1 and total_pending > 1:
                            # PDFium nie jest bezpieczny wątkowo nawet na różnych dokumentach: serializuj ensure_pages()
                            # tym samym RLockiem, z którego korzysta pdfio.alt_text() (bez modyfikacji pdfio.py).
                            for _, _, _, doc_obj, _ in pending:
                                if hasattr(doc_obj, "ensure_pages"):
                                    orig_ensure = doc_obj.ensure_pages

                                    def _locked_ensure(count: int, _fn=orig_ensure) -> None:
                                        with pdfio._ENGINE_LOCK:
                                            return _fn(count)

                                    doc_obj.ensure_pages = _locked_ensure

                        def _process_one(item):
                            cls_name, rel, pdf, doc, record = item
                            t0 = time.perf_counter()
                            err_msg = None
                            try:
                                data, trace, answer = extractor.run(doc, by_name[cls_name])
                            except Exception as exc:
                                if not isolate_doc_errors:
                                    raise
                                data, trace, answer = {}, [], ""
                                err_msg = f"{type(exc).__name__}: {exc}"
                                record["blad"] = err_msg
                            out_path = resolve_under(self.output_dir, job.case_name, rel.name)
                            out_path.parent.mkdir(parents=True, exist_ok=True)
                            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                            record.update(
                                pola=trace,
                                odpowiedz_modelu=answer,
                                czas_ekstrakcji_s=round(time.perf_counter() - t0, 2),
                                model=getattr(extractor.backend, "last_stats", None),
                            )
                            resolve_under(self.trace_dir, job.case_name, f"{rel.stem}.trace.json")
                            write_trace(self.trace_dir, rel, record)
                            return cls_name, rel, pdf, data, trace, err_msg

                        def _record_done(done_count: int, res) -> None:
                            cls_name, rel, pdf, data, trace, err_msg = res
                            if not err_msg:
                                case_results.append((rel.name, cls_name, data))
                                case_review.extend(review_entries(rel.name, trace))
                            with self._jobs_lock:
                                job.processed_files += 1
                                remaining = total_pending - done_count
                                job.eta_s = (
                                    ((time.perf_counter() - t_extract) / done_count) * remaining
                                    if remaining > 0
                                    else 0.0
                                )
                                job.documents_done.append({
                                    "file": pdf.name,
                                    "klasa": cls_name,
                                    "skipped": False,
                                    "error": err_msg,
                                })

                        ordered = sorted(pending, key=lambda item: (item[0], item[2].name))
                        if parallel > 1 and total_pending > 1:
                            job.stage = f"ekstrakcja równoległa API ({min(parallel, total_pending)} naraz)"
                            done_count = 0
                            retry_items = []
                            with ThreadPoolExecutor(max_workers=min(parallel, total_pending)) as pool:
                                futures = {pool.submit(_process_one, it): it for it in ordered}
                                for fut in as_completed(futures):
                                    res = fut.result()
                                    err_msg = res[5]
                                    if err_msg and "Model po API nie odpowiada" in err_msg:
                                        retry_items.append(futures[fut])
                                    else:
                                        done_count += 1
                                        job.current_file = res[2].name
                                        _record_done(done_count, res)
                            for it in retry_items:
                                if job.cancel_requested:
                                    job.status = "cancelled"
                                    job.stage = "anulowano przez użytkownika"
                                    job.finished_at = time.time()
                                    return
                                it[4].pop("blad", None)
                                job.current_file = it[2].name
                                job.stage = f"ponowienie ({it[0]})"
                                res = _process_one(it)
                                done_count += 1
                                _record_done(done_count, res)
                        else:
                            for done_idx, it in enumerate(ordered, 1):
                                if job.cancel_requested:
                                    job.status = "cancelled"
                                    job.stage = "anulowano przez użytkownika"
                                    job.finished_at = time.time()
                                    return
                                job.current_file = it[2].name
                                job.stage = f"ekstrakcja ({it[0]})"
                                res = _process_one(it)
                                _record_done(done_idx, res)
                    finally:
                        extract.VISUAL_READER = None

                # Etap 3: kontrola krzyżowa sprawy
                job.current_file = None
                job.stage = "kontrola krzyżowa sprawy"
                rules = load_rules(self.cross_checks_path)
                items = case_review + case_findings(rules, case_results)
                rev_path = resolve_under(self.trace_dir, job.case_name, "do_sprawdzenia.json")
                rev_path.parent.mkdir(parents=True, exist_ok=True)
                rev_path.write_text(
                    json.dumps({"sprawa": job.case_name, "pozycje": items}, ensure_ascii=False, indent=1, default=str),
                    encoding="utf-8",
                )
                job.review_count = len(items)
                job.status = "done"
                job.stage = "zakończono"
                job.finished_at = time.time()
        except Exception as exc:
            job.status = "error"
            job.stage = "błąd przetwarzania"
            job.error = str(exc) or exc.__class__.__name__
            job.finished_at = time.time()


# ---------------------------------------------------------------- handler HTTP
def make_handler(state: WebAppState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def handle(self) -> None:
            try:
                super().handle()
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass

        def log_message(self, fmt: str, *args) -> None:
            # Zwięzłe logi bez zaśmiecania stdout w testach
            if os.environ.get("O2J_WEB_QUIET") == "1":
                return
            super().log_message(fmt, *args)

        def _send_bytes(self, status: int, content_type: str, payload: bytes,
                        extra_headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, status: int, data: dict | list) -> None:
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, "application/json; charset=utf-8", raw)

        def _read_body(self, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Nieprawidłowy nagłówek Content-Length.") from exc
            if length < 0 or length > max_bytes:
                raise OverflowError(f"Przekroczono maksymalny rozmiar żądania ({max_bytes // (1024 * 1024)} MB).")
            return self.rfile.read(length) if length else b""

        def _check_test_seam(self) -> str | None:
            if not state.enable_test_seam:
                return None
            return (self.headers.get("X-Test-Fail") or "").strip() or None

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = urllib.parse.unquote(parsed.path)
            try:
                fail = self._check_test_seam()
                if fail == "500":
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Symulowany błąd serwera (500)."})
                    return

                if path in ("/", "/index.html"):
                    self._serve_asset("index.html")
                    return
                if path.startswith("/assets/"):
                    self._serve_asset(path[len("/assets/"):])
                    return

                if path == "/api/status":
                    classes = state.list_classes_data()
                    active = [j for j in state.list_jobs() if j["status"] in ("queued", "running")]
                    self._send_json(HTTPStatus.OK, {
                        "status": "ok",
                        "backend": state.backend_summary(),
                        "checksum_policy": extract.CHECKSUM_POLICY,
                        "visual_reader_available": state.visual_reader_available(),
                        "visual_reader_default": state.default_visual_reader,
                        "mmproj_name": Path(state.mmproj_path).name,
                        "classes_count": len(classes),
                        "class_names": [c["name"] for c in classes],
                        "active_jobs": len(active),
                        "test_seam": state.enable_test_seam,
                    })
                    return

                if path == "/api/cases":
                    self._send_json(HTTPStatus.OK, {"cases": state.list_cases()})
                    return

                m_zip = re.fullmatch(r"/api/cases/([^/]+)/download\.zip", path)
                if m_zip:
                    case_name = m_zip.group(1)
                    data = state.build_case_zip(case_name)
                    safe_dl = sanitize_case_name(case_name)
                    self._send_bytes(
                        HTTPStatus.OK,
                        "application/zip",
                        data,
                        {"Content-Disposition": f'attachment; filename="{safe_dl}.zip"'},
                    )
                    return

                m_json = re.fullmatch(r"/api/cases/([^/]+)/files/([^/]+)/json", path)
                if m_json:
                    case_name = sanitize_case_name(m_json.group(1))
                    fname = Path(m_json.group(2)).name
                    if not fname.lower().endswith(".json"):
                        raise ValueError("Dozwolone wyłącznie pliki .json.")
                    target = resolve_under(state.output_dir, case_name, fname)
                    if not target.is_file():
                        raise FileNotFoundError(f"Nie znaleziono pliku '{fname}' w sprawie '{case_name}'.")
                    raw = target.read_bytes()
                    self._send_bytes(
                        HTTPStatus.OK,
                        "application/json; charset=utf-8",
                        raw,
                        {"Content-Disposition": f'attachment; filename="{fname}"'},
                    )
                    return

                m_case = re.fullmatch(r"/api/cases/([^/]+)", path)
                if m_case:
                    self._send_json(HTTPStatus.OK, state.get_case_detail(m_case.group(1)))
                    return

                if path == "/api/jobs":
                    self._send_json(HTTPStatus.OK, {"jobs": state.list_jobs()})
                    return

                m_job = re.fullmatch(r"/api/jobs/([^/]+)", path)
                if m_job:
                    job = state.get_job(m_job.group(1))
                    if job is None:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Nie znaleziono zadania o podanym ID."})
                        return
                    self._send_json(HTTPStatus.OK, job.to_dict())
                    return

                if path == "/api/classes":
                    self._send_json(HTTPStatus.OK, {"classes": state.list_classes_data()})
                    return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Nieznany punkt końcowy: {path}"})
            except FileNotFoundError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Błąd wewnętrzny: {exc}"})

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = urllib.parse.unquote(parsed.path)
            try:
                fail = self._check_test_seam()
                if fail == "500":
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Symulowany błąd serwera (500)."})
                    return
                if fail == "409":
                    self._send_json(HTTPStatus.CONFLICT, {"error": "Symulowany konflikt zasobu (409)."})
                    return

                if path == "/api/cases/run":
                    self._handle_run_case(force_fail=fail)
                    return

                m_cancel = re.fullmatch(r"/api/jobs/([^/]+)/cancel", path)
                if m_cancel:
                    job = state.cancel_job(m_cancel.group(1))
                    if job is None:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Nie znaleziono zadania."})
                        return
                    self._send_json(HTTPStatus.OK, job.to_dict())
                    return

                if path == "/api/classes/validate":
                    payload = json.loads(self._read_body(2 * 1024 * 1024).decode("utf-8"))
                    _, summary = parse_class_yaml(payload.get("yaml", ""))
                    self._send_json(HTTPStatus.OK, {"valid": True, "summary": summary})
                    return

                if path == "/api/classes":
                    payload = json.loads(self._read_body(2 * 1024 * 1024).decode("utf-8"))
                    saved = state.save_class_yaml(
                        yaml_text=payload.get("yaml", ""),
                        filename=payload.get("filename"),
                        overwrite=bool(payload.get("overwrite", False)),
                    )
                    self._send_json(HTTPStatus.CREATED, {"saved": saved, "classes": state.list_classes_data()})
                    return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Nieznany punkt końcowy: {path}"})
            except OverflowError as exc:
                self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": str(exc)})
            except FileExistsError as exc:
                self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
            except FileNotFoundError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except (ValueError, json.JSONDecodeError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Błąd wewnętrzny: {exc}"})

        def _handle_run_case(self, force_fail: str | None = None) -> None:
            ctype = self.headers.get("Content-Type", "")
            body = self._read_body()
            if "multipart/form-data" in ctype.lower():
                fields, files = parse_multipart(ctype, body)
                if not files:
                    raise ValueError("Dodaj co najmniej jeden plik PDF przed uruchomieniem ekstrakcji.")
                if len(files) > MAX_FILES_PER_UPLOAD:
                    raise ValueError(f"Maksymalnie {MAX_FILES_PER_UPLOAD} plików PDF w jednym zgłoszeniu.")
                case_name = sanitize_case_name(fields.get("case_name"))
                ocr_checksum = fields.get("ocr_checksum") or "confidence"
                visual_reader = fields.get("visual_reader") or state.default_visual_reader
                case_in = resolve_under(state.input_dir, case_name)
                case_in.mkdir(parents=True, exist_ok=True)
                saved_pdfs: list[Path] = []
                for orig_name, raw_bytes in files:
                    safe_name = sanitize_pdf_filename(orig_name)
                    if len(raw_bytes) == 0:
                        raise ValueError(f"Plik '{safe_name}' jest pusty.")
                    if len(raw_bytes) > MAX_FILE_BYTES:
                        raise OverflowError(f"Plik '{safe_name}' przekracza limit 25 MB.")
                    if not raw_bytes[:8].lstrip().startswith(b"%PDF-"):
                        raise ValueError(f"Plik '{safe_name}' nie ma poprawnego nagłówka PDF (%PDF-).")
                    dest = resolve_under(case_in, safe_name)
                    dest.write_bytes(raw_bytes)
                    saved_pdfs.append(dest)
                job = state.start_job(
                    case_name,
                    saved_pdfs,
                    ocr_checksum=ocr_checksum,
                    visual_reader=visual_reader,
                    force_fail=force_fail,
                )
                self._send_json(HTTPStatus.ACCEPTED, job.to_dict())
                return

            payload = json.loads(body.decode("utf-8") or "{}")
            case_name = sanitize_case_name(payload.get("case_name"))
            ocr_checksum = payload.get("ocr_checksum") or "confidence"
            visual_reader = payload.get("visual_reader") or state.default_visual_reader
            case_in = resolve_under(state.input_dir, case_name)
            if not case_in.is_dir():
                raise FileNotFoundError(f"Katalog sprawy '{case_name}' nie istnieje w input/.")
            pdfs = sorted(case_in.glob("*.pdf"))
            if not pdfs:
                raise ValueError(f"Brak plików PDF w input/{case_name}/.")
            job = state.start_job(
                case_name,
                pdfs,
                ocr_checksum=ocr_checksum,
                visual_reader=visual_reader,
                force_fail=force_fail,
            )
            self._send_json(HTTPStatus.ACCEPTED, job.to_dict())

        def _serve_asset(self, rel_name: str) -> None:
            target = resolve_under(ASSETS_DIR, rel_name)
            if not target.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Brak zasobu: {rel_name}"})
                return
            mime, _ = mimetypes.guess_type(target.name)
            ctype = mime or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self._send_bytes(HTTPStatus.OK, ctype, target.read_bytes())

    return Handler


def create_server(host: str, port: int, state: WebAppState) -> ThreadingHTTPServer:
    ThreadingHTTPServer.allow_reuse_address = True
    return ThreadingHTTPServer((host, port), make_handler(state))


def _make_mock_backend():
    """Szybki, deterministyczny backend demonstracyjno-testowy (tylko po jawnym --mock-extractor)."""
    class MockBackend:
        name = "MockBackend (tryb testowy bez LLM)"
        last_stats = {"wygenerowane": 24, "stan_z_pamieci": True, "czas_s": 0.05}

        def complete(self, system: str, user: str, prefill: str, max_tokens: int) -> str:
            text_part = user.split("TEKST DOKUMENTU:", 1)[-1]
            if "Przelew" in prefill or "przelew_bankowy" in user:
                return "## przelew_bankowy\ndata_operacji: 2025-06-15\nkwota: 17,00\nna_rachunek: -\nnumer_transakcji: -\ntytul: Opłata skarbowa\nz_rachunku: -"
            if "mocodawca" in user.lower():
                return "## mocodawca 1\ndata.typ: osoba_prawna\ndata.nazwa: -\ndata.imie_nazwisko: -\ndata.krs: -\ndata.nip: -\npodpisujacy: -\n## pelnomocnicy 1\nimie_nazwisko: -\npesel: -"
            m_date = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{2}\.\d{4})", text_part)
            m_nip = re.search(r"NIP[:\s]*([\d\- ]{10,13})", text_part, re.I)
            return (
                "## OdwolanieKIO\n"
                f"data: {m_date.group(1) if m_date else '-'}\n"
                "czynnosc_dzien: -\n"
                "czynnosc_powod_id: 4\n"
                "miejscowosc: -\n"
                "## Odwolujacy 1\n"
                "krs: -\nnazwa: -\n"
                f"nip: {m_nip.group(1).strip() if m_nip else '-'}\n"
                "regon: -\nprzez-pelnomocnika: 0\n"
                "pelnomocnik.imie_nazwisko: -\npelnomocnik.nazwa: -\npelnomocnik.mail: -\n"
                "## Zamawiajacy 1\n"
                "krs: -\nnazwa: -\nnip: -\nregon: -\nprowadzacy_postepowanie: -\n"
                "## ZamowieniePubliczne\n"
                "numer_bzp: -\nnumer_postepowania: -\nnumer_ted: -\ntytul: -"
            )

    return MockBackend()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="odwolania2json.web", description="Interfejs webowy Odwołania2json (UZP/KIO)")
    ap.add_argument("--host", default=os.environ.get("O2J_WEB_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("O2J_WEB_PORT", "8080")))
    ap.add_argument("--input", type=Path, default=APP_ROOT / "input")
    ap.add_argument("--output", type=Path, default=APP_ROOT / "output")
    ap.add_argument("--trace", type=Path, default=APP_ROOT / "trace")
    ap.add_argument("--classes", type=Path, default=APP_ROOT / "configs" / "classes")
    ap.add_argument("--cross-checks", type=Path, default=APP_ROOT / "configs" / "cross_checks.yaml")
    ap.add_argument("--model", default=os.environ.get("O2J_MODEL", str(APP_ROOT / "models" / "Qwen3.5-4B-Q4_K_M.gguf")))
    ap.add_argument("--threads", type=int, default=int(os.environ.get("O2J_THREADS", default_threads())))
    ap.add_argument("--visual-reader", choices=("off", "on"), default=os.environ.get("O2J_VISUAL_READER", "off"))
    ap.add_argument("--mmproj", default=os.environ.get("O2J_MMPROJ", str(APP_ROOT / "models" / "mmproj-F16.gguf")))
    ap.add_argument("--mock-extractor", action="store_true", help="tryb testowy bez ładowania GGUF")
    ap.add_argument("--enable-test-seam", action="store_true", help="włącza deterministyczne wstrzykiwanie błędów (X-Test-Fail)")
    args = ap.parse_args(argv)

    state = WebAppState(
        input_dir=args.input,
        output_dir=args.output,
        trace_dir=args.trace,
        classes_dir=args.classes,
        cross_checks_path=args.cross_checks,
        model_path=args.model,
        threads=args.threads,
        mmproj_path=args.mmproj,
        default_visual_reader=args.visual_reader,
        backend_factory=_make_mock_backend if args.mock_extractor else None,
        enable_test_seam=args.enable_test_seam,
    )
    server = create_server(args.host, args.port, state)
    print(f"Odwołania2json Web UI: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
