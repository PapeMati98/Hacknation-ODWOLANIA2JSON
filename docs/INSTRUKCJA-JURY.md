# ODWOŁANIA2JSON. Uruchomienie dla jury UZP

**Drużyna „Nie wiem, ale wygeneruję”.** Aplikacja odczytuje PDF-y tekstowe i skany. Korzysta z Synaps-PL Small 4B, polskiego modelu językowego z rodziny Synaps opracowanego przez Synaptivo. Publiczna próba z 21 listopada objęła 30 skanów UZP i trwała 2 min 44 s. [Karta modelu](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B)

## Ocena wsadowa na VM UZP

Drużyna otrzymała VM. Polecenie wsadowe w wersji `8889069` przetworzyło tu 30 publicznych skanów w 8 min 31 s z F1 0,9935. Przy ocenie zgłoszenia jury umieszcza PDF-y w `/opt/solution/input/<sprawa>/`, uruchamia polecenie z `/opt/solution/RUN.md` i pobiera pliki z `/opt/solution/output`. Obraz projektu zawiera Python 3.13 i OCR. Zespół konfiguruje usługę wraz z kluczem w `/opt/solution/.env` przed odcięciem dostępu o 11.00. [Polecenie dla jury](../RUN.md) · [Instrukcja VM UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/VM.md)

## Pokaz interfejsu w Windows

Dotychczasowy pomiar wykonaliśmy pod adresem `https://api.synaptivo.eu/v1` z modelem `Synaptivo/Synaps-PL-Small-4B`. Pomiar dokumentuje próbę na publicznych przykładach. Do dokumentów oceny zespół musi wskazać adres usługi z potwierdzoną lokalizacją przetwarzania i przyjętą polityką prywatności. Do pokazu na publicznych przykładach w Windows użyj adresu i klucza przekazanych przez zespół. Zalecany jest Python 3.13 z programem `py`. Z katalogu z `start_ui.bat` wykonaj polecenia w PowerShell i wpisz klucz w ukrytym polu. Ustawienia obowiązują w bieżącej konsoli i jej procesach.

```powershell
$env:O2J_API_BASE = Read-Host 'Adres API przekazany przez zespół, z końcówką /v1'
$env:O2J_API_MODEL = 'Synaptivo/Synaps-PL-Small-4B'
$env:O2J_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'Klucz jury' -AsSecureString)).Password
```

Przy lokalnym OCR pozostaw `O2J_OCR_BASE` nieustawione. PDF-y i obrazy stron pozostają w środowisku oceny. Do API trafiają tekst i pola formularza. Polityka dostawcy opisuje zakres i miejsce przetwarzania. [Polityka prywatności API Synapsa](https://synaptivo.eu/api/polityka-prywatnosci/) · [Dokumentacja API](https://synaptivo.eu/api/) · [Kopia polityki na VM](./POLITYKA-PRYWATNOSCI-API-SYNAPS.md)

## Pierwsza próba

1. Uruchom `.\start_ui.bat` z tej samej konsoli. Otwórz w przeglądarce `http://127.0.0.1:8080`. W informacji o modelu sprawdź tryb API i nazwę wskazaną przez zespół.
2. Pobierz [przelew.pdf](./prezentacja/demo/przelew.pdf) i [wzorzec UZP](./prezentacja/demo/wzorzec-uzp.json) ze sprawy nr 02. Wgraj PDF, uruchom ekstrakcję i porównaj wynik ze wzorcem. Data operacji to **2026-08-23**, a kwota **50,00 zł**. [Oryginalne pliki organizatora](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/0b360a9da4b482a6a280696df6714404e0953505/dane/przyklad_02)
3. Z widoku dokumentu pobierz JSON. Z widoku sprawy możesz również pobrać wyniki w ZIP.

## Przetwarzanie zbioru

Umieść PDF-y w podkatalogach spraw w `input`, np. `input/sprawa_02/przelew.pdf`. W tej samej konsoli możesz uruchomić tryb wsadowy. Skrypt przyjmie przekazane wcześniej ustawienia API i przygotuje środowisko Pythona, jeśli jest potrzebne.

```powershell
.\start.bat --input .\input --output .\output --trace .\trace
```

Wynik przykładu trafi do `output/sprawa_02/przelew.json`. Ślad ekstrakcji i pola do sprawdzenia znajdują się w `trace`. W razie komunikatu o przełączeniu na lokalny GGUF sprawdź adres, nazwę modelu i ważność klucza przed pomiarem czasu Synapsa. Na czas oceny całej partii UZP przeznacza 45 minut na 150 PDF-ów. [Zasady UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/README.md)
