"""Eksperyment i bramka końcowej walidacji modelem (bez OCR i bez dokumentów - same wartości z gold).

Mierzy dwie rzeczy na wartościach wzorcowych ze spraw nie-hold-out:
  korekta  - model przepisuje wartość zepsutą jak przez OCR (zgubione polskie znaki, „z 0.o.”); liczymy,
             ile zepsutych wartości wraca do wzorca i ile poprawnych wartości model psuje (z bezpiecznikiem
             w kodzie i bez niego),
  ocena    - pytanie zamknięte TAK/NIE „czy »X« to <rodzaj wartości>?”; liczymy fałszywe NIE dla wartości
             wzorcowych i wykrycie dla wartości oczywiście złych (etykiety formularzy, wartości innego rodzaju).

  python tools/gate_sanity.py --manifest ../eval/manifest.json --manifest ../eval/skany-manifest.json --report sanity.json
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odwolania2json.sanity import KINDS, accept_correction, correction_prompt, question_prompt   # noqa: E402
from odwolania2json.textmatch import bare                                                          # noqa: E402

LABELS = ["Szczegóły płatności", "Szczegóły zlecenia", "Dane odbiorcy", "Dane nadawcy", "Tytuł", "Opis", "Przelew krajowy",
          "Nazwa kontrahenta", "Rachunek zleceniodawcy", "Data operacji", "Kwota", "Typ transakcji", "Status wykonane",
          "Prezes Zarządu", "Członek Zarządu", "radca prawny", "Prokurent", "Za Mocodawcę", "PEŁNOMOCNICTWO", "ODWOŁANIE",
          "reprezentowany przez pełnomocnika", "adres do korespondencji", "Zamawiający", "Odwołujący", "dnia", "ul. Polna 115"]
PATHS = {
    "person": [("Odwolujacy", "pelnomocnik", "imie_nazwisko"), ("mocodawca", "podpisujacy", "imie_nazwisko"),
               ("pelnomocnicy", "imie_nazwisko"), ("mocodawca", "data", "imie_nazwisko")],
    "organization": [("Odwolujacy", "nazwa"), ("Zamawiajacy", "nazwa"), ("mocodawca", "data", "nazwa"),
                     ("Odwolujacy", "pelnomocnik", "nazwa")],
    "place": [("OdwolanieKIO", "miejscowosc")],
    "title": [("przelew_bankowy", "tytul")],
}


def values_at(node, path):
    if not path:
        return [node] if isinstance(node, str) and node.strip() else []
    if isinstance(node, list):
        return [v for item in node for v in values_at(item, path)]
    if isinstance(node, dict):
        return values_at(node.get(path[0]), path[1:])
    return []


def damage(value: str, rng: random.Random) -> str | None:
    """Wartość zepsuta jak przez OCR: zgubione polskie znaki albo zero w „o.o.”."""
    if "z o.o." in value and rng.random() < 0.5:
        return value.replace("z o.o.", "z 0.o.")
    plain = "".join({"ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ź": "z", "ż": "z",
                     "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N", "Ó": "O", "Ś": "S", "Ź": "Z", "Ż": "Z"}.get(c, c)
                    for c in value)
    return plain if plain != value else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, action="append", required=True)
    ap.add_argument("--model", default=str(Path(__file__).resolve().parent.parent / "models" / "Qwen3.5-4B-Q4_K_M.gguf"))
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--per-kind", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(args.seed)

    pool: dict[str, list[str]] = {k: [] for k in PATHS}
    for m in args.manifest:
        for item in json.loads(m.read_text(encoding="utf-8")):
            if not item.get("gold") or item.get("split") == "holdout":
                continue
            gold = json.loads(Path(item["gold"]).read_text(encoding="utf-8"))
            for kind, paths in PATHS.items():
                for path in paths:
                    pool[kind] += values_at(gold, path)
    for kind in pool:
        unique = sorted(set(pool[kind]))
        rng.shuffle(unique)
        pool[kind] = unique[: args.per_kind]
    print({k: len(v) for k, v in pool.items()}, flush=True)

    from odwolania2json.llm import LlamaCppBackend
    backend = LlamaCppBackend(args.model, args.threads)
    times, rows = [], []

    def run(prompt: str, max_tokens: int) -> str:
        t0 = time.perf_counter()
        text = backend.say(prompt, max_tokens)
        times.append(time.perf_counter() - t0)
        return text

    # --- korekta zapisu
    fix = {"zepsute": 0, "naprawione": 0, "naprawione_z_bezpiecznikiem": 0, "pogorszone_z_bezpiecznikiem": 0,
           "poprawne": 0, "zmienione_poprawne": 0, "zmienione_poprawne_z_bezpiecznikiem": 0}
    for kind, values in pool.items():
        for value in values:
            read = run(correction_prompt(kind, value), 64)
            fix["poprawne"] += 1
            fix["zmienione_poprawne"] += read != value
            kept = read if accept_correction(value, read) else value
            fix["zmienione_poprawne_z_bezpiecznikiem"] += kept != value
            rows.append({"test": "korekta_poprawnej", "rodzaj": kind, "wartosc": value, "model": read, "przyjeto": kept})
            broken = damage(value, rng)
            if broken is None:
                continue
            read = run(correction_prompt(kind, broken), 64)
            kept = read if accept_correction(broken, read) else broken
            fix["zepsute"] += 1
            fix["naprawione"] += read == value
            fix["naprawione_z_bezpiecznikiem"] += kept == value
            fix["pogorszone_z_bezpiecznikiem"] += kept not in (value, broken)
            rows.append({"test": "korekta_zepsutej", "rodzaj": kind, "wzorzec": value, "wartosc": broken, "model": read, "przyjeto": kept})
            print(f"  {kind:12} {broken!r} -> {read!r} {'OK' if kept == value else ('bez zmian' if kept == broken else 'ŹLE')}", flush=True)

    # --- ocena TAK/NIE
    judge = {"wzorcowe": 0, "falszywe_nie": 0, "zle": 0, "wykryte": 0}
    for kind, values in pool.items():
        wrong = LABELS + [v for other, vs in pool.items() if other != kind for v in vs[:6]
                          if not (kind == "organization" and other == "place") and not (kind == "title")]
        if kind == "title":
            wrong = LABELS
        for value in values:
            answer = run(question_prompt(kind, value), 3)
            judge["wzorcowe"] += 1
            bad = answer.strip().upper().startswith("NIE")
            judge["falszywe_nie"] += bad
            rows.append({"test": "ocena_wzorcowej", "rodzaj": kind, "wartosc": value, "model": answer})
            if bad:
                print(f"  fałszywe NIE: {kind} {value!r}", flush=True)
        for value in wrong:
            answer = run(question_prompt(kind, value), 3)
            judge["zle"] += 1
            hit = answer.strip().upper().startswith("NIE")
            judge["wykryte"] += hit
            rows.append({"test": "ocena_zlej", "rodzaj": kind, "wartosc": value, "model": answer})
            if not hit:
                print(f"  niewykryte: {kind} {value!r} -> {answer!r}", flush=True)

    summary = {"rodzaje": {k: KINDS[k] for k in pool}, "korekta": fix, "ocena": judge,
               "mediana_s": round(statistics.median(times), 2), "pytan": len(times), "watki": args.threads}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.report:
        args.report.write_text(json.dumps({"podsumowanie": summary, "wiersze": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
