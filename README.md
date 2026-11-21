# Odwołania2json

Rozwiązanie zadania **Odwołania2json** (Urząd Zamówień Publicznych, HackNation 2026): zamienia dokumenty PDF sprawy odwoławczej KIO — odwołanie, pełnomocnictwo, potwierdzenie przelewu — na pliki JSON zgodne ze schematem organizatora.

- Aplikacja działa lokalnie bez GPU. Wariant konkursowy odczytuje pola przy użyciu **Synaps-PL Small 4B**, polskiego modelu językowego z rodziny Synaps opracowanego przez Synaptivo. [Publiczny model i licencja Apache 2.0](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B)
- Drużyna **„NIe wiem, ale wygeneruje”** przetestowała cały proces z lokalną usługą Synapsa. Na 30 publicznych skanach UZP uzyskała F1 0,9935 w 3 min 03 s. Próba przez publiczne API z kluczem jury dała F1 0,9935 na 30 skanach w 2 min 44 s. [Instrukcja jury](./docs/INSTRUKCJA-JURY.md) · [Ustalenia UZP](./docs/USTALENIA-UZP.md)
- Obsługuje PDF-y z warstwą tekstową i **skany** (OCR).
- Typ dokumentu jest rozpoznawany **po treści**, nigdy po nazwie pliku. Dokument spoza obsługiwanych klas (np. ogłoszenie, wyrok KIO, SWZ) dostaje **pusty plik JSON** (`{}`).
- Nową klasę dokumentu dodaje się **jednym plikiem YAML, bez zmian w kodzie**.
- Każda wartość jest weryfikowana, także krzyżowo (dwa niezależne odczyty skanu, zgodność między dokumentami sprawy). Wartość niepewna trafia do wyniku jako `null`, a razem z proponowanym odczytem i powodem — na listę `do_sprawdzenia.json` dla człowieka. Zasada projektu: *lepiej przekazać pole do sprawdzenia, niż wpisać błędną wartość*.

## Uruchomienie

### Przykład dla jury

Z kluczem z formularza zgłoszeniowego ustaw adres publicznego API i nazwę modelu zgodnie z [instrukcją jury](./docs/INSTRUKCJA-JURY.md). W PowerShell uruchom `.\start_ui.bat` i otwórz `http://127.0.0.1:8080`. Wgraj plik `przelew.pdf` ze sprawy `przyklad_02`, uruchom ekstrakcję i pobierz `przelew.json`. Sześć pól można porównać z plikiem o tej samej nazwie u organizatora. Przycisk „Pobierz ZIP sprawy” pobiera wszystkie wyniki. [Przykład i wzorzec UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/0b360a9da4b482a6a280696df6714404e0953505/dane/przyklad_02) · [Prezentacja projektu (PDF)](./docs/Odwolania2JSON-prezentacja.pdf) · [Materiały do wystąpienia, PowerPoint i przykład do demo](./docs/prezentacja/README.md) · [Treść zgłoszenia HackTribe](./docs/DRAFT-HACKTRIBE.md)

### Wariant lokalny z Qwenem

W tym wariancie wymagania to Windows lub Linux, Python 3.13+, ok. 5 GB wolnego RAM (zmierzone zużycie: 4,6 GB), ok. 3,5 GB na dysku (model). GPU, internet (po pobraniu modelu) i klucz API nie są potrzebne.

```bat
start.bat
```

Skrypt przy pierwszym uruchomieniu tworzy środowisko `.venv` i instaluje zależności z `requirements.txt`. W wariancie lokalnym instaluje również `requirements-local.txt` i pobiera wagi modelu. Następnie przetwarza pliki z folderu `input`.

Ręcznie:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-local.txt
.venv/Scripts/python tools/download_models.py
.venv/Scripts/python -m odwolania2json
```

Docker (Linux / Windows / macOS):

```bash
docker compose up --build
```

Kontener `odwolania2json` czyta `./input`, zapisuje do `./output` i `./trace`, a model trzyma w `./models` (brakujący pobiera przy pierwszym starcie). Modele OCR są w obrazie.

### Interfejs webowy (prototyp — upload PDF + podgląd JSON/śladu/YAML)

Interfejs w przeglądarce działa pod adresem lokalnym, korzysta z dołączonych zasobów i obsługuje wywołania modelu zgodnie z wybranym trybem pracy. Domyślny port to `8080`.

```bat
start_ui.bat
```

lub ręcznie / w Dockerze:

```bash
.venv/Scripts/python -m odwolania2json.web --host 127.0.0.1 --port 8080
# opcjonalnie z czytelnikiem wizualnym domyślnie włączonym:
.venv/Scripts/python -m odwolania2json.web --host 127.0.0.1 --port 8080 --visual-reader on
# albo przez Docker Compose:
docker compose up --build web
```

Po uruchomieniu otwórz `http://127.0.0.1:8080`.

#### Mapa widoków, pól i przycisków UI

| Element / przycisk | Gdzie | Dokładne działanie |
|---|---|---|
| Zakładka **Sprawy i ekstrakcja** | Pasek główny | Główny widok roboczy: upload PDF, lista spraw z `input/`/`output/`, podgląd JSON, śladu ekstrakcji, listy `do_sprawdzenia.json` i punktacji klasyfikatora. |
| Zakładka **Klasy dokumentów (YAML)** | Pasek główny | Przegląd, walidacja i zapis plików w `configs/classes/*.yaml` bez restartu serwera i bez zmian w kodzie. |
| Globalny pasek błędu: **Ponów** / **Zamknij** | Pod nagłówkiem (gdy błąd sieci/API) | `Ponów` pojawia się tylko przy błędach z przypisaną akcją ponowienia (np. odczyt `/api/status`, listy spraw, statusu zadania albo uruchomienie z `input/`); błędy bez akcji ponowienia (np. nieudane anulowanie zadania) pokazują wyłącznie `Zamknij`. |
| Pasek zadania: **Anuluj** / **Ponów** / **Zamknij** | Nad obszarem roboczym | `Anuluj` ustawia flagę przerwania zadania po bieżącym dokumencie (`POST /api/jobs/<id>/cancel`, już zapisane JSON-y pozostają w `output/`); `Ponów` pojawia się przy błędzie zadania i powtarza ostatnie wywołanie z **bieżącymi** wartościami formularza (polityka OCR, czytelnik wizualny, wybrane pliki); `Zamknij` chowa baner po zakończeniu. |
| Strefa **Upuść pliki PDF sprawy lub wybierz z dysku** | Nowa sprawa | Wybór wielu plików `.pdf` (drag & drop lub okno systemowe). Pliki bez rozszerzenia `.pdf` są odrzucane po stronie UI, a backend dodatkowo weryfikuje nagłówek `%PDF-`, limit 25 MB/plik i max 25 plików/zgłoszenie. |
| Baner błędu uploadu: **Zamknij** | Nowa sprawa (przy błędzie pliku/wysyłki) | Chowa komunikat walidacji uploadu (np. odrzucony plik nie-PDF lub błąd `400`/`413`). |
| Przycisk **×** przy nazwie pliku | Lista wybranych plików | Usuwa pojedynczy plik z kolejki przed wysłaniem (nie usuwa nic z dysku). |
| Pole **Nazwa katalogu sprawy** | Nowa sprawa | Opcjonalna nazwa podfolderu w `input/` i `output/`. Puste pole generuje automatyczną nazwę `sprawa_RRRRMMDD_GGMMSS`. |
| Lista **Polityka sum kontrolnych OCR** | Nowa sprawa | Przekazuje `--ocr-checksum` do nowego uruchomienia lub `Przetwórz z input/`: `confidence` (domyślnie: zła suma przy wysokiej pewności OCR zostaje z ostrzeżeniem, inaczej `null`) lub `strict` (zła suma z OCR zawsze daje `null`). |
| Lista **Czytelnik wizualny skanów (mmproj)** | Nowa sprawa | Przekazuje `--visual-reader` (`off` domyślnie — szybszy OCR 2 z 3; `on` — dodatkowy odczyt obrazu linii przez `models/mmproj-F16.gguf`, maks. 12 wycinków/dokument, wyłącznie lokalny tryb CPU). Gdy brak pliku `mmproj`, opcja `włączony` jest zablokowana z czytelną informacją. |
| Przycisk **Uruchom ekstrakcję** | Nowa sprawa | Zapisuje wybrane PDF-y do `input/<sprawa>/`, uruchamia asynchroniczny potok (`POST /api/cases/run`, HTTP 202) i pokazuje pasek postępu z etapem, czasem trwania oraz szacowanym ETA. Po zakończeniu automatycznie otwiera sprawę na pierwszym sklasyfikowanym dokumencie. |
| Przycisk **Wyczyść** | Nowa sprawa | Czyści listę wybranych (niewysłanych jeszcze) plików PDF z formularza; nie kasuje plików na dysku. |
| Przycisk **Odśwież** | Sprawy w przestrzeni roboczej | Przeładowuje listę spraw z katalogów `input/`, `output/` i `trace/` (`GET /api/cases`), np. po zewnętrznym uruchomieniu CLI. |
| Pozycja na liście spraw | Sprawy w przestrzeni roboczej | Otwiera podgląd sprawy (`GET /api/cases/<sprawa>`). Pokazuje liczbę sklasyfikowanych JSON-ów, dokumentów spoza klas (`{}`) oraz liczbę uwag z `do_sprawdzenia.json`. |
| Przycisk **Przetwórz z input/** | Pasek podsumowania sprawy | Widoczny, gdy w `input/<sprawa>/` są pliki PDF. Uruchamia ponownie ekstrakcję na plikach z dysku z aktualnie wybraną w formularzu polityką OCR i ustawieniem czytelnika wizualnego. |
| Przycisk **Pobierz ZIP sprawy** | Pasek podsumowania sprawy | Pobiera archiwum `<sprawa>.zip` ze wszystkimi wygenerowanymi plikami `output/<sprawa>/*.json` — łącznie z pustymi plikami `{}` dla dokumentów spoza klas (`GET /api/cases/<sprawa>/download.zip`). |
| Pigułki dokumentów (nad podziałem ekranu) | Inspektor sprawy | Przełączają aktywny dokument sprawy (obsługa myszy i klawiszy `←`/`→`). Dokument rozpoznany pokazuje nazwę klasy (`odwolanie`, `pelnomocnictwo`, `przelew`), a dokument obcy znacznik `spoza klas → {}`. |
| Przyciski **Kopiuj JSON** i **Pobierz .json** | Lewy panel (JSON) | `Kopiuj JSON` kopiuje sformatowaną treść JSON (`indent=2`) do schowka, a `Pobierz .json` pobiera dokładny plik z `output/<sprawa>/<plik>.json` (oba działają także dla dokumentu spoza klas z pustym obiektem `{}`). |
| Podzakładka **Ślad ekstrakcji** + filtry **Wszystkie / Ostrzeżenia / Odrzucone / OK** | Prawy panel | Tabela pole po polu z `trace/<sprawa>/<plik>.trace.json`: ścieżka pola, wartość końcowa + uwaga walidatora, źródło (`tekst` / `OCR` + wskaźnik pewności i werdykt czytelnika wizualnego) oraz status. Filtry zawężają wiersze bez przeładowania. |
| Podzakładka **Do sprawdzenia** | Prawy panel | Prezentuje listę z `trace/<sprawa>/do_sprawdzenia.json` dla całej sprawy: pola odrzucone (z proponowaną wartością i powodem), ostrzeżenia OCR oraz rozbieżności kontroli krzyżowej między dokumentami. |
| Podzakładka **Klasyfikacja** | Prawy panel | Tabela wyniku klasyfikatora (suma punktów ze słów kluczowych, dopasowań tytułu i wag ujemnych `negative`) dla każdej klasy YAML wobec progu `min_score` oraz werdykt (`wybrana`, `poniżej progu`, `inna klasa`). Otwiera się automatycznie po kliknięciu dokumentu spoza klas (`{}`). |
| Lista klas po lewej + **+ Nowa klasa** | Zakładka YAML | Kliknięcie klasy ładuje jej plik z `configs/classes/` do edytora z podglądem sekcji, pól i reguł YAML. `+ Nowa klasa` wstawia gotowy szablon `decyzja.yaml`. |
| Pole **Nazwa pliku w configs/classes/** | Zakładka YAML | Nazwa docelowego pliku YAML (np. `decyzja.yaml`). Każda edycja tego pola automatycznie wygasza ewentualny stan konfliktu `409` i ukrywa przycisk `Ponów z nadpisaniem`. |
| Pole **Definicja klasy YAML** | Zakładka YAML | Edytor treści YAML klasy dokumentu; każda edycja resetuje blokadę po błędzie walidacji i ukrywa baner sukcesu poprzedniego zapisu. |
| Przycisk **Waliduj YAML** | Zakładka YAML | Wysyła treść edytora do `POST /api/classes/validate` (walidator `parse_class_yaml` zgodny ze schematem `DocClass` i `DocClass.sections()`) bez zapisu na dysk; pokazuje podsumowanie sekcji, liczby pól i użytych reguł lub dokładny błąd składni. |
| Przycisk **Zapisz klasę YAML**, **Ponów z nadpisaniem** i **Zamknij** (alert YAML) | Zakładka YAML | Zapisuje atomowo plik do `configs/classes/<nazwa>.yaml` (`POST /api/classes`). Klasa działa natychmiast bez restartu serwera. Jeśli plik już istnieje (lub jest klasą wbudowaną), serwer zwraca `409 Conflict` i wymaga zmiany nazwy albo jawnego kliknięcia `Ponów z nadpisaniem`; `Zamknij` chowa baner błędu/konfliktu. |

### Wejście i wyjście

```
input/                          output/
├── case1/                      ├── case1/
│   ├── odwolanie_nr_1.pdf      │   ├── odwolanie_nr_1.json
│   ├── pelnomocnictwo_nr_1.pdf │   ├── pelnomocnictwo_nr_1.json
│   └── przelew_nr_1.pdf        │   └── przelew_nr_1.json
```

Plik JSON ma tę samą nazwę co PDF i leży w podfolderze tej samej sprawy. Dla dokumentu, który nie należy do żadnej klasy, powstaje plik z pustym obiektem `{}`. Obok powstaje folder `trace/`:

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
| `--ocr-checksum` / `O2J_OCR_CHECKSUM` | numer ze skanu ze złą sumą kontrolną: `confidence` = zostaje z ostrzeżeniem przy wysokiej pewności odczytu, inaczej `null`; `strict` = zawsze `null` | `confidence` |
| `--resume` | pomija dokumenty, które mają już wynik w `output` — wznowienie przerwanego przebiegu | wyłączone |
| `--visual-reader` / `O2J_VISUAL_READER`, `--mmproj` | czytelnik wizualny: drugi odczyt wycinków linii skanu tym samym modelem z projektorem obrazu (`python tools/download_models.py --vision`, 672 MB) | `off` |
| `O2J_API_BASE`, `O2J_API_MODEL`, `O2J_API_KEY` | adres, identyfikator i klucz do usługi Synaps w wariancie konkursowym | wartości przekazywane do oceny osobno |

### Czas działania i przerwany przebieg
W próbie `api-s1-v5` proces z Synapsem na 30 skanach zajął 183 s. W starszym trybie lokalnym z Qwenem na 12-rdzeniowym CPU sprawa (odwołanie + pełnomocnictwo + przelew) zajmuje około 2 minut dla PDF-ów tekstowych; skan dodaje około minuty na OCR dokumentu. Program wypisuje postęp i szacowany pozostały czas. Wynik każdego dokumentu jest zapisywany od razu po jego przetworzeniu, więc przerwanie nie niszczy gotowych plików, a `--resume` kończy przebieg od miejsca przerwania.

### Tryb lokalny a API
W wariancie konkursowym aplikacja korzysta z otwartych wag Synaps-PL Small 4B przez API. Przetestowany identyfikator lokalnego serwera modelu to `synaps-pl-4b-s1`. Wersja jury korzysta z `https://api.synaptivo.eu/v1` i identyfikatora `Synaptivo/Synaps-PL-Small-4B`. Bez skonfigurowanego API aplikacja może korzystać z lokalnego Qwena GGUF. [Pomiar wariantu Synaps](./docs/USTALENIA-UZP.md)

## Użyty model językowy

| | |
|---|---|
| Model konkursowy | [Synaps-PL Small 4B](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B), rodzina Synaps, Synaptivo. Wydanie S1 powstało przez dostrojenie Qwen3.5-4B na polskich zadaniach. Licencja Apache 2.0. |
| Postać | publiczne wagi Synaps w dwóch plikach safetensors, rewizja `67e30d0` |
| Wykonanie | Aplikacja lokalna i lokalny OCR. Ekstrakcja przez publiczne API Synapsa sprawdzone z kluczem jury. |
| Ustawienia | temperatura 0 (wynik powtarzalny), tryb rozumowania wyłączony |
| Wariant lokalny z Qwenem | Q4_K_M GGUF, 2,7 GB na dysku. Zmierzono 4,6 GB pamięci z OCR dla tego wariantu. |

Model ma wąską rolę: czyta tekst dokumentu i wpisuje wartości do formularza `klucz: wartość`. Nie rozpoznaje typu dokumentu, nie buduje JSON-a i nie liczy pól słownikowych — to robi kod na podstawie YAML. Każdą wartość z modelu sprawdza kod (sumy kontrolne, obecność w dokumencie, miejsce w dokumencie, drugi odczyt skanu); wartość, która nie przechodzi kontroli, nie trafia do wyniku. Dzięki temu wystarcza mały model, a wymiana na inny plik GGUF to jeden parametr (`--model`).

## Architektura

```
PDF ──► pdfio ──► classify ──► extract (LLM) ──► walidacja pól ──► kontrola krzyżowa ──► JSON
         │           │              │                 │                   │              + trace
   tekst lub OCR   klasy YAML   formularz z YAML   validators        crosscheck         + do_sprawdzenia
   (dwa odczyty)                                  + textmatch    + cross_checks.yaml
```

| Moduł | Rola |
|---|---|
| `odwolania2json/pdfio.py` | Warstwa tekstowa PDF; gdy jej brak — OCR na CPU (RapidOCR, modele PP-OCR przez ONNX Runtime). Każda strona skanu jest czytana dwa razy w różnej rozdzielczości: linie o niskiej pewności są zastępowane lepszym odczytem albo dostają znacznik `[NIECZYTELNE]`, a drugi odczyt służy do kontroli krzyżowej wartości. Z ramek linii odtwarzany jest układ strony, a czarne prostokąty anonimizacji dostają znacznik `[ZAKRYTE]` (patrz „Układ strony skanu”). |
| `odwolania2json/vision.py` | Opcjonalny czytelnik wizualny: drugi, niezależny odczyt wycinka linii; tylko potwierdza albo wetuje wartość z OCR. |
| `odwolania2json/config.py` | Wczytuje klasy dokumentów z YAML; buduje z nich formularz i opis pól dla modelu. |
| `odwolania2json/extract.py` | Klasyfikacja (słowa kluczowe i tytuł z YAML, próg odrzucenia) oraz ekstrakcja: model wypełnia zwięzły formularz `klucz: wartość`, kod zamienia go na JSON i weryfikuje każde pole. |
| `odwolania2json/llm.py` | Ekstrakcja przez API Synapsa i obsługa lokalnego wariantu z Qwenem GGUF. |
| `odwolania2json/validators.py` | Sumy kontrolne NIP / REGON / PESEL / NRB, format KRS, daty, numery BZP i TED, kwoty, e-mail, nazwiska bez tytułów; naprawa typowych pomyłek OCR o jeden znak. |
| `odwolania2json/textmatch.py` | Sprawdza, czy wartość faktycznie występuje w dokumencie; zastępuje niedokładnie przepisaną wartość dosłownym fragmentem tekstu, dociąga niepełne numery, porównuje dwa odczyty OCR. |
| `odwolania2json/crosscheck.py` | Kontrola krzyżowa: ten sam numer w kilku polach, zgodność między dokumentami sprawy, lista pozycji do sprawdzenia. |
| `odwolania2json/cli.py` | Przetwarzanie folderu `input`; dokumenty są grupowane klasami, żeby model czytał stałą część promptu tylko raz na klasę. |

### Dlaczego formularz, a nie JSON prosto z modelu
Na CPU czas zależy głównie od liczby generowanych tokenów. Formularz `klucz: wartość` jest około dwa razy krótszy niż JSON z tymi samymi danymi, a strukturę JSON (zagnieżdżenia, typy, pola wyliczane ze słowników) deterministycznie odtwarza kod.

Model lokalny wypełnia formularz w sposób prowadzony: klucze podaje mu kod (szybkie przetwarzanie wsadowe), a model generuje wyłącznie wartości. Stan modelu po przeczytaniu instrukcji i opisu pól danej klasy jest zapamiętywany, więc dla kolejnych dokumentów tej klasy czytany jest już tylko tekst dokumentu. Lista podmiotów kończy się, gdy model przestaje podawać nowe — powtórzenie już wpisanego podmiotu jest odrzucane.

### Układ strony skanu
OCR zwraca linie w kolejności, która przy układzie dwukolumnowym (etykieta „Odwołujący:” na marginesie, dane obok) miesza strony postępowania. Dlatego tekst skanu jest składany z ramek linii:

- linie o tym samym położeniu w pionie tworzą wiersz (od lewej do prawej), wiersze bez większego odstępu — blok;
- etykieta stojąca na marginesie obok bloku trafia na jego początek;
- **czarne prostokąty anonimizacji** są wykrywane w obrazie (spójny, wypełniony obszar ciemnych pikseli) i wstawiane do tekstu jako `[ZAKRYTE]`. Wartość zawierająca znacznik albo występująca wyłącznie tuż obok niego (ocalały fragment zakrytej całości, np. „Kancelaria Prawna [ZAKRYTE]”) daje `null`;
- strona jest renderowana jak kartka A4 — skan zapisany w małej rozdzielczości nie jest sztucznie powiększany; linia nadal nieczytelna jest czytana ponownie z wycinka w kilku powiększeniach;
- **skan przekrzywiony** (kartka położona krzywo, 0,7–1,5° w skanach organizatora) jest prostowany rachunkowo: kąt wynika z ramek długich linii, a wiersze i bloki układane są we współrzędnych wyprostowanych. Bez tego długie linie zachodzą w pionie na sąsiednie i punkty wyliczenia mieszają się ze sobą;
- typowe pomyłki OCR są poprawiane w tekście: „sp. z 0.o.” → „sp. z o.o.”, litera wewnątrz ciągu cyfr („9994328o29”) → cyfra. Imię, nazwisko i krótka nazwa, które OCR odczytał w dokumencie raz z polskim znakiem, raz bez („Łukasz” / „Lukasz”), dostają zapis przeważający we wszystkich odczytach.

### Kontrola krzyżowa
Sprawdzenie pojedynczego pola nie wystarcza: KRS, daty, kwoty i numery ogłoszeń nie mają sumy kontrolnej, a poprawny numer może trafić do niewłaściwego podmiotu. Dlatego wynik przechodzi dodatkowe kontrole:

1. **Niezależne odczyty skanu.** Każda strona skanu jest czytana w dwóch rozdzielczościach, a przy wątpliwości w trzeciej. Wartość bez sumy kontrolnej (KRS, data, kwota, numer BZP/TED, sygnatura, numer transakcji) musi powtórzyć się w innym odczycie. Inny odczyt daje inną wartość → `null`. Inny odczyt w ogóle nie zawiera tej linii → wartość zostaje z ostrzeżeniem. Poprawka numeru o jeden znak na podstawie sumy kontrolnej jest przyjmowana tylko wtedy, gdy poprawiony numer widać w innym odczycie.
   **Wskaźnik pewności** każdej wartości ze skanu łączy pewność linii podawaną przez OCR z werdyktem innych odczytów: *wysoka* — linia pewna (≥ 0,95) i inny odczyt daje to samo; *średnia* — brak sprzeczności, ale linia mniej pewna albo inny odczyt jej nie zawiera; *niska* — inny odczyt daje inną wartość. Niska → `null`; średnia → wartość zostaje z ostrzeżeniem. Numer ze złą sumą kontrolną zostaje (z ostrzeżeniem) tylko przy pewności wysokiej. Wskaźnik jest zapisany w śladzie i na liście do sprawdzenia.
2. **Wartość musi być w dokumencie.** Dotyczy każdego pola, także dat, kwot i numerów ogłoszeń: model nie może podać wartości, której w tekście nie ma (np. przepisanej z instrukcji).
3. **Kontrola przypisania.** Ten sam NIP / KRS / REGON / rachunek nie może trafić do kilku pól. Numer zostaje przy tym podmiocie, przy którego nazwie leży w dokumencie; gdy nie da się tego ustalić — znika ze wszystkich pól.
4. **Zależności między polami** (w YAML klasy): `requires` — pole ma sens tylko razem z innym (miejscowość z nagłówka tylko z datą; dane pełnomocnika tylko wtedy, gdy strona działa przez pełnomocnika — `requires: "../przez-pelnomocnika=1"`); `not_in` — wartość nie może powtarzać się na innej liście (podpisujący pełnomocnictwo nie może być pełnomocnikiem); `line_pattern` — linia, w której stoi wartość, musi mieć określoną postać (data odwołania stoi w osobnej linii nagłówka, sama albo po miejscowości; data ze zdania w treści nią nie jest). Na 71 przykładowych odwołaniach (tekst i skany) reguła przepuszcza wszystkie 55 dat nagłówka i żadnej innej daty.
   `decide` — gdy dokument nazywa rzecz wprost we wskazanym zdaniu, rozstrzyga to zdanie, a nie model. W odwołaniu: pierwszy punkt wyliczenia „wnoszę odwołanie wobec: 1. …” wyznacza rodzaj zaskarżonej czynności (pozycję słownika) i jej dzień — zgodnie z zasadą organizatora, że liczy się wyłącznie pierwszy zarzut. Reguła rozstrzyga tylko wtedy, gdy zdanie pasuje do dokładnie jednej pozycji (albo zawiera dokładnie jedną datę); inaczej zostaje odpowiedź modelu. Bez modelu reguły dają na 10 skanach organizatora 10/10 dla rodzaju i 10/10 dla dnia, a na 48 sprawach tekstowych 44 trafne rozstrzygnięcia rodzaju, 0 błędnych i 4 pozostawione modelowi.
   `reject` — wartość nie może mieć postaci, której to pole mieć nie może: etykieta rubryki bankowej („Szczegóły płatności”, „Dane odbiorcy”) nie jest tytułem przelewu, zdanie nie jest numerem transakcji, tekst z cyframi albo ze słowem „kancelaria”, „prezes”, „sp.” nie jest imieniem i nazwiskiem. Wartość pasująca w całości do wzorca → `null`. Reguły nie odrzucają żadnej z 357 wartości wzorcowych organizatora.
   `cut` — wartość kończy się przed wskazanym dopiskiem (nazwa mocodawcy bez „z siedzibą w …”, adresu i numerów rejestrowych).
   `lists.<lista>.count` (na poziomie klasy) — liczba elementów listy wynikająca wprost z tekstu. W pełnomocnictwie konsorcjum mocodawców jest tylu, ile punktów „1) …, 2) …” przed zdaniem udzielającym pełnomocnictwa; model jest prowadzony do kolejnego mocodawcy, a rozbieżność między wyliczeniem a wynikiem trafia na listę do sprawdzenia. Na 58 przykładowych pełnomocnictwach reguła podaje liczbę zgodną ze wzorcem w 58 przypadkach.
5. **Zgodność między dokumentami sprawy** (`configs/cross_checks.yaml`): Odwołujący z odwołania ↔ mocodawca z pełnomocnictwa (KRS, NIP, nazwa), pełnomocnik z odwołania ↔ pełnomocnicy z pełnomocnictwa, kolejność dat. Rozbieżność jest zgłaszana, ale nie zmienia JSON-ów — nie wiadomo, który dokument ma rację. Na 60 przykładowych sprawach organizatora reguły nie dają ani jednego fałszywego alarmu.

Reguły między dokumentami dopisuje się w YAML, bez zmian w kodzie (rodzaje: `same`, `not_after`, `one_of`).

**Czytelnik wizualny (opcja `--visual-reader on`).** Ten sam model z projektorem obrazu czyta wycinek pojedynczej linii skanu jako drugi, niezależny czytelnik. Nigdy nie jest autorem wartości: odczyt zgodny podnosi wskaźnik pewności o jeden stopień, odczyt z inną wartością zeruje pole, odczyt pusty lub niezwiązany z linią niczego nie zmienia. Pytany jest tylko o pola, których pewność nie jest wysoka (najwyżej 12 wycinków na dokument), nigdy o linię z czarnym prostokątem. Numer potwierdza wyłącznie cały fragment cyfr — nie część dłuższego numeru. Przy numerze ze złą sumą kontrolną czytelnik niczego nie zmienia (może tylko dopisać uwagę do listy do sprawdzenia).

### Weryfikacja wartości
Dla każdego pola w `trace/<sprawa>/<plik>.trace.json` zapisywane są: wartość surowa z modelu, wartość końcowa, źródło (`warstwa_tekstowa` / `ocr`) oraz status:

| Status | Znaczenie |
|---|---|
| `ok` | wartość przeszła walidację |
| `naprawiono` | błąd OCR jednego znaku poprawiony na podstawie sumy kontrolnej |
| `dopasowano` | wartość modelu zastąpiona dosłownym fragmentem dokumentu (ucięte słowo, zmieniona końcówka, niepełny numer) |
| `ostrzezenie` | wartość zachowana, ale trafia na listę do sprawdzenia: zła suma kontrolna przy odczycie dokładnym (warstwa tekstowa) albo przy wysokiej pewności odczytu ze skanu; średnia pewność odczytu ze skanu |
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
Opcje pola: `verify_in_text`, `enum`, `enum_from`, `derive`, `only_if_multiple` (pole wypełniane tylko, gdy lista ma kilka elementów), `requires`, `not_in`, `line_pattern` (wyrażenie regularne lub lista wyrażeń z miejscem `{value}` — postać linii, w której musi stać wartość), `decide` (`scope` — w których zdaniach szukać; dla pola słownikowego dodatkowo `patterns` — wyrażenie dla każdej pozycji słownika: gdy pasuje dokładnie jedna, rozstrzyga ona zamiast modelu; dla daty wystarczy `scope`: rozstrzyga jedyna data we wskazanym zdaniu), `known_values` (lista znanych zapisów — wartość różniąca się tylko polskimi znakami jest zamieniana na zapis z listy), `output_type: integer`. `requires` przyjmuje nazwę pola obok albo ścieżkę poziom wyżej z wymaganą wartością (`"../pole=1"`). `reject` (lista wyrażeń: wartość pasująca w całości jest odrzucana), `cut` (lista wyrażeń: wartość jest ucinana przed dopasowaniem), `check` (opis, czym wartość ma być — pytanie do końcowej oceny modelem, patrz niżej). Reguły list wpisuje się w sekcji `lists` klasy: `count` ze `scope` (fragment dokumentu) i `item` (numer punktu wyliczenia).
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
| [Synaps-PL Small 4B](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B) | Apache-2.0 | polski model z rodziny Synaps opracowany przez Synaptivo na bazie Qwen3.5-4B, ekstrakcja konkursowa |
| Qwen3.5-4B (GGUF, kwantyzacja unsloth) | Apache-2.0 | alternatywny wariant lokalny; opcjonalnie jego projektor obrazu `mmproj-F16.gguf` (czytelnik wizualny) |
| llama.cpp / llama-cpp-python | MIT | uruchamianie modelu na CPU |
| RapidOCR + modele PP-OCR | Apache-2.0 | OCR |
| ONNX Runtime | MIT | silnik OCR |
| pypdfium2 (PDFium) | Apache-2.0 / BSD-3 | odczyt i render PDF |
| OpenCV, NumPy, Pillow, PyYAML | Apache-2.0 / BSD / MIT-CMU / MIT | przetwarzanie obrazu i konfiguracja |
| Znak graficzny UZP (`odwolania2json/web_assets/uzp-logo.png`) | Identyfikacja wizualna UZP (`gov.pl/web/uzp`) | wyłącznie lokalny nagłówek prototypu Web UI dla zadania UZP na HackNation 2026 (wymienny jednym plikiem, brak połączeń zewnętrznych) |
