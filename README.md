# Odwołania2json

Rozwiązanie zadania **Odwołania2json** (Urząd Zamówień Publicznych, HackNation 2026): zamienia dokumenty PDF sprawy odwoławczej KIO — odwołanie, pełnomocnictwo, potwierdzenie przelewu — na pliki JSON zgodne ze schematem organizatora.

- Działa **lokalnie na CPU, bez GPU**. Wyłącznie komponenty open source (Apache-2.0 / MIT / BSD).
- Obsługuje PDF-y z warstwą tekstową i **skany** (OCR).
- Dokument spoza obsługiwanych klas (np. ogłoszenie TED) jest pomijany — nie powstaje dla niego JSON.
- Nową klasę dokumentu dodaje się **jednym plikiem YAML, bez zmian w kodzie**.
- Każda wartość jest weryfikowana, także krzyżowo (dwa niezależne odczyty skanu, zgodność między dokumentami sprawy). Wartość niepewna trafia do wyniku jako `null`, a razem z proponowanym odczytem i powodem — na listę `do_sprawdzenia.json` dla człowieka. Zasada projektu: *lepiej przekazać pole do sprawdzenia, niż wpisać błędną wartość*.

## Uruchomienie

Wymagania: Windows lub Linux, Python 3.13+, ok. 4 GB wolnego RAM, ok. 3,5 GB na dysku (model).

```bat
start.bat
```

Skrypt przy pierwszym uruchomieniu tworzy środowisko `.venv`, instaluje zależności z `requirements.txt` i pobiera model. Potem przetwarza wszystko z folderu `input`.

Ręcznie:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
.venv/Scripts/python tools/download_models.py
.venv/Scripts/python -m odwolania2json
```

Docker (Linux / Windows / macOS):

```bash
docker compose up --build
```

Kontener czyta `./input`, zapisuje do `./output` i `./trace`, a model trzyma w `./models` (brakujący pobiera przy pierwszym starcie). Modele OCR są w obrazie.

### Wejście i wyjście

```
input/                          output/
├── case1/                      ├── case1/
│   ├── odwolanie_nr_1.pdf      │   ├── odwolanie_nr_1.json
│   ├── pelnomocnictwo_nr_1.pdf │   ├── pelnomocnictwo_nr_1.json
│   └── przelew_nr_1.pdf        │   └── przelew_nr_1.json
```

Plik JSON ma tę samą nazwę co PDF i leży w podfolderze tej samej sprawy. Obok powstaje folder `trace/`:

- `trace/<sprawa>/<plik>.trace.json` — ślad ekstrakcji dokumentu (klasa, odpowiedź modelu, źródło i status każdego pola),
- `trace/<sprawa>/do_sprawdzenia.json` — lista dla człowieka: pola odrzucone przez weryfikację (z proponowaną wartością i powodem) oraz rozbieżności między dokumentami sprawy.

### Parametry

| Parametr / zmienna | Znaczenie | Domyślnie |
|---|---|---|
| `--input`, `--output`, `--trace` | foldery robocze | `input`, `output`, `trace` |
| `--classes` | folder z klasami dokumentów | `configs/classes` |
| `--model` / `O2J_MODEL` | plik GGUF modelu lokalnego | `models/Qwen3.5-4B-Q4_K_M.gguf` |
| `--cross-checks` | reguły kontroli krzyżowej między dokumentami sprawy | `configs/cross_checks.yaml` |
| `--threads` / `O2J_THREADS` | liczba wątków CPU | połowa rdzeni, najwyżej 6 |
| `--ocr-checksum` / `O2J_OCR_CHECKSUM` | numer ze skanu ze złą sumą kontrolną: `strict` = `null` i pozycja do sprawdzenia; `agree` = zostaje z ostrzeżeniem, gdy potwierdza go inny, niezależny odczyt OCR | `strict` |
| `O2J_API_BASE`, `O2J_API_MODEL`, `O2J_API_KEY` | model serwowany przez API zgodne z OpenAI (zamiast lokalnego) | — |

## Architektura

```
PDF ──► pdfio ──► classify ──► extract (LLM) ──► walidacja pól ──► kontrola krzyżowa ──► JSON
         │           │              │                 │                   │              + trace
   tekst lub OCR   klasy YAML   formularz z YAML   validators        crosscheck         + do_sprawdzenia
   (dwa odczyty)                                  + textmatch    + cross_checks.yaml
```

| Moduł | Rola |
|---|---|
| `odwolania2json/pdfio.py` | Warstwa tekstowa PDF; gdy jej brak — OCR na CPU (RapidOCR, modele PP-OCR przez ONNX Runtime). Każda strona skanu jest czytana dwa razy w różnej rozdzielczości: linie o niskiej pewności są zastępowane lepszym odczytem albo dostają znacznik `[NIECZYTELNE]`, a drugi odczyt służy do kontroli krzyżowej wartości. |
| `odwolania2json/config.py` | Wczytuje klasy dokumentów z YAML; buduje z nich formularz i opis pól dla modelu. |
| `odwolania2json/extract.py` | Klasyfikacja (słowa kluczowe i tytuł z YAML, próg odrzucenia) oraz ekstrakcja: model wypełnia zwięzły formularz `klucz: wartość`, kod zamienia go na JSON i weryfikuje każde pole. |
| `odwolania2json/llm.py` | Model językowy: lokalnie przez llama.cpp (Qwen3.5-4B, Apache-2.0) albo przez API zgodne z OpenAI. |
| `odwolania2json/validators.py` | Sumy kontrolne NIP / REGON / PESEL / NRB, format KRS, daty, numery BZP i TED, kwoty, e-mail, nazwiska bez tytułów; naprawa typowych pomyłek OCR o jeden znak. |
| `odwolania2json/textmatch.py` | Sprawdza, czy wartość faktycznie występuje w dokumencie; zastępuje niedokładnie przepisaną wartość dosłownym fragmentem tekstu, dociąga niepełne numery, porównuje dwa odczyty OCR. |
| `odwolania2json/crosscheck.py` | Kontrola krzyżowa: ten sam numer w kilku polach, zgodność między dokumentami sprawy, lista pozycji do sprawdzenia. |
| `odwolania2json/cli.py` | Przetwarzanie folderu `input`; dokumenty są grupowane klasami, żeby model czytał stałą część promptu tylko raz na klasę. |

### Dlaczego formularz, a nie JSON prosto z modelu
Na CPU czas zależy głównie od liczby generowanych tokenów. Formularz `klucz: wartość` jest około dwa razy krótszy niż JSON z tymi samymi danymi, a strukturę JSON (zagnieżdżenia, typy, pola wyliczane ze słowników) deterministycznie odtwarza kod.

Model lokalny wypełnia formularz w sposób prowadzony: klucze podaje mu kod (szybkie przetwarzanie wsadowe), a model generuje wyłącznie wartości. Stan modelu po przeczytaniu instrukcji i opisu pól danej klasy jest zapamiętywany, więc dla kolejnych dokumentów tej klasy czytany jest już tylko tekst dokumentu. Lista podmiotów kończy się, gdy model przestaje podawać nowe — powtórzenie już wpisanego podmiotu jest odrzucane.

### Kontrola krzyżowa
Sprawdzenie pojedynczego pola nie wystarcza: KRS, daty, kwoty i numery ogłoszeń nie mają sumy kontrolnej, a poprawny numer może trafić do niewłaściwego podmiotu. Dlatego wynik przechodzi dodatkowe kontrole:

1. **Niezależne odczyty skanu.** Każda strona skanu jest czytana w dwóch rozdzielczościach, a przy wątpliwości w trzeciej. Wartość bez sumy kontrolnej (KRS, data, kwota, numer BZP/TED, sygnatura, numer transakcji) musi powtórzyć się w innym odczycie. Inny odczyt daje inną wartość → `null`. Inny odczyt w ogóle nie zawiera tej linii → wartość zostaje z ostrzeżeniem. Poprawka numeru o jeden znak na podstawie sumy kontrolnej jest przyjmowana tylko wtedy, gdy poprawiony numer widać w innym odczycie.
2. **Wartość musi być w dokumencie.** Dotyczy każdego pola, także dat, kwot i numerów ogłoszeń: model nie może podać wartości, której w tekście nie ma (np. przepisanej z instrukcji).
3. **Kontrola przypisania.** Ten sam NIP / KRS / REGON / rachunek nie może trafić do kilku pól. Numer zostaje przy tym podmiocie, przy którego nazwie leży w dokumencie; gdy nie da się tego ustalić — znika ze wszystkich pól.
4. **Zależności między polami** (w YAML klasy): `requires` — pole ma sens tylko razem z innym (miejscowość z nagłówka tylko z datą); `not_in` — wartość nie może powtarzać się na innej liście (podpisujący pełnomocnictwo nie może być pełnomocnikiem).
5. **Zgodność między dokumentami sprawy** (`configs/cross_checks.yaml`): Odwołujący z odwołania ↔ mocodawca z pełnomocnictwa (KRS, NIP, nazwa), pełnomocnik z odwołania ↔ pełnomocnicy z pełnomocnictwa, kolejność dat. Rozbieżność jest zgłaszana, ale nie zmienia JSON-ów — nie wiadomo, który dokument ma rację. Na 60 przykładowych sprawach organizatora reguły nie dają ani jednego fałszywego alarmu.

Reguły między dokumentami dopisuje się w YAML, bez zmian w kodzie (rodzaje: `same`, `not_after`, `one_of`).

### Weryfikacja wartości
Dla każdego pola w `trace/<sprawa>/<plik>.trace.json` zapisywane są: wartość surowa z modelu, wartość końcowa, źródło (`warstwa_tekstowa` / `ocr`) oraz status:

| Status | Znaczenie |
|---|---|
| `ok` | wartość przeszła walidację |
| `naprawiono` | błąd OCR jednego znaku poprawiony na podstawie sumy kontrolnej |
| `dopasowano` | wartość modelu zastąpiona dosłownym fragmentem dokumentu (ucięte słowo, zmieniona końcówka, niepełny numer) |
| `ostrzezenie` | wartość zachowana, ale trafia na listę do sprawdzenia: zła suma kontrolna przy odczycie dokładnym (warstwa tekstowa) albo brak potwierdzenia w drugim odczycie OCR |
| `nieczytelne` | wartość z OCR nie przechodzi walidacji i nie da się jej jednoznacznie naprawić albo dwa odczyty OCR się różnią → `null` |
| `niezweryfikowane` | wartości nie ma w tekście dokumentu, numer przypisano do kilku pól albo pole łamie regułę `requires` / `not_in` → `null` |
| `brak` | informacji nie ma w dokumencie |

## Jak dodać nową klasę dokumentu

Wystarczy dodać plik `configs/classes/<nazwa>.yaml`. Przykład — decyzja administracyjna:

```yaml
name: decyzja
description: Decyzja administracyjna wydana przez organ wobec strony.
pages: 2                       # ile pierwszych stron czytać
classify:
  title: ["decyzja"]           # słowa szukane na początku pierwszej strony
  keywords:                    # słowo -> waga
    "decyzja": 3
    "orzekam": 3
    "pouczenie": 2
  negative:
    "wnoszę odwołanie": 4
  min_score: 4                 # poniżej progu dokument nie należy do klasy
dictionaries:                  # słowniki do pól wyliczanych
  rodzaje:
    1: Pozytywna
    2: Odmowna
output:                        # struktura wynikowego JSON
  Decyzja:
    numer:
      type: string
      validator: text
      verify_in_text: true     # wartość musi występować w dokumencie
      desc: "Znak (numer) decyzji."
    data:
      type: string
      validator: date          # normalizacja do YYYY-MM-DD
      desc: "Data wydania; przepisz tak, jak jest zapisana."
    rodzaj_id:
      type: integer
      enum_from: rodzaje       # model wybiera numer ze słownika
      desc: "Rodzaj rozstrzygnięcia."
    rodzaj_opis:
      derive: {dictionary: rodzaje, key: Decyzja.rodzaj_id}   # pole wyliczane przez kod
  Strony:                      # lista - sekcja powtarzana dla każdego podmiotu
    - nazwa:
        type: string
        validator: text
        verify_in_text: true
        desc: "Nazwa strony."
      nip:
        type: string
        validator: nip
        desc: "NIP strony."
```

Dostępne walidatory: `text`, `person` (imię i nazwisko bez tytułów), `date`, `amount`, `email`, `nip`, `regon`, `pesel`, `krs`, `nrb`, `bzp`, `ted`.
Opcje pola: `verify_in_text`, `enum`, `enum_from`, `derive`, `only_if_multiple` (pole wypełniane tylko, gdy lista ma kilka elementów), `requires`, `not_in`, `output_type: integer`.
Podpowiedzi do pozycji słownika (jak dana pozycja bywa opisana w dokumentach) wpisuje się w sekcji `hints`.

## Ocena jakości

```bash
python tools/make_manifest.py --uzp <repo UZP> --gold-real <gold realny> --out eval/manifest.json
python tools/make_scandev.py --manifest eval/manifest.json --split dev --cases 10 --out eval/scandev
python -m odwolania2json --input <repo UZP>/dane --output eval/out
python tools/score.py --manifest eval/manifest.json --pred eval/out --split dev
```

- `tools/score.py` — F1 według definicji organizatora (błędna wartość = FP, brak = FN, długie teksty z progiem 80%, elementy list dopasowywane po treści).
- `tools/make_scandev.py` — zamienia tekstowe PDF-y w „skany” (render, obrót, szum, JPEG) do testu ścieżki OCR.
- `tools/replay.py` — przelicza weryfikację i kontrolę krzyżową na zapisanych odpowiedziach modelu (bez uruchamiania modelu); `tools/check_second_read.py` — zgodność niezależnych odczytów OCR.
- `eval/splits.json` — podział spraw przykładowych: `dev` (48 spraw, strojenie), `holdout` (12 spraw, zamrożone do pomiaru końcowego), `scandev` (10 spraw zamienionych na skany); `eval/gold-real/` — gold dla realnego skanu organizatora.
- `tools/check_classify.py` — macierz pomyłek klasyfikatora, `tools/bench_ocr.py` — czas i dokładność OCR, `tools/diff_pred.py` — różnice pole po polu.
- `tests/` — testy jednostkowe walidatorów, dopasowania do tekstu i kontroli krzyżowej (`python -m pytest tests`).

## Użyte komponenty zewnętrzne

| Komponent | Licencja | Zastosowanie |
|---|---|---|
| Qwen3.5-4B (GGUF, kwantyzacja unsloth) | Apache-2.0 | model językowy |
| llama.cpp / llama-cpp-python | MIT | uruchamianie modelu na CPU |
| RapidOCR + modele PP-OCR | Apache-2.0 | OCR |
| ONNX Runtime | MIT | silnik OCR |
| pypdfium2 (PDFium) | Apache-2.0 / BSD-3 | odczyt i render PDF |
| OpenCV, NumPy, Pillow, PyYAML | Apache-2.0 / BSD / MIT-CMU / MIT | przetwarzanie obrazu i konfiguracja |
