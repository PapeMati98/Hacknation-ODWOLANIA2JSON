# ODWOŁANIA2JSON. Uruchomienie dla jury UZP

**Drużyna „NIe wiem, ale wygeneruje”.** Aplikacja obsługuje elektroniczne PDF-y i skany. Do ekstrakcji używa Synaps-PL Small 4B, polskiego modelu językowego z rodziny Synaps opracowanego przez Synaptivo. **Stan na 21 listopada.** Konkursowe API przeszło próbę przez publiczny adres z kluczem jury. W próbie aplikacja obsłużyła 30 publicznych skanów UZP w 2 min 44 s. Do opisanej poniżej próby w Windows zainstaluj Python 3.13 z programem uruchamiającym `py`. Skrypt interfejsu wywołuje `py -3.13` przy tworzeniu środowiska. Potrzebujesz również połączenia z usługą modelu. Pierwsze uruchomienie pobiera zależności. [Publiczna karta modelu](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B)

## Dostęp do modelu

Adres API to `https://api.synaptivo.eu/v1`, a identyfikator modelu to `Synaptivo/Synaps-PL-Small-4B`. Klucz do testów zespół przekazuje jury w formularzu zgłoszeniowym. W PowerShell otwórz katalog zawierający `start_ui.bat` i `requirements.txt`, wykonaj poniższe polecenia i wpisz klucz w ukrytym polu. Ustawienia dotyczą bieżącej konsoli i uruchamianych z niej procesów.

```powershell
$env:O2J_API_BASE = 'https://api.synaptivo.eu/v1'
$env:O2J_API_MODEL = 'Synaptivo/Synaps-PL-Small-4B'
$env:O2J_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'Klucz jury' -AsSecureString)).Password
```

W konfiguracji konkursowej OCR działa na komputerze oceniającego. Pozostaw `O2J_OCR_BASE` nieustawione. Plik PDF i obrazy stron pozostają na tym komputerze. Do API Synapsa trafiają tekst oraz pola potrzebne do odczytu wartości. Przed oceną zespół przekaże adres obowiązującej polityki dostawcy. [Projekt polityki dla API Synaps](./POLITYKA-PRYWATNOSCI-API-SYNAPS.md)

## Pierwsza próba

1. Uruchom `.\start_ui.bat` z tej samej konsoli. Otwórz w przeglądarce `http://127.0.0.1:8080`. W informacji o modelu sprawdź tryb API i nazwę wskazaną przez zespół.
2. Pobierz [przelew.pdf](./prezentacja/demo/przelew.pdf) i [wzorzec UZP](./prezentacja/demo/wzorzec-uzp.json) ze sprawy nr 02. Wgraj PDF, uruchom ekstrakcję i porównaj wynik ze wzorcem. Data operacji to **2026-08-23**, a kwota **50,00 zł**. [Oryginalne pliki organizatora](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/0b360a9da4b482a6a280696df6714404e0953505/dane/przyklad_02)
3. Z widoku dokumentu pobierz JSON. Z widoku sprawy możesz również pobrać wyniki w ZIP.

## Przetwarzanie zbioru

Umieść PDF-y w podkatalogach spraw w `input`, np. `input/sprawa_02/przelew.pdf`. W tej samej konsoli możesz uruchomić tryb wsadowy. Skrypt przyjmie przekazane wcześniej ustawienia API i przygotuje środowisko Pythona, jeśli jest potrzebne.

```powershell
.\start.bat --input .\input --output .\output --trace .\trace
```

Wynik przykładu trafi do `output/sprawa_02/przelew.json`. Ślad ekstrakcji i pola do sprawdzenia znajdują się w `trace`. W razie komunikatu o przełączeniu na lokalny GGUF sprawdź adres, nazwę modelu i ważność klucza przed pomiarem czasu Synapsa. Na czas oceny całej partii UZP przeznacza 45 minut na 150 PDF-ów. [Zasady UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md)
