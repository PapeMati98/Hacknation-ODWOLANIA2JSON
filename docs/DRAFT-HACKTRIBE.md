# Zgłoszenie Odwołania2JSON w HackTribe

**Stan na 22 listopada 2026.** Karta projektu dla zadania UZP jest zapisana i zawiera link do repozytorium. Ostatnie potwierdzenie od Mateusza dotyczy karty i linku do repozytorium. Lider dołącza aktualny PDF i zapisuje komplet. Termin upływa w niedzielę 22 listopada o godz. 11.00 czasu polskiego. [Panel projektów](https://hacknation2026.hacktribe.co/my/) · [Instrukcja zgłaszania projektów, s. 5–7](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4)

| Pole formularza | Wartość |
|---|---|
| Nazwa projektu | Odwołania2JSON — ekstrakcja danych ze spraw KIO |
| Zadanie partnerskie | Odwołania2json — Urząd Zamówień Publicznych |
| Nazwa zespołu | NIe wiem, ale wygeneruje |
| Numer stolika | Lider wpisuje przydzielony numer z hali. |
| Lider i skład | Sprawdzić w panelu lidera. Przy dwóch zadaniach zespołowych drugi projekt zakłada inny lider, a do obu dodaje się ten sam skład. |
| Link do prototypu | [PapeMati98/Hacknation-ODWOLANIA2JSON](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON) |

**Model wykorzystany w prototypie.** [Synaptivo/Synaps-PL-Small-4B na Hugging Face](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B) · [Rewizja wag i licencja Apache 2.0](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B/tree/67e30d038b23acb894e877fb6533e25d82afc86a)

### Krótki opis projektu

Zamieniamy dokumenty sprawy przed Krajową Izbą Odwoławczą w dane dla systemu UZP. Użytkownik wgrywa odwołanie, pełnomocnictwo lub potwierdzenie przelewu. Dla każdego rozpoznanego PDF otrzymuje osobny JSON oraz ślad odczytu. Aplikacja obsługuje dokumenty elektroniczne i skany.

### Przyjęte podejście

Z PDF pobieramy tekst lub rozpoznajemy go lokalnym OCR. Plik YAML określa reguły rozpoznawania dokumentu i pola wyniku. Odczytuje je Synaps-PL Small 4B, polski model z rodziny Synaps opracowany przez Synaptivo i udostępniony na licencji Apache 2.0. Aplikacja sprawdza wartości względem dokumentu i porównuje je między pismami sprawy. Oceniający może prześledzić odczyt i dodać klasę w edytorze YAML. W wariancie z API odczyt pól wykonuje usługa Synaptivo. Na przydzielonej i przygotowanej maszynie UZP jury uruchamia jedną komendę z pliku RUN.md.

### Dotychczasowe postępy

Rozpoznajemy odwołania, pełnomocnictwa i przelewy. Na 30 publicznych skanach UZP przez API uzyskaliśmy F1 0,9935 w 2 min 44 s. Na własnym zbiorze 43 trudnych dokumentów wykorzystanym do poprawek wersja `ed312e1` uzyskała F1 0,974. W oddzielnej próbie dokumentów spoza klas wszystkie 22 orzeczenia KIO otrzymały pusty JSON. Wcześniejszy test na 36 odłożonych dokumentach dotyczył wersji 1800d25 (F1 0,9938). W odrębnej próbie z lokalnym Qwenem po dodaniu czwartej klasy przez YAML poprawnie odczytaliśmy oba pola protokołu. Aplikacja udostępnia JSON dokumentu i ZIP sprawy.

### Przy zapisie projektu

Osoba zakładająca projekt staje się jego liderem. Przy dwóch zadaniach zespołowych drugi projekt zakłada inny uczestnik i dodaje ten sam skład. Dla startu jednoosobowego organizator przewidział odrębną procedurę. Potwierdzeniem zapisu jest karta projektu w panelu lidera z właściwym zadaniem i nazwą. [Instrukcja HackTribe](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4)

### Przed ostatecznym zapisem do 11.00

Lider sprawdza tytuł, wybrane zadanie UZP, nazwę drużyny, stolik, skład, opis, podejście, postęp i adres prototypu. Dołącza sześcioslajdowy PDF w polu prezentacji, zapisuje całość i ponownie otwiera kartę oraz załącznik. W opcjonalnym polu dodatkowych materiałów może podać link do scenariusza i przykładów. [PDF do formularza](./Odwolania2JSON-prezentacja.pdf) · [Pakiet prezentacyjny](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON/tree/main/docs/prezentacja)

**Próba na VM.** Lider zamawia jedną VM na zespół przez oficjalny formularz UZP. Zgodnie z informacją Mateusza z niedzieli rano zgłoszenie zapotrzebowania jest jeszcze przed zespołem. Na przydzielonej maszynie zespół przygotowuje `/opt/solution/RUN.md`, obraz z zależnościami oraz konfigurację usługi z kluczem w `/opt/solution/.env`. Przed 11.00 sprawdza polecenie jury na publicznych dokumentach. W opisie i prezentacji podajemy nazwę usługi oraz sposób uruchomienia. [Polecenie dla jury](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON/blob/main/RUN.md) · [Instrukcja VM UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/VM.md) · [Formularz zapotrzebowania](https://forms.cloud.microsoft/e/HRFJjEcqMF)

**Do potwierdzenia przy oddaniu.** Ostateczny adres usługi i obowiązująca polityka powinny odpowiadać faktycznej trasie przetwarzania. W sprawdzonej konfiguracji model działa w Polsce, a Cloudflare Free nie gwarantuje miejsca odszyfrowania w UE/EOG. Jury potrzebuje również uzgodnionego odczytu prywatnego repozytorium. [Projekt polityki](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON/blob/main/docs/POLITYKA-PRYWATNOSCI-API-SYNAPS.md)
