# Zgłoszenie Odwołania2JSON w HackTribe

**Stan na 22 listopada 2026.** Karta projektu dla zadania UZP jest zapisana i zawiera link do repozytorium. Ostatnie potwierdzenie od Mateusza dotyczy karty i linku do repozytorium. Lider dołącza aktualny PDF i zapisuje komplet. Termin upływa w niedzielę 22 listopada o godz. 11.00 czasu polskiego. [Panel projektów](https://hacknation2026.hacktribe.co/my/) · [Instrukcja zgłaszania projektów, s. 5–7](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4)

| Pole formularza | Wartość |
|---|---|
| Nazwa projektu | JSON, ja tu tylko parsuję |
| Zadanie partnerskie | Odwołania2json — Urząd Zamówień Publicznych |
| Nazwa zespołu | Nie wiem, ale wygeneruję |
| Numer stolika | 5D |
| Lider i skład | Agnieszka Pruszek. Na karcie zadeklarowano 4 osoby. Przy drugim zadaniu zespołowym lider porównuje imienny skład obu kart. |
| Link do prototypu | [PapeMati98/Hacknation-ODWOLANIA2JSON](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON) |

**Model wykorzystany w prototypie.** [Synaptivo/Synaps-PL-Small-4B na Hugging Face](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B) · [Rewizja wag i licencja Apache 2.0](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B/tree/67e30d038b23acb894e877fb6533e25d82afc86a)

### Problem

W 2025 r. do Krajowej Izby Odwoławczej wniesiono 5 986 odwołań. W jednej sprawie dane stron, pełnomocników i wpłat mogą być rozproszone między kilkoma plikami PDF. Odczytanie i zapisanie ich w jednolitym formacie ułatwia rejestrację sprawy i sprawdzenie danych w piśmie źródłowym. [Sprawozdanie Prezesa UZP za 2025 r., s. 43 PDF](https://www.gov.pl/attachment/0757b70a-3436-4aeb-aee9-f798888eac6d#page=43)

### Krótki opis projektu

Zamieniamy dokumenty sprawy przed Krajową Izbą Odwoławczą w dane dla systemu UZP. Użytkownik wgrywa odwołanie, pełnomocnictwo lub potwierdzenie przelewu. Dla każdego rozpoznanego PDF otrzymuje osobny JSON oraz ślad odczytu. Aplikacja obsługuje dokumenty elektroniczne i skany.

### Przyjęte podejście

Z PDF pobieramy tekst lub rozpoznajemy go lokalnym OCR. Plik YAML określa reguły rozpoznawania dokumentu i pola wyniku. Odczytuje je Synaps-PL Small 4B, polski model z rodziny Synaps opracowany przez Synaptivo i udostępniony na licencji Apache 2.0. Aplikacja sprawdza wartości względem dokumentu i porównuje je między pismami sprawy. Oceniający może prześledzić odczyt i dodać klasę w edytorze YAML. W wariancie z API odczyt pól wykonuje usługa Synaptivo. Na przydzielonej i przygotowanej maszynie UZP jury uruchamia jedną komendę z pliku RUN.md.

### Dotychczasowe postępy

Rozpoznajemy odwołania, pełnomocnictwa i przelewy. Na 30 publicznych skanach UZP przez API uzyskaliśmy F1 0,9935 w 2 min 44 s. Na własnym zbiorze 43 trudnych dokumentów wykorzystanym do poprawek wersja `ed312e1` uzyskała F1 0,974. W oddzielnej próbie dokumentów spoza klas wszystkie 22 orzeczenia KIO otrzymały pusty JSON. Na 36 dokumentach z 12 odłożonych spraw kod ed312e1 uzyskał F1 0,9963 w 32 sekundy. W odrębnej próbie z lokalnym Qwenem po dodaniu czwartej klasy przez YAML poprawnie odczytaliśmy oba pola protokołu. Aplikacja udostępnia JSON dokumentu i ZIP sprawy.

### Instrukcja uruchomienia do pola 17

Na maszynie UZP umieśćcie pliki PDF w `/opt/solution/input/<sprawa>/`. W katalogu `/opt/solution` wykonajcie polecenie z sekcji „Polecenie dla jury” w pliku `RUN.md`. Dla każdego PDF wynikowy JSON znajdziecie w `/opt/solution/output/<sprawa>/`. [RUN.md](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON/blob/main/RUN.md)

### Przy zapisie projektu

Osoba zakładająca projekt staje się jego liderem. Przy dwóch zadaniach zespołowych drugi projekt zakłada inny uczestnik i dodaje ten sam skład. Dla startu jednoosobowego organizator przewidział odrębną procedurę. Potwierdzeniem zapisu jest karta projektu w panelu lidera z właściwym zadaniem i nazwą. [Instrukcja HackTribe](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4)

### Przed ostatecznym zapisem do 11.00

Lider sprawdza tytuł, wybrane zadanie UZP, nazwę drużyny, stolik, skład, opis, podejście, postęp i adres prototypu. Dołącza sześcioslajdowy PDF w polu prezentacji, zapisuje całość i ponownie otwiera kartę oraz załącznik. W opcjonalnym polu dodatkowych materiałów może podać link do scenariusza i przykładów. [PDF do formularza](./Odwolania2JSON-prezentacja.pdf) · [Pakiet prezentacyjny](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON/tree/main/docs/prezentacja)

**Próba na VM.** Zespół otrzymał dostęp do oficjalnej maszyny UZP. Do potwierdzenia pozostaje wykonanie pełnego polecenia jury na tej maszynie. Na przydzielonej maszynie zespół przygotowuje `/opt/solution/RUN.md`, obraz z zależnościami oraz konfigurację usługi z kluczem w `/opt/solution/.env`. Przed 11.00 sprawdza polecenie jury na publicznych dokumentach. W opisie i prezentacji podajemy nazwę usługi oraz sposób uruchomienia. [Polecenie dla jury](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON/blob/main/RUN.md) · [Instrukcja VM UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/VM.md) · [Formularz zapotrzebowania](https://forms.cloud.microsoft/e/HRFJjEcqMF)

**Przy oddaniu.** Trzy konta wskazane przez UZP otrzymały imienne zaproszenia do prywatnego repozytorium. GitHub potwierdził wysyłkę 22 listopada o 09.38 czasu polskiego. Dostęp danego konta aktywuje się po przyjęciu zaproszenia. W polu z materiałami dodatkowymi można wkleić publiczną dokumentację API i politykę z 22 listopada 2026 r. [Dokumentacja API](https://synaptivo.eu/api/) · [Polityka prywatności API Synapsa](https://synaptivo.eu/api/polityka-prywatnosci/)
