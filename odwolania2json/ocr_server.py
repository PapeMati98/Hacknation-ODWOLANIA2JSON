"""Usługa OCR po API: czyta strony-skany tym samym kodem co aplikacja (pdfio.ocr_page), ale na serwerze -
na karcie graficznej albo na wielu rdzeniach. Aplikacja na laptopie wysyła plik PDF i numery stron,
a dostaje linie tekstu z pewnością, odczyty alternatywne i położenie czarnych prostokątów anonimizacji.

  python -m odwolania2json.ocr_server --port 11462 [--cuda] [--workers 2]

  POST /ocr?pages=0,1      treść: plik PDF, nagłówek Authorization: Bearer <klucz>
  GET  /health

Klucz podaje zmienna O2J_OCR_KEY (bez niej usługa przyjmuje każde zapytanie - tylko do prób na 127.0.0.1).
Usługa niczego nie zapisuje na dysku i nie wypisuje treści dokumentów.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import sys
import time
import urllib.parse
from concurrent.futures import ProcessPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pypdfium2 as pdfium

from . import pdfio

MAX_BODY = 40 * 2 ** 20         # największy przyjmowany plik
MAX_PAGES = 6                   # najwięcej stron w jednym zapytaniu


def _init_worker(threads: int, cuda: bool) -> None:
    pdfio.OCR_THREADS, pdfio.OCR_CUDA = threads, cuda


def read_pdf(data: bytes, indices: list[int]) -> dict:
    pdf = pdfium.PdfDocument(data)
    pages = {}
    for i in indices:
        if 0 <= i < len(pdf):
            lines, reads, redactions = pdfio.ocr_page(pdf[i], all_reads=True)
            pages[str(i)] = {"lines": [[l.text, l.conf, l.y, l.box, l.lay, l.angle] for l in lines],
                             "reads": {str(dpi): text for dpi, text in reads.items()}, "redactions": redactions}
    return {"pages": pages}


def make_server(host: str, port: int, key: str | None, pool=None) -> ThreadingHTTPServer:
    """`pool` = None: odczyt w wątku zapytania (testy, jeden proces); inaczej pula procesów roboczych."""
    stats = {"zapytania": 0, "strony": 0, "czas_s": 0.0}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:        # bez dziennika zapytań (żadnych danych dokumentów)
            pass

        def reply(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=float).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.rstrip("/").endswith("/health"):
                self.reply(200, {"status": "ok", **stats})
            else:
                self.reply(404, {"error": "nie ma takiego adresu"})

        def do_POST(self) -> None:
            url = urllib.parse.urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if not url.path.rstrip("/").endswith("/ocr"):
                self.close_connection = True
                return self.reply(404, {"error": "nie ma takiego adresu"})
            if key and not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {key}"):
                self.close_connection = True
                return self.reply(401, {"error": "brak albo zły klucz API"})
            if not 0 < length <= MAX_BODY:
                self.close_connection = True
                return self.reply(413, {"error": f"plik musi mieć od 1 bajta do {MAX_BODY // 2 ** 20} MB"})
            data = self.rfile.read(length)
            try:
                indices = [int(p) for p in urllib.parse.parse_qs(url.query).get("pages", ["0"])[0].split(",")][:MAX_PAGES]
            except ValueError:
                return self.reply(400, {"error": "parametr pages: numery stron po przecinku, od 0"})
            t0 = time.perf_counter()
            try:
                result = pool.submit(read_pdf, data, indices).result() if pool else read_pdf(data, indices)
            except Exception as exc:                 # zły plik albo błąd silnika - klient przeczyta lokalnie
                return self.reply(422, {"error": f"nie udało się odczytać pliku: {type(exc).__name__}"})
            stats["zapytania"] += 1
            stats["strony"] += len(result["pages"])
            stats["czas_s"] = round(stats["czas_s"] + time.perf_counter() - t0, 2)
            self.reply(200, result)

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="odwolania2json.ocr_server", description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=11462)
    ap.add_argument("--cuda", action="store_true", help="silnik OCR na karcie graficznej (wymaga onnxruntime-gpu)")
    ap.add_argument("--workers", type=int, default=0, help="procesy robocze (domyślnie: 2 z kartą, połowa rdzeni bez)")
    ap.add_argument("--threads", type=int, default=0, help="wątki silnika na proces (domyślnie: 2 z kartą, 1 bez)")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    workers = args.workers or (2 if args.cuda else max(1, (os.cpu_count() or 4) // 2))
    threads = args.threads or (2 if args.cuda else 1)
    key = os.environ.get("O2J_OCR_KEY")
    with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(threads, args.cuda)) as pool:
        server = make_server(args.host, args.port, key, pool)
        print(f"Usługa OCR: http://{args.host}:{args.port}/ocr | procesy: {workers} | karta graficzna: "
              f"{'tak' if args.cuda else 'nie'} | klucz: {'wymagany' if key else 'BRAK (tylko do prób lokalnych)'}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
