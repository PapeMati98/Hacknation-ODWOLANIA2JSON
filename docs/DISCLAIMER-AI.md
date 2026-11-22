# Oświadczenie o wykorzystaniu sztucznej inteligencji

**Projekt:** JSON, ja tu tylko parsuję (Odwołania2JSON) · **Drużyna:** Nie wiem, ale wygeneruję · **Zadanie:** [UZP] Odwołania2JSON, HackNation 2026

## Krótka wersja (do zgłoszenia, slajdu lub opisu filmu)

> Przy tworzeniu projektu korzystaliśmy z narzędzi sztucznej inteligencji: asystentów programowania i redakcji (Claude, Gemini w Antigravity, Grok, Codex) oraz syntezatora mowy w filmie. Pola z dokumentów odczytuje otwarty model językowy Synaps-PL Small 4B (Apache 2.0). Wszystkie wyniki AI zespół przejrzał, sprawdził i zaakceptował. Za architekturę, decyzje projektowe, kod i wyniki odpowiada zespół. Dane testowe są syntetyczne albo publiczne, a dane osobowe w nich fikcyjne.

## Co mówi regulamin

Regulamin HackNation 2026 nie zakazuje korzystania z narzędzi AI i nie wymaga ich oznaczania. Ma jednak rozdział 6 „Własność intelektualna”:

- **pkt 6.1:** każdy uczestnik oświadcza, że w zakresie swojego wkładu jest twórcą rozwiązania i ma do tego wkładu pełne autorskie prawa majątkowe;
- **pkt 6.2:** uczestnik oświadcza, że jego wkład nie narusza praw osób trzecich, w szczególności praw autorskich;
- **pkt 5.8:** po upływie czasu nie wolno zmieniać rozwiązania.

To oświadczenie ma pokazać jury, gdzie użyliśmy AI i co jest pracą zespołu. Na tej podstawie zespół może złożyć oświadczenia z pkt 6.1 i 6.2. Wymagania zadania UZP (otwarte komponenty, otwarty model językowy, dostawca API z serwerami w UE/EOG) opisują [ustalenia UZP](./USTALENIA-UZP.md).

## AI jako część rozwiązania

| Składnik | Do czego służy | Licencja |
|---|---|---|
| Synaps-PL Small 4B (Synaptivo, na bazie Qwen3.5-4B) | odczyt pól z tekstu dokumentu, wariant konkursowy przez API | Apache 2.0, otwarte wagi |
| Qwen3.5-4B (GGUF) przez llama.cpp | alternatywny wariant w pełni lokalny na CPU | Apache 2.0 / MIT |
| RapidOCR z modelami PP-OCR | rozpoznawanie tekstu na skanach | Apache 2.0 |

Model nie podejmuje ostatecznych decyzji. Każdą wartość aplikacja sprawdza regułami, które napisał zespół: sumy kontrolne NIP/REGON/PESEL i rachunku, obecność wartości w dokumencie, zgodność między pismami sprawy. Wartość niepewna zostaje pusta i trafia na listę „do sprawdzenia” dla człowieka. Pełna lista komponentów i licencji jest w [README](../README.md).

## AI jako narzędzie pracy zespołu

| Narzędzie | Do czego użyte |
|---|---|
| Claude (Anthropic), w tym Claude Code | pomoc przy kodzie i dokumentacji, przygotowanie etykiet do pomiaru F1 (`eval/gold-real`), generator syntetycznych danych testowych (`eval/trudne`), redakcja tekstów zgłoszenia, okładka, dopasowanie kolorów prezentacji, scenariusz i montaż filmu. Commity z udziałem Claude mają dopisek `Co-Authored-By`. |
| Gemini w Antigravity | projekt interfejsu webowego |
| Grok, Codex | pomoc przy programowaniu i analizie |
| Lokalny Qwen jako „nauczyciel” | etykiety pomocnicze do dostrajania, obok wzorców JSON organizatora |
| Syntezator mowy macOS (głos „Zosia”) | lektor w 45-sekundowym filmie, głos syntetyczny |

## Co jest pracą zespołu

- wybór podejścia i architektura (PDF → OCR → klasyfikacja → ekstrakcja → walidacja → JSON), konfiguracja klas w YAML i reguły walidacji;
- decyzje, które podpowiedzi AI przyjąć, poprawić albo odrzucić; przegląd i testowanie kodu;
- pomiary F1 i czasu, wdrożenie na maszynie UZP, prezentacja i wystąpienie przed jury.

## Dane i materiały

- **Dane testowe:** publiczne przykłady UZP, publiczne orzeczenia KIO z orzeczenia.uzp.gov.pl oraz dokumenty syntetyczne. Dane osobowe i numery w dokumentach syntetycznych są fikcyjne (prefiks 999, poprawne sumy kontrolne).
- **Etykiety od Claude** służą tylko do pomiaru F1, nie do trenowania modelu.
- **Znaki UZP, HackNation i Synaptivo** są użyte wyłącznie do oznaczenia wydarzenia, zadania i dostawcy modelu.
- **Grafiki** (okładka, diagramy) przygotowano programowo, bez generatorów obrazów.

## Przejrzystość

Model Synaps-PL Small 4B udostępnia firma Synaptivo, której prezesem jest członek zespołu, Mateusz Pietrzak. Wagi modelu są publiczne na licencji Apache 2.0, a zasady przetwarzania danych w API opisuje [polityka prywatności API](./POLITYKA-PRYWATNOSCI-API-SYNAPS.md).

---

*Oświadczenie przygotowano 22 listopada 2026 r. na podstawie repozytorium projektu i regulaminu HackNation 2026. Nie stanowi porady prawnej.*
