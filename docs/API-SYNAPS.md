# API polskiego modelu Synaps-PL Small 4B

Synaptivo udostępnia model do prób odczytu pól z dokumentów. W aplikacji Odwołania2JSON pliki PDF, OCR i składanie wynikowego JSON pozostają po stronie oceniającego. API dostaje tekst i zwraca proponowane wartości. [Polityka prywatności API](./POLITYKA-PRYWATNOSCI-API-SYNAPS.md) · [Karta modelu i licencja Apache 2.0](https://huggingface.co/Synaptivo/Synaps-PL-Small-4B)

## Połączenie i model

| Ustawienie | Wartość |
|---|---|
| Adres sprawdzony w próbach na publicznych przykładach | `https://api.synaptivo.eu/v1` |
| Identyfikator modelu | `Synaptivo/Synaps-PL-Small-4B` |
| Uwierzytelnianie | Nagłówek `Authorization: Bearer <klucz>` |
| Dane żądania i odpowiedzi | JSON, w kodowaniu UTF-8 |
| Dostęp konkursowy | Klucz przyznaje zespół. Na maszynie jury aplikacja odczytuje go z `/opt/solution/.env`. |

## Metody dla klienta

| Metoda | Do czego służy |
|---|---|
| `GET /v1/models` | Zwraca identyfikatory modeli dostępne po uwierzytelnieniu. |
| `POST /v1/completions` | Przyjmuje `model` i tekstowy `prompt`. Aplikacja konkursowa pobiera wartość pola z `choices[0].text`. |
| `POST /v1/chat/completions` | Przyjmuje `model` i listę `messages`. Tekst odpowiedzi jest w `choices[0].message.content`. |

## Próba na danych fikcyjnych

Przykład dla Bash. Zmienna `O2J_API_KEY` zawiera klucz przekazany uprawnionej osobie. Wstaw do skryptu nazwę zmiennej, dzięki czemu jej wartość pozostanie poza treścią dokumentacji.

```bash
curl --fail-with-body --silent --show-error \
  --header "Authorization: Bearer ${O2J_API_KEY:?ustaw klucz testowy}" \
  https://api.synaptivo.eu/v1/models
```

Poniższy przykład sprawdza odczyt numeru z jednego fikcyjnego zdania. Aplikacja konkursowa dodatkowo porównuje wynik modelu z dokumentem.

```bash
curl --fail-with-body --silent --show-error \
  --header "Authorization: Bearer ${O2J_API_KEY:?ustaw klucz testowy}" \
  --header 'Content-Type: application/json' \
  --data '{"model":"Synaptivo/Synaps-PL-Small-4B","prompt":"Dokument fikcyjny. Numer sprawy: DEMO-17. Przepisz numer sprawy:","max_tokens":24,"temperature":0}' \
  https://api.synaptivo.eu/v1/completions
```

## Limity i błędy

W konfiguracji zgłoszonej dla prób konkursowych brama przyjmuje do 16 MiB na żądanie i ustawia maksymalnie 4096 generowanych tokenów. Dla jednego klucza limit wynosi 6000 żądań na minutę. Do serwera modelu trafia jednocześnie do 16 żądań. Po 120 sekundach oczekiwania na wolne miejsce brama może zwrócić HTTP 503. Odpowiedź wraca jako pojedynczy dokument JSON. Ustaw `stream` na `false` albo pomiń to pole.

| Odpowiedź | Co sprawdzić |
|---|---|
| `400` lub `413` | Sprawdź składnię, obsługiwane pola i rozmiar żądania. |
| `404` | Sprawdź adres metody i identyfikator modelu. |
| `401` | Sprawdź, czy w środowisku jest ważny klucz i czy żądanie zawiera nagłówek Bearer. |
| `429` | Ogranicz liczbę wywołań i ponów po przerwie. |
| `502` lub `503` | Usługa jest chwilowo niedostępna lub zajęta. Ponów po przerwie. |

W sprawie dostępu konkursowego i prywatności kontakt przyjmuje **Mateusz Pietrzak, Prezes Zarządu Synaptivo**. W zgłoszeniu technicznym wystarczą godzina, metoda i kod odpowiedzi. [mateusz.pietrzak@synaptivo.eu](mailto:mateusz.pietrzak@synaptivo.eu) · [Instrukcja uruchomienia jury](../RUN.md)
