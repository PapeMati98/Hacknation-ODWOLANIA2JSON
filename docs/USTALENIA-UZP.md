# ODWOŁANIA2JSON. Ustalenia UZP i wybór modelu

**22 listopada 2026, czas polski.** Drużyna **NIe wiem, ale wygeneruje** wybrała **Synaps-PL Small 4B**, polski model językowy z rodziny Synaps opracowany przez Synaptivo. W konkursie używamy wydania S1. Publiczne API przeszło próbę z kluczem jury. Adres i identyfikator modelu zawiera [instrukcja uruchomienia](./INSTRUKCJA-JURY.md). Wcześniejsze próby lokalne używały aliasu `synaps-pl-4b-s1`. Bieżące wymagania określają [README UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/README.md) i [instrukcja VM](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/VM.md).

## Odpowiedzi UZP na Discordzie

| Godzina | Ustalenie | Wpływ na projekt |
|---|---|---|
| 11.23–11.28 | UZP omówił wywołanie otwartego modelu po API, także płatnym z kluczem dla oceniających. | Warunki dotyczące dostawcy doprecyzowała odpowiedź z godz. 15.17. |
| 11.26 | MateuszSz (UZP) opisał ocenę pojedynczych pól. Długi tekst, np. nazwa firmy, może otrzymać punkt od 80% podobieństwa. Prawidłowo puste pole jest pomijane w F1. | Porównujemy pola ze wzorcem. Dokładna funkcja podobieństwa i pełna lista pól z tolerancją pozostają otwarte. |
| 15.17 | MateuszSz doprecyzował warunki hostingu. Usługodawcą ma być firma z serwerami w UE/EOG, a jej polityka prywatności ma podawać zakres i miejsce przetwarzania. | Dla API Synapsa przygotować odpowiednią informację o dostawcy, lokalizacji przetwarzania i klucz do testów jury. [Wiadomość UZP](https://discord.com/channels/1430883737486229536/1572733135035174982/1573703993442439300) |
| 15.55 | MateuszSz potwierdził, że imiona i nazwiska w wyniku powinny być w mianowniku. | Stosować także do pełnomocników wskazanych w tekście w przypadku zależnym. Potwierdzają to komentarze w [schematach organizatora](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/0b360a9da4b482a6a280696df6714404e0953505/oczekiwane-json). |
| 16.23 | Dominik Olczak (UZP) wskazał konta GitHub `DominikOlczak`, `MateuSzSz-Sz` i `rkrol-dev`. | Po finalnym oddaniu projektu Mateusz przewiduje dostęp jury tylko do odczytu. |

W pytaniach uczestników z godz. 12.20 pozostały m.in. sposób dopasowywania wielu elementów listy, dokładna miara podobieństwa długich tekstów i dopuszczalność dodatkowych pól w wynikowym JSON. Projekt prowadzi je odpowiednio jako Q-006, Q-002 i Q-011.

Ta część obejmuje odpowiedzi utrwalone w projekcie do godz. 16.23. Dowód wskazania kont jury znajduje się w lokalnym archiwum projektu jako `docs/organizator/2026-11-21-uzp-konta-jury.png`. Późniejsze zmiany poniżej pochodzą z publicznego repozytorium organizatora. [Kanał zadania](https://discord.com/channels/1430883737486229536/1572733135035174982)

## Bieżące wymagania opublikowane w README

| Obszar | Co będzie oceniane |
|---|---|
| Czas | UZP przeznacza 45 minut na 150 PDF-ów. Dla VM wskazuje Ubuntu 24.04, 2 vCPU, 16 GB RAM, 64 GB dysku i brak GPU. Czas na maszynie zespołu i czas na rzeczywistej VM są odrębnymi pomiarami. |
| Punktacja | W preselekcji F1 ma wagę 100%. W finale jakość i elastyczność mają po 50%. UZP zachował zakres 1–20 pkt za model, 1–20 pkt za rozszerzalność i 1–10 pkt za dodatkowe funkcje. Szczegóły punktacji LLM są w opracowaniu. O godz. 19.27 organizator wycofał wcześniejszą tabelę progów i zapis o 20 pkt za wariant lokalny. O godz. 19.36 zapowiedział zmianę organizacji testów. |
| API i składniki | Aplikacja działa lokalnie bez GPU, model może działać przez firmowe API z kluczem dla jury. Obowiązują otwarte komponenty, w tym model językowy. OCR może działać lokalnie lub przez API. Przy OCR przez API organizator uwzględni parametry modelu OCR w ocenie. |
| Uruchomienie i pliki | Python 3.13+, `requirements.txt`. Na VM organizatora systemowy Python to 3.12, obraz projektu ma 3.13. Po 11.00 jury uruchamia komendę z `/opt/solution/RUN.md`, która czyta `/opt/solution/input` i zapisuje `/opt/solution/output`. Zespół wcześniej ustawia klucz w `/opt/solution/.env` oraz przygotowuje obraz i OCR. |
| Materiały do oddania | Tytuł i link GitHub do działającego prototypu, w którym można wgrać PDF i odczytać wynik. Instrukcja HackTribe przewiduje zamknięcie zgłoszeń 22 listopada o 11.00 i dołączenie prezentacji PDF do 10 MB. |

[Bieżące warunki UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/README.md) · [Instrukcja maszyny](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/VM.md) · [Przewodnik HackNation](https://hacknation.pl/przewodnik-uczestnika)

## Synaps w zgłoszeniu

W ukończonych próbach na tych samych 30 publicznych skanach UZP odnotowano następujące wyniki. Pomiary obejmują przetwarzanie PDF i zapis JSON. Identyfikatory odpowiadają folderom pomiarów zespołu.

| Przebieg | Czas 30 skanów | F1 UZP | F1 przy dokładnej zgodności |
|---|---:|---:|---:|
| `api-s1` | 4 min 15 s | 0,9886 | 0,9735 |
| `api-s1-ocr` | 5 min 44 s | 0,9902 | 0,9752 |
| `api-s1-v2` | 3 min 03 s | 0,9902 | 0,9752 |
| `api-s1-v3` | 2 min 37 s | 0,9853 | 0,9701 |
| `api-s1-v4` | 2 min 40 s | 0,9819 | 0,9667 |
| `api-s1-v5` | **3 min 03 s** | **0,9935** | **0,9769** |

W próbie `api-s1-v5` na 30 skanach uzyskano 306 trafień, 2 wyniki nadmiarowe i 2 pominięcia według miary UZP. Na 127 PDF-ach z warstwą tekstową z zestawu rozwojowego zespołu uzyskano F1 0,9986 w 2 min 20 s. Wcześniejszy `api-s1-v2` na 25 plikach z ośmiu publicznych spraw osiągnął F1 1,0000 w 23 s. Wynik na 150 nieujawnionych PDF-ach zależy od liczby stron, udziału skanów i warunków oceny.

**Otwarte wagi potwierdzone.** Publiczne wydanie `Synaptivo/Synaps-PL-Small-4B`, rewizja `67e30d0`, ma dwa pliki wag, kartę i licencję Apache 2.0. Metadane Hugging Face wskazują bazę `Qwen/Qwen3.5-4B`. Kartę, licencję i listę wag sprawdzono anonimowo. [Karta modelu wskazana przez Mateusza](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B) · [Pliki wydania 67e30d0](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B/tree/67e30d038b23acb894e877fb6533e25d82afc86a)

**Dostęp do API i stan polityki.** W publicznej próbie z 21 listopada na 30 skanach uzyskano F1 0,9935 w 164 s. 22 listopada serwer bez klucza zwrócił HTTP 401. Polityka dostawcy opisuje dane wysyłane z aplikacji oraz miejsce ich przetwarzania. Wersja w repo ma status projektu. Kontakt w sprawach API przyjmuje Mateusz Pietrzak, Prezes Zarządu Synaptivo. [Polityka API](./POLITYKA-PRYWATNOSCI-API-SYNAPS.md) · [Dokumentacja API](./API-SYNAPS.md)

**Nocna próba odporności.** Na 43 trudnych PDF-ach z zestawu zespołu wykorzystanego do poprawek uzyskano F1 0,974 (392 TP, 13 FP, 8 FN) dla `ed312e1`. Wszystkie 22 osobne orzeczenia KIO dostały `{}`. Na oddzielnym zbiorze 36 dokumentów z 12 odłożonych spraw wersja `ed312e1` uzyskała F1 0,9963 w 32 s (403 TP, 2 FP, 1 FN). Wcześniejszy pomiar tej samej próby na `1800d25` wyniósł F1 0,9938 w 31 s. [Zbiór zespołu](../eval/trudne)
