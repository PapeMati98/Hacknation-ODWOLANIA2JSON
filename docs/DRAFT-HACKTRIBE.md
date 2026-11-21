# Zgłoszenie Odwołania2JSON w HackTribe

**Treść do wklejenia do HackTribe, 21 listopada 2026.** Zapis karty projektu w panelu lidera czeka na potwierdzenie. Projekt i wybór zadania trzeba zapisać przed godz. 20.00 w sobotę 21 listopada. Termin na uzupełnienie całości upływa o godz. 11.00 w niedzielę 22 listopada czasu polskiego. [Panel projektów](https://hacknation2026.hacktribe.co/my/) · [Instrukcja zgłaszania projektów, s. 5–7](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4)

| Pole formularza | Wartość |
|---|---|
| Nazwa projektu | Odwołania2JSON — ekstrakcja danych ze spraw KIO |
| Zadanie partnerskie | Odwołania2json — Urząd Zamówień Publicznych |
| Nazwa zespołu | Lider podaje faktyczną nazwę zespołu przy zapisie. |
| Numer stolika | Lider wpisuje przydzielony numer z hali. |
| Link do prototypu | [PapeMati98/Hacknation-ODWOLANIA2JSON](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON) |

### Krótki opis projektu

Zamieniamy dokumenty sprawy przed Krajową Izbą Odwoławczą w dane, które można wczytać do systemu UZP. Użytkownik wgrywa odwołanie, pełnomocnictwo lub potwierdzenie przelewu. Dla każdego rozpoznanego PDF otrzymuje osobny plik JSON oraz ślad odczytu. Aplikacja przetwarza dokumenty lokalnie na CPU i obsługuje również skany.

### Przyjęte podejście

Z PDF pobieramy tekst, a w przypadku skanów korzystamy z OCR i porównujemy odczyty. Plik YAML określa, jak rozpoznać klasę i jakich pól w niej szukać. Lokalny model Qwen3.5-4B odczytuje wartości, a aplikacja sprawdza je względem dokumentu, zestawia dane pomiędzy pismami tej samej sprawy i wskazuje rozbieżności do weryfikacji. Użytkownik może przejrzeć ślad odczytu każdego pola i dodać klasę w edytorze YAML.

### Dotychczasowe postępy

Działają trzy klasy dokumentów UZP. Na 30 publicznych skanach treningowych organizatora, po 10 z każdej klasy, uzyskaliśmy F1 0,9752. Przy wymaganiu dokładnej zgodności wartości F1 wyniósł 0,9580. Interfejs pozwala pobrać JSON dokumentu i ZIP całej sprawy. W osobnej próbie dodaliśmy czwartą klasę przez YAML i poprawnie odczytaliśmy dwa pola protokołu przekazania: jego numer i datę. Jury oceni prototyp na oddzielnym, ukrytym zbiorze spraw.

### Przy zapisie projektu

Osoba zakładająca projekt staje się jego liderem. Przy dwóch zadaniach zespołowych drugi projekt zakłada inny uczestnik i dodaje ten sam skład. Dla startu jednoosobowego organizator przewidział odrębną procedurę. Potwierdzeniem zapisu jest karta projektu w panelu lidera z właściwym zadaniem i nazwą. [Instrukcja HackTribe](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4)

### Do niedzieli

Lider uzupełnia skład, wkleja adres repozytorium z tabeli i dołącza prezentację. Po zapisaniu sprawdza, czy karta pokazuje właściwe zadanie i czy można otworzyć załącznik. Organizator zaleca demo do dwóch minut. [Prezentacja PDF](./Odwolania2JSON-prezentacja.pdf) · [Przewodnik uczestnika](https://hacknation.pl/przewodnik-uczestnika)
