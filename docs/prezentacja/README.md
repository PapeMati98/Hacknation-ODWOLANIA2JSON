# ODWOŁANIA2JSON · prezentacja dla jury UZP

**Drużyna „Nie wiem, ale wygeneruję”** pokazuje, jak z potwierdzenia przelewu w PDF uzyskać sześć pól w JSON i jak dodać do aplikacji kolejną klasę dokumentów.

[Prezentacja PDF do HackTribe](../Odwolania2JSON-prezentacja.pdf) · [Edytowalny PowerPoint z notatkami do sześciu slajdów](./Odwolania2JSON.pptx) · [Uruchomienie dla jury](../INSTRUKCJA-JURY.md)

## Przygotowanie pokazu

1. Uruchom aplikację zgodnie z instrukcją jury. Wprowadź klucz przed udostępnieniem ekranu. Otwórz widok sprawy. W drugiej karcie przygotuj przykład protokołu zgodnie z opisem pod scenariuszem.
2. Pobierz trzy pliki poniżej. Wgraj do aplikacji wyłącznie PDF. Jeśli otwierasz prezentację na drugim komputerze, skopiuj tam również pliki demonstracyjne.

| Plik | Do czego służy |
|---|---|
| [przelew.pdf](./demo/przelew.pdf) | Dokument wejściowy z publicznej sprawy UZP nr 02. |
| [wzorzec-uzp.json](./demo/wzorzec-uzp.json) | Oczekiwane wartości opublikowane przez organizatora. |
| [wynik-synaps.json](./demo/wynik-synaps.json) | JSON pobrany z aplikacji we wcześniejszej próbie z rzeczywistym Synapsem przez lokalną usługę. Sześć pól zgodziło się ze wzorcem. ZIP zawierał ten sam JSON. Próba trwała 12,33 s. |

PDF i wzorzec pochodzą z wersji danych UZP `0b360a9`. Po otwarciu pliku JSON rozwiń obiekt `przelew_bankowy`. Dwa pola łatwe do odczytania z ekranu to `data_operacji` (`2026-08-23`) i `kwota` (`50.0`, czyli 50,00 zł). [Oryginalna sprawa UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/0b360a9da4b482a6a280696df6714404e0953505/dane/przyklad_02)

## Scenariusz na dwie minuty

| Czas | Co pokazać i powiedzieć |
|---|---|
| 0:00–0:15 · slajd 1 | „To przelew z publicznej sprawy UZP. Osoba sprawdzająca akta potrzebuje m.in. daty operacji, kwoty i numeru transakcji. Pokażemy, skąd wzięły się w JSON.” |
| 0:15–0:50 · slajd 2 i aplikacja | Wgraj `przelew.pdf` i uruchom ekstrakcję. Otwórz wynik. Wskaż 23 sierpnia i 50 zł, pobierz JSON i pokaż ślad odczytu jednego pola. Przy braku połączenia pokaż `wynik-synaps.json` i powiedz wprost, że pochodzi z wcześniejszej próby na tym samym dokumencie. |
| 0:50–1:15 · slajd 3 | „Na przydzielonej maszynie UZP przetworzyliśmy 30 publicznych skanów w 8 min 31 s. F1 wyniósł 0,9935. Na 36 dokumentach z 12 odłożonych spraw wersja ed312e1 uzyskała F1 0,9963 w 32 s. Wynik na ukrytym zbiorze ustali jury.” |
| 1:15–1:38 · slajd 4 i edytor YAML | W przygotowanym edytorze wskaż frazę „protokół przekazania” i oba pola w sekcji `output`. „Nową klasę dodajemy jednym plikiem YAML. W próbie z lokalnym modelem aplikacja poprawnie odczytała numer protokołu i datę.” |
| 1:38–1:55 · slajd 5 | Pokaż `RUN.md` i przykład UZP. „Na maszynie jury jeden przebieg czyta PDF-y z `input` i zwraca JSON w `output`. OCR działa lokalnie. Do ręcznego sprawdzenia mamy też interfejs z widokiem pól i pobieraniem ZIP.” |
| 1:55–2:00 · slajd 6 | „Pola odczytuje polski model z rodziny Synaps opracowany przez Synaptivo. Dziękujemy.” Zostaw slajd ze źródłami na czas pytań. |

## Czwarta klasa na czas pytań

W edytorze wybierz **+ Nowa klasa**. Wpisz nazwę `protokol_przekazania.yaml`, wklej zawartość [pokazowej definicji klasy](./demo/protokol_przekazania.yaml) i wybierz **Waliduj YAML**. Edytor pokaże pola `numer_protokolu` i `data_przekazania`. Walidacja wystarczy do prezentacji reguł na scenie.

Aby powtórzyć ekstrakcję, wybierz **Zapisz klasę YAML** w swojej kopii demonstracyjnej i wgraj [fikcyjny protokół przygotowany przez zespół](./demo/protokol-pokazowy.pdf). Na dokumencie widnieją numer **DEMO-042/2026** i data **21.11.2026**. Oczekiwane wartości obu pól w JSON to `DEMO-042/2026` i `2026-11-21`. W lokalnym powtórzeniu z Qwen3.5-4B oba pola zgodziły się z dokumentem. [Pobrany wynik próby protokołu](./demo/protokol-wynik-lokalny.json)

## Pytania jury

- **Ile trwają te same 30 skanów na maszynie jury?** Na oficjalnej VM UZP z 2 vCPU wersja `8889069` uzyskała F1 0,9935 w 8 min 31 s. Wcześniejszy pomiar na stacji zespołu przez publiczne API trwał 2 min 44 s, a z lokalną usługą modelu 3 min 03 s. Wszystkie czasy obejmują OCR i zapis JSON. [Warunki pomiarów](../USTALENIA-UZP.md)
- **Co oznacza limit 45 minut?** Tyle UZP przeznacza na przetworzenie 150 PDF-ów podczas oceny. Preselekcja zależy od F1 na nieujawnionych sprawach. W finale jakość i możliwość rozbudowy ważą po 50%. [Kryteria organizatora](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md#7-kryteria-oceny)
- **Jaki model pracuje w aplikacji?** Synaps-PL Small 4B to polski model z rodziny Synaps. Synaptivo dostroiło warstwy tekstowe Qwen3.5-4B do polskich zadań. Pełne wagi modelu wydano na licencji Apache 2.0. [Karta modelu i licencja](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B/tree/67e30d038b23acb894e877fb6533e25d82afc86a)
- **Gdzie są przetwarzane dane?** OCR odczytuje PDF i obrazy na miejscu. Do API trafiają tekst i definicje pól. Model działa w Polsce. Brama HTTPS odszyfrowuje żądania w sieci globalnej. Zakres danych i zasady działania usługi opisuje Synaptivo. [Polityka prywatności API Synapsa](https://synaptivo.eu/api/polityka-prywatnosci/)

## Grafiki użyte w slajdach

Znaki UZP i HackNation oraz dwa kadry z aplikacji są dostępne jako oddzielne pliki PNG. Interfejs zaprojektował zespół w Antigravity z Gemini. [Znak UZP](./grafiki/logo-uzp.png) · [Znak HackNation](./grafiki/logo-hacknation.png) · [Widok sprawy](./grafiki/widok-sprawy.png) · [Edytor YAML](./grafiki/edytor-yaml.png) · [Materiał KAS ze znakiem HackNation](https://www.gov.pl/web/ias-wroclaw/resort-finansow-partnerem-strategiczny-na-hacknation-w-bydgoszczy-z-kas-dwa-zadania-dla-uczestnikow)
