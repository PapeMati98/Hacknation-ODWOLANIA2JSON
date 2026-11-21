# ODWOŁANIA2JSON. Uruchomienie dla jury UZP

**Drużyna „NIe wiem, ale wygeneruje”.** Aplikacja obsługuje elektroniczne PDF-y i skany. Do ekstrakcji używa Synaps-PL Small 4B, polskiego modelu językowego z rodziny Synaps opracowanego przez Synaptivo. **Stan na 21 listopada.** Działa lokalna usługa testowa. Zewnętrzny dostęp jury będzie możliwy po uruchomieniu konkursowego API i przekazaniu danych dostępowych. Komputer osoby oceniającej potrzebuje systemu Windows, Pythona 3.13 lub nowszego i dostępu do usługi modelu. Pierwsze uruchomienie pobiera zależności. [Publiczna karta modelu](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B)

## Dostęp do modelu

Po uruchomieniu usługi zespół przekaże jury osobnym kanałem adres firmowej usługi, identyfikator obsługiwanego modelu i klucz do testów. W PowerShell, w katalogu zawierającym `start_ui.bat` i `requirements.txt`, ustaw przekazane wartości. Pole klucza ukrywa wpisywane znaki. Ustawienia dotyczą bieżącej konsoli i uruchamianych z niej procesów.

```powershell
$env:O2J_API_BASE = Read-Host 'Adres usługi LLM przekazany przez zespół, łącznie z /v1'
$env:O2J_API_MODEL = Read-Host 'Identyfikator modelu podany przez zespół'
$env:O2J_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'Klucz jury' -AsSecureString)).Password
```

Jeżeli zespół przekazał osobny adres OCR, ustaw również `O2J_OCR_BASE` i ewentualny osobny `O2J_OCR_KEY`. Bez adresu usługi OCR skany są odczytywane lokalnie. Tryb zdalnego OCR wysyła do tej usługi dokument PDF i numery stron do odczytu.

## Pierwsza próba

1. Uruchom `.\start_ui.bat` z tej samej konsoli. Otwórz w przeglądarce `http://127.0.0.1:8080`. W informacji o modelu sprawdź tryb API i nazwę wskazaną przez zespół.
2. Z przykładowej sprawy organizatora pobierz `przelew.pdf` oraz wzorzec `przelew.json`. Wgraj PDF, otwórz wynik i porównaj pola ze wzorcem. W tym przykładzie data operacji to **2026-08-23**, a kwota **50,00 zł**. [Sprawa UZP nr 02](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/0b360a9da4b482a6a280696df6714404e0953505/dane/przyklad_02)
3. Z widoku dokumentu pobierz JSON. Z widoku sprawy możesz również pobrać wyniki w ZIP.

## Przetwarzanie zbioru

Umieść PDF-y w podkatalogach spraw w `input`, np. `input/sprawa_02/przelew.pdf`. W tej samej konsoli możesz uruchomić tryb wsadowy. Skrypt przyjmie przekazane wcześniej ustawienia API i przygotuje środowisko Pythona, jeśli jest potrzebne.

```powershell
.\start.bat --input .\input --output .\output --trace .\trace
```

Wynik przykładu trafi do `output/sprawa_02/przelew.json`. Ślad ekstrakcji i pola do sprawdzenia znajdują się w `trace`. W razie komunikatu o przełączeniu na lokalny GGUF sprawdź adres, nazwę modelu i ważność klucza przed pomiarem czasu Synapsa. Na czas oceny całej partii UZP przeznacza 45 minut na 150 PDF-ów. [Zasady UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md)
