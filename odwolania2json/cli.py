"""Interfejs wiersza poleceń: input/<sprawa>/*.pdf -> output/<sprawa>/<nazwa>.json.

Dokument nierozpoznany jako żadna klasa (np. ogłoszenie TED) dostaje pusty plik JSON: {}.
Ślad ekstrakcji (klasa, wyniki klasyfikacji, odpowiedź modelu, źródło i status każdego pola)
trafia do katalogu trace/, a nie do output/. Dla każdej sprawy powstaje też
trace/<sprawa>/do_sprawdzenia.json: pola odrzucone przez weryfikację (z proponowaną wartością)
oraz rozbieżności między dokumentami sprawy - lista dla człowieka.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

from . import extract, pdfio
from .config import load_classes
from .crosscheck import case_findings, load_rules, review_entries
from .extract import Extractor, classify
from .llm import make_backend

APP_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="odwolania2json", description=__doc__)
    ap.add_argument("--input", type=Path, default=APP_ROOT / "input")
    ap.add_argument("--output", type=Path, default=APP_ROOT / "output")
    ap.add_argument("--trace", type=Path, default=APP_ROOT / "trace")
    ap.add_argument("--classes", type=Path, default=APP_ROOT / "configs" / "classes")
    ap.add_argument("--cross-checks", type=Path, default=APP_ROOT / "configs" / "cross_checks.yaml")
    ap.add_argument("--model", default=os.environ.get("O2J_MODEL", str(APP_ROOT / "models" / "Qwen3.5-4B-Q4_K_M.gguf")))
    ap.add_argument("--threads", type=int, default=int(os.environ.get("O2J_THREADS", default_threads())))
    ap.add_argument("--only", help="przetwórz tylko te sprawy (lista po przecinku)")
    ap.add_argument("--ocr-workers", type=int, default=int(os.environ.get("O2J_OCR_WORKERS", default_ocr_workers())),
                    help="ile procesów naraz wczytuje dokumenty (OCR skanów); 1 = bez procesów roboczych")
    ap.add_argument("--ocr-checksum", choices=("confidence", "strict"), default=extract.CHECKSUM_POLICY,
                    help="numer ze skanu ze złą sumą kontrolną: confidence = zostaje z ostrzeżeniem przy wysokiej "
                         "pewności odczytu, inaczej null (domyślnie); strict = zawsze null")
    ap.add_argument("--visual-reader", choices=("off", "on"), default=os.environ.get("O2J_VISUAL_READER", "off"),
                    help="czytelnik wizualny: drugi odczyt wycinków linii skanu modelem z projektorem obrazu "
                         "(wymaga pliku --mmproj); potwierdza albo wetuje wartości o nie-wysokiej pewności")
    ap.add_argument("--final-check", choices=("off", "note", "veto"), default=os.environ.get("O2J_FINAL_CHECK", "off"),
                    help="końcowa ocena modelem pól z opcją `check` w YAML (pytanie TAK/NIE: czy wartość jest tym, czym "
                         "ma być): note = odpowiedź NIE dopisuje pole do listy do sprawdzenia, veto = dodatkowo zeruje pole")
    ap.add_argument("--mmproj", default=os.environ.get("O2J_MMPROJ", str(APP_ROOT / "models" / "mmproj-F16.gguf")))
    ap.add_argument("--resume", action="store_true",
                    help="pomiń dokumenty, które mają już wynik w katalogu output (wznowienie przerwanego przebiegu)")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    extract.CHECKSUM_POLICY = args.ocr_checksum

    classes = load_classes(args.classes)
    by_name = {c.name: c for c in classes}
    only = set(args.only.split(",")) if args.only else None
    pdfs = sorted(p for p in args.input.rglob("*.pdf") if not only or p.parent.name in only)
    print(f"Dokumentów: {len(pdfs)} | klasy: {', '.join(by_name)}", flush=True)
    t_all = time.perf_counter()
    cases: dict[Path, dict] = {}         # sprawa -> wyniki dokumentów i pozycje do sprawdzenia
    todo = []
    for pdf in pdfs:
        rel = pdf.relative_to(args.input).with_suffix(".json")
        if args.resume and restore(args, rel, cases):
            print(f"  {rel}: wynik już jest (--resume)", flush=True)
        else:
            todo.append((pdf, rel))

    # Model po API (O2J_API_BASE): ekstrakcja biegnie równolegle z czytaniem kolejnych dokumentów.
    extractor = None
    if os.environ.get("O2J_API_BASE"):
        backend = make_backend(args.model, args.threads)
        problem = backend.ping()
        if problem is None:
            extractor = Extractor(backend, final_check=args.final_check)
            print(f"Model: {backend.name} | dokumentów naraz: {backend.parallel}", flush=True)
        elif Path(args.model).is_file():
            print(f"UWAGA: {problem}\n       Przechodzę na model lokalny {Path(args.model).name} (wolniej).", flush=True)
            os.environ.pop("O2J_API_BASE")
        else:
            print(f"BŁĄD: {problem}", flush=True)
            return 2
    streaming = extractor is not None

    done = 0
    failed: list[str] = []
    t_extract = time.perf_counter()

    def extract_one(cls_name: str, rel: Path, doc, record: dict):
        t0 = time.perf_counter()
        error = None
        try:
            data, trace, answer = extractor.run(doc, by_name[cls_name])
        except Exception as exc:                     # jeden dokument nie może zatrzymać całej partii
            data, trace, answer, error = {}, [], "", f"{type(exc).__name__}: {exc}"
            record["blad"] = error
        out_path = args.output / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        record.update(pola=trace, odpowiedz_modelu=answer, czas_ekstrakcji_s=round(time.perf_counter() - t0, 2),
                      model=getattr(extractor.backend, "last_stats", None))
        write_trace(args.trace, rel, record)
        return cls_name, rel, data, trace, time.perf_counter() - t0, error

    def collect(result, total: int) -> None:
        nonlocal done
        cls_name, rel, data, trace, seconds, error = result
        done += 1
        if error:
            failed.append(str(rel))
            print(f"  [{done}/{total}] {rel}: BŁĄD - {error} -> pusty JSON", flush=True)
            return
        flagged = sum(1 for t in trace if t["status"] in ("nieczytelne", "niezweryfikowane"))
        left = (time.perf_counter() - t_extract) / done * (total - done)
        print(f"  [{done}/{total}] {rel}: {cls_name} | {seconds:.1f} s | pola odrzucone: {flagged}"
              f" | pozostało ok. {left / 60:.0f} min", flush=True)
        case = cases.setdefault(rel.parent, {"results": [], "review": []})
        case["results"].append((rel.name, cls_name, data))
        case["review"] += review_entries(rel.name, trace)

    # Etap 1: wczytanie (tekst lub OCR) i klasyfikacja. Skany czyta kilka procesów naraz.
    workers = max(1, min(args.ocr_workers, len(todo) or 1))
    ocr_threads = max(1, (os.cpu_count() or 4) // workers) if workers > 1 else 0
    jobs = []
    api_pool = ThreadPoolExecutor(extractor.backend.parallel) if streaming else None
    pending: dict = {}                   # zadanie ekstrakcji -> jego argumenty (do ponowienia po błędzie API)

    def classified(pdf: Path, rel: Path, doc, cls_name, scores, seconds: float) -> None:
        record = {"plik": str(pdf), "skan": doc.is_scan, "klasa": cls_name, "punkty_klas": scores,
                  "nieczytelne_linie": sum(p.unreadable for p in doc.pages), "czas_wczytania_s": seconds}
        if cls_name is None:
            # Wymóg organizatora (README, 21.11): dokument spoza klas dostaje pusty plik JSON.
            out_path = args.output / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text("{}", encoding="utf-8")
            print(f"  {rel}: dokument spoza klas -> pusty JSON {scores}", flush=True)
            write_trace(args.trace, rel, record)
        elif streaming:
            job = (cls_name, rel, doc, record)
            pending[api_pool.submit(extract_one, *job)] = job
        else:
            jobs.append((cls_name, rel, doc, record))

    if workers == 1:
        _init_reader(str(args.classes), 0)
        for pdf, rel in todo:
            classified(pdf, rel, *read_document(str(pdf)))
    else:
        with ProcessPoolExecutor(workers, initializer=_init_reader, initargs=(str(args.classes), ocr_threads)) as readers:
            reads = {readers.submit(read_document, str(pdf)): (pdf, rel) for pdf, rel in todo}
            for future in as_completed(reads):
                classified(*reads[future], *future.result())
    waiting = len(pending) if streaming else len(jobs)
    print(f"Wczytano i sklasyfikowano w {time.perf_counter() - t_all:.0f} s (procesy OCR: {workers}); "
          f"do ekstrakcji: {waiting}", flush=True)

    # Etap 2: ekstrakcja. Model lokalny: po kolei, pogrupowana klasami - stała część promptu zostaje w cache modelu.
    if streaming:
        again = []
        for future in as_completed(pending):
            result = future.result()
            if result[5] and "Model po API nie odpowiada" in result[5]:
                again.append(pending[future])      # serwer nie odpowiedział: druga próba po całej partii
            else:
                collect(result, len(pending))
        api_pool.shutdown()
        if again and not extractor.backend.unavailable:
            print(f"Ponawiam {len(again)} dokumentów, przy których serwer modelu nie odpowiedział", flush=True)
        for job in again:
            job[3].pop("blad", None)
            collect(extract_one(*job), len(pending))
    elif jobs:
        extractor = Extractor(make_backend(args.model, args.threads), final_check=args.final_check)
        print(f"Model: {extractor.backend.name}", flush=True)
        if args.visual_reader == "on":
            if not hasattr(extractor.backend, "enable_vision") or not Path(args.mmproj).is_file():
                print(f"Czytelnik wizualny wyłączony: brak pliku {args.mmproj} albo model nie jest lokalny", flush=True)
            else:
                from .vision import VisualReader
                extractor.backend.enable_vision(args.mmproj)
                extract.VISUAL_READER = VisualReader(extractor.backend)
                print(f"Czytelnik wizualny: {Path(args.mmproj).name}", flush=True)
        t_extract = time.perf_counter()
        for job in sorted(jobs, key=lambda j: (j[0], str(j[1]))):
            collect(extract_one(*job), len(jobs))
    if failed:
        print(f"UWAGA: {len(failed)} dokumentów bez wyniku (pusty JSON): {', '.join(failed)}", flush=True)

    # Etap 3: kontrola krzyżowa między dokumentami sprawy i lista pozycji do sprawdzenia przez człowieka.
    rules = load_rules(args.cross_checks)
    total = 0
    for case_dir, case in sorted(cases.items()):
        items = case["review"] + case_findings(rules, case["results"])
        total += len(items)
        path = args.trace / case_dir / "do_sprawdzenia.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"sprawa": str(case_dir), "pozycje": items}, ensure_ascii=False, indent=1,
                                   default=str), encoding="utf-8")
    print(f"Pozycji do sprawdzenia: {total} (trace/<sprawa>/do_sprawdzenia.json)", flush=True)
    seconds = time.perf_counter() - t_all
    print(f"Gotowe: {len(pdfs)} dokumentów w {seconds:.0f} s ({seconds / max(1, len(pdfs)):.1f} s na dokument)", flush=True)
    return 0


CLASSIFY_PAGES = 2          # tyle pierwszych stron wystarcza do rozpoznania klasy
_CLASSES: list = []


def _init_reader(classes_dir: str, ocr_threads: int) -> None:
    """Przygotowanie procesu czytającego dokumenty: klasy z YAML i liczba wątków silnika OCR."""
    global _CLASSES
    pdfio.OCR_THREADS = ocr_threads
    _CLASSES = load_classes(Path(classes_dir))


def read_document(path: str):
    """Wczytanie i klasyfikacja jednego dokumentu. Najpierw strony potrzebne do rozpoznania klasy, potem -
    tylko jeśli klasa ich wymaga (`pages` w YAML) - kolejne: każda strona skanu to pełny OCR."""
    t0 = time.perf_counter()
    doc = pdfio.load(path, max_pages=CLASSIFY_PAGES)
    cls_name, scores = classify(doc, _CLASSES)
    if cls_name is not None:
        doc.ensure_pages(next(c.pages for c in _CLASSES if c.name == cls_name))
        doc.alt_text(pdfio.ALT_DPIS[0], 1)      # drugi odczyt 1. strony skanu: potrzebny prawie zawsze (daty, kwoty, numery)
    return doc, cls_name, scores, round(time.perf_counter() - t0, 2)


def default_ocr_workers() -> int:
    """Procesy czytające skany: po jednym na rdzeń fizyczny (zwykle połowa rdzeni logicznych), najwyżej 8."""
    return max(1, min(8, (os.cpu_count() or 4) // 2))


def default_threads() -> int:
    """llama.cpp na CPU jest ograniczone przepustowością pamięci: więcej niż ~6 wątków nie przyspiesza."""
    return max(1, min(6, (os.cpu_count() or 4) // 2))


def restore(args, rel: Path, cases: dict) -> bool:
    """Wznowienie: wczytuje gotowy wynik dokumentu i jego ślad, żeby kontrola krzyżowa sprawy była pełna."""
    out_path, trace_path = args.output / rel, args.trace / rel.with_suffix(".trace.json")
    if not out_path.is_file() or not trace_path.is_file():
        return False
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
        record = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not record.get("klasa") or "pola" not in record:
        return False
    case = cases.setdefault(rel.parent, {"results": [], "review": []})
    case["results"].append((rel.name, record["klasa"], data))
    case["review"] += review_entries(rel.name, record["pola"])
    return True


def write_trace(trace_dir: Path, rel: Path, record: dict) -> None:
    path = trace_dir / rel.with_suffix(".trace.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
