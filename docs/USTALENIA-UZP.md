# ODWOŁANIA2JSON. Ustalenia UZP i wybór modelu

**21 listopada 2026, czas polski.** Drużyna **NIe wiem, ale wygeneruje** wybrała **Synaps-PL Small 4B**, polski model językowy z rodziny Synaps opracowany przez Synaptivo. W konkursie używamy wydania S1. Zespół sprawdził Synaps przez testową usługę lokalną. Mateusz potwierdził, że konkursowa usługa API dla jury nie została jeszcze uruchomiona. Identyfikator w próbach zespołu to `synaps-pl-4b-s1`. Punkt odniesienia dla konkursu stanowi [README UZP w wersji 0b360a9 z godz. 19.36](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md).

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
| Czas | **150 PDF-ów w maksymalnie 45 minut** dla całego zbioru. Odpowiada to średnio 18 s na PDF. Organizator zapowiedział zmianę sposobu przeprowadzania oceny. Aktualna wersja nie określa modelu procesora ani wielkości RAM. |
| Punktacja | W preselekcji F1 ma wagę 100%. W finale jakość i elastyczność mają po 50%. UZP zachował zakres 1–20 pkt za model, 1–20 pkt za rozszerzalność i 1–10 pkt za dodatkowe funkcje. Szczegóły punktacji LLM są w opracowaniu. O godz. 19.27 organizator wycofał wcześniejszą tabelę progów i zapis o 20 pkt za wariant lokalny. O godz. 19.36 zapowiedział zmianę organizacji testów. |
| API i składniki | Aplikacja działa lokalnie bez GPU, model może działać przez firmowe API z kluczem dla jury. Obowiązują otwarte komponenty, w tym model językowy. OCR może działać lokalnie lub przez API. Przy OCR przez API organizator uwzględni parametry modelu OCR w ocenie. |
| Uruchomienie i pliki | Python 3.13+, `requirements.txt` i uruchomienie skryptem. Wynik zachowuje nazwę bazową PDF i podkatalog sprawy w `output/`. Dla dokumentu spoza klas organizator wymaga pustego JSON. |
| Materiały do oddania | Tytuł i link GitHub do działającego prototypu, w którym można wgrać PDF i odczytać wynik. Instrukcja HackTribe przewiduje zamknięcie zgłoszeń 22 listopada o 11.00 i dołączenie prezentacji PDF do 10 MB. |

Źródła wymagań to [README UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md), [historia zmiany punktacji i warunków testu](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/compare/a48d25b...0b360a9da4b482a6a280696df6714404e0953505) oraz [przewodnik HackNation](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4).

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

**Warunki dostawcy API do potwierdzenia.** Konkursowe API dla jury jest dopiero planowane. Publiczna strona polityki prywatności Synaptivo 21 listopada wyświetlała zapowiedź publikacji. Przed oddaniem potrzebny jest obowiązujący dokument obejmujący zakres i miejsce przetwarzania danych przez API oraz potwierdzenie lokalizacji serwerów w UE/EOG. Potrzebna jest również próba z adresem i kluczem przeznaczonymi dla jury. Ostatnie pomiary korzystały z testowego adresu lokalnego. Klucz przekazuje się jury poza repozytorium. [Polityka Synaptivo](https://synaptivo.eu/polityka-prywatnosci/) · [Warunki UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md)
