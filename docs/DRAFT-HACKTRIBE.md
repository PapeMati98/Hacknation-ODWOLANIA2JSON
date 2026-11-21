# Zgłoszenie Odwołania2JSON w HackTribe

**Stan na 21 listopada 2026.** Karta projektu dla zadania UZP jest zapisana i zawiera link do repozytorium. Po zakończeniu prac nad kodem zespół dołączy prezentację PDF i zapisze komplet zgłoszenia. Termin upływa w niedzielę 22 listopada o godz. 11.00 czasu polskiego. [Panel projektów](https://hacknation2026.hacktribe.co/my/) · [Instrukcja zgłaszania projektów, s. 5–7](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4)

| Pole formularza | Wartość |
|---|---|
| Nazwa projektu | Odwołania2JSON — ekstrakcja danych ze spraw KIO |
| Zadanie partnerskie | Odwołania2json — Urząd Zamówień Publicznych |
| Nazwa zespołu | NIe wiem, ale wygeneruje |
| Numer stolika | Lider wpisuje przydzielony numer z hali. |
| Link do prototypu | [PapeMati98/Hacknation-ODWOLANIA2JSON](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON) |

**Model wykorzystany w prototypie.** [Synaptivo/Synaps-PL-Small-4B na Hugging Face](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B) · [Rewizja wag i licencja Apache 2.0](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B/tree/67e30d038b23acb894e877fb6533e25d82afc86a)

### Krótki opis projektu

Zamieniamy dokumenty sprawy przed Krajową Izbą Odwoławczą w dane dla systemu UZP. Użytkownik wgrywa odwołanie, pełnomocnictwo lub potwierdzenie przelewu. Dla każdego rozpoznanego PDF otrzymuje osobny JSON oraz ślad odczytu. Aplikacja obsługuje dokumenty elektroniczne i skany.

### Przyjęte podejście

Z dokumentów elektronicznych pobieramy tekst, a skany odczytujemy za pomocą OCR. Plik YAML określa, jak rozpoznać klasę i jakich pól w niej szukać. Pola odczytuje Synaps-PL Small 4B, polski model językowy z rodziny Synaps. Synaptivo dostroiło go na polskich zadaniach i udostępnia jego wagi na licencji Apache 2.0. Aplikacja korzysta z działającego firmowego API Synaptivo. Jury otrzyma klucz w formularzu zgłoszeniowym. Aplikacja sprawdza odczytane pola względem treści dokumentu, porównuje dane pomiędzy pismami tej samej sprawy i oznacza rozbieżności. Użytkownik może przejrzeć źródło każdego pola i dodać klasę w edytorze YAML.

### Dotychczasowe postępy

Działają trzy klasy dokumentów UZP. W próbie zespołu `api-s1-v5` Synaps przetworzył 30 publicznych skanów UZP w 3 min 03 s. F1 wyniósł 0,9935, a przy dokładnej zgodności wartości 0,9769. W oddzielnej próbie przez publiczne API te same 30 skanów przetworzono w 2 min 44 s z F1 0,9935. Interfejs pozwala pobrać JSON dokumentu i ZIP sprawy. W osobnej próbie dodaliśmy czwartą klasę przez YAML i poprawnie odczytaliśmy numer oraz datę protokołu przekazania. Jury oceni rozwiązanie na 150 nieujawnionych PDF-ach, z limitem 45 minut.

### Przy zapisie projektu

Osoba zakładająca projekt staje się jego liderem. Przy dwóch zadaniach zespołowych drugi projekt zakłada inny uczestnik i dodaje ten sam skład. Dla startu jednoosobowego organizator przewidział odrębną procedurę. Potwierdzeniem zapisu jest karta projektu w panelu lidera z właściwym zadaniem i nazwą. [Instrukcja HackTribe](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4)

### Do niedzieli

Po zakończeniu prac lider sprawdza skład i zgodność opisu z oddawaną wersją prototypu, porównuje wynik końcowego pomiaru z prezentacją o Synapsie, dołącza PDF i zapisuje formularz. Następnie otwiera załącznik z karty projektu. Organizator zaleca demo do dwóch minut. [Prezentacja PDF dla jury](./Odwolania2JSON-prezentacja.pdf) · [Przewodnik uczestnika](https://hacknation.pl/przewodnik-uczestnika)
