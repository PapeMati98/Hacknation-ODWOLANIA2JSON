# ODWOŁANIA2JSON — uruchomienie oceny na VM UZP

## Polecenie dla jury

Z katalogu `/opt/solution` uruchom poniższe polecenie po umieszczeniu plików PDF w `input/<sprawa>/`. Korzysta z obrazu przygotowanego przez zespół na tej maszynie i kończy się po przetworzeniu całej partii.

```bash
sudo docker run --rm --pull=never --env-file /opt/solution/.env --mount type=bind,src=/opt/solution/input,dst=/app/input,readonly --mount type=bind,src=/opt/solution/output,dst=/app/output --volume /opt/solution/trace:/app/trace odwolania2json:jury python -m odwolania2json
```

Dla `input/sprawa_01/odwolanie.pdf` wynik znajduje się w `output/sprawa_01/odwolanie.json`. Dokument spoza obsługiwanych klas dostaje `{}`. Ślady ekstrakcji są w `trace/`. Kod zakończenia polecenia i ostatni komunikat pozwalają sprawdzić przebieg.

## Przygotowanie przez zespół przed oddaniem maszyny

1. Umieść kod, ten plik, konfigurację i `Dockerfile` bezpośrednio w `/opt/solution`. Zachowaj katalogi `input` i `output` utworzone przez organizatora.
2. Zbuduj obraz wcześniej z katalogu projektu na VM poleceniem `sudo docker build -t odwolania2json:jury .`. Obraz zawiera Python 3.13, zależności aplikacji i modele OCR. Sprawdź jego obecność przez `sudo docker image inspect --format '{{.Id}}' odwolania2json:jury`.
3. W pliku `/opt/solution/.env` umieść po jednej wartości na linię w formacie `NAZWA=wartość`. Wymagane są `O2J_API_BASE` (zweryfikowany adres usługi Synaptivo zakończony `/v1`), `O2J_API_MODEL=Synaptivo/Synaps-PL-Small-4B` i `O2J_API_KEY` (klucz testowy zespołu). Osoba konfigurująca VM ustawia prawa dostępu do pliku tak, aby klucz mogło odczytać konto administracyjne oceniających. Pozostaw `O2J_OCR_BASE` nieustawione. Sam OCR działa na CPU maszyny, a ekstrakcja pól korzysta z zewnętrznego API polskiego modelu Synaps-PL Small 4B.
4. Umieść [przykładowy przelew UZP](docs/prezentacja/demo/przelew.pdf) w podkatalogu sprawy w `input/` i wykonaj dokładnie polecenie jury. Porównaj sześć pól z [wzorcem UZP](docs/prezentacja/demo/wzorzec-uzp.json). Sprawdź także jeden publiczny skan. Po próbie pozostaw oba katalogi organizatora przygotowane na jego zbiór. Zależności i obrazy mają być dostępne na miejscu również po restarcie.

Dostęp zespołu do VM kończy się 22 listopada 2026 o godz. 11.00 czasu polskiego. Oceniający uruchamiają partię samodzielnie. [Instrukcja VM opublikowana przez UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/VM.md)

Zakres danych wysyłanych do API i miejsce ich przetwarzania opisuje Synaptivo. [Dokumentacja API](https://synaptivo.eu/api/) · [Polityka prywatności](https://synaptivo.eu/api/polityka-prywatnosci/) · [Kopia na tej maszynie](docs/POLITYKA-PRYWATNOSCI-API-SYNAPS.md)
