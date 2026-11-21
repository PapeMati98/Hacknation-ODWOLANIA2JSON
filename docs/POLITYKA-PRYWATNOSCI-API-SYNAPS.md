# Polityka prywatności konkursowego API Synaps

**Mateusz zatwierdził projekt polityki 21 listopada 2026 r.** Akceptacja dotyczy [przedstawionej wersji 0e428bb](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON/blob/0e428bb4c27d4ca0f2a162f1ab073880801565b2/docs/POLITYKA-PRYWATNOSCI-API-SYNAPS.md). Poniżej odnotowano także wynik uruchomienia API dla jury HackNation 2026. Pola w nawiasach kwadratowych wskazują dane potrzebne do publikacji obowiązującej polityki.

## Kto świadczy usługę i w jakim celu

Dostawcą jest **Synaptivo sp. z o.o.**, ul. Falista 168/9, 94-115 Łódź, KRS 0001147537. W sprawach prywatności można napisać na adres pocztowy spółki. **[Synaptivo — właściwy kontakt elektroniczny do spraw danych oraz kontakt do inspektora ochrony danych, jeśli został wyznaczony.]** [Dane kontaktowe spółki](https://synaptivo.eu/kontakt/)

API służy do oceny prototypu przez upoważnionych członków jury. Aplikacja odczytuje dane z odwołań do Krajowej Izby Odwoławczej, pełnomocnictw i potwierdzeń przelewów. Synaps-PL Small 4B, polski model językowy z rodziny Synaps opracowany przez Synaptivo, proponuje wartości do formularza. Osoba oceniająca może porównać wynik z dokumentem. Usługa nie rozstrzyga odwołań ani nie podejmuje decyzji wywołujących skutki prawne wobec osób wymienionych w aktach.

## Jakie dane trafiają do API

| Etap | Dane i sposób ich użycia |
|---|---|
| Na komputerze oceniającego | Aplikacja odczytuje tekst z PDF. Skany rozpoznaje lokalnie za pomocą OCR. Plik PDF i obrazy stron pozostają w środowisku oceniającego. Tam też zapisywane są wynikowy JSON, ślad odczytu i pola wymagające sprawdzenia. O czasie przechowywania tych lokalnych plików decyduje podmiot zarządzający tym środowiskiem. |
| Żądanie do modelu | Aplikacja przekazuje tekst odczytany z dokumentu, instrukcję, nazwy pól i ich dotychczas odczytane wartości. Krótki dokument może zmieścić się w żądaniu w całości jako tekst. Model odsyła proponowane wartości, a aplikacja sprawdza je i składa wynik. Ten sam tekst może wystąpić w kilku żądaniach dotyczących jednego dokumentu. |
| Dostęp techniczny | Klucz testowy jury uwierzytelnia połączenie. Brama Synaptivo zapisuje czas żądania, ścieżkę, kod odpowiedzi, ośmioznakowy skrót klucza, czas obsługi w milisekundach i liczby tokenów na wejściu i wyjściu. Dziennik bramy pomija treść żądań i odpowiedzi. Dziennik serwera modelu zawiera wpisy o połączeniach i zbiorcze statystyki przepustowości. **[Claude — uzupełnić zakres metadanych przetwarzanych przez Cloudflare, w tym sposób obsługi adresu IP klienta.]** |

Dane o osobach wymienionych w aktach pochodzą z plików przekazanych przez oceniającego. Dane techniczne dotyczą użytkowników API i powstają podczas połączenia. Dane odczytane z akt, zależnie od ich treści, mogą obejmować imiona i nazwiska stron, pełnomocników, osób podpisujących i płatników, ich funkcje, adresy, dane kontaktowe, identyfikatory, dane rachunków, kwoty, daty i tytuły płatności oraz treść czynności procesowych. W tekście mogą też wystąpić informacje o innych osobach wymienionych w piśmie.

## Gdzie przetwarzamy dane i kto ma do nich dostęp

Model działa na serwerze Synaptivo w **Polsce**. OCR odbywa się na komputerze oceniającego. Połączenie z aplikacji przechodzi przez Cloudflare Tunnel do bramy Synaptivo, która sprawdza klucz i kieruje żądanie do modelu. Cloudflare odszyfrowuje połączenie i może przetwarzać treść żądania oraz odpowiedzi. Region odszyfrowania i miejsca przechowywania logów dla konkursowej nazwy hosta czekają na potwierdzenie. Warunkiem UZP są serwery usługi w UE/EOG. Odbiorcami wyników są upoważnieni oceniający.

**[Claude — potwierdzić region odszyfrowania HTTPS dla `api.synaptivo.eu` oraz lokalizację logów Cloudflare i ich ewentualnych eksportów. Wskazać dostawców i kraje monitoringu, kopii i dostępu serwisowego, zakres widocznych danych i uprawnione osoby.]**

**[Synaptivo — na podstawie powyższych ustaleń podać, czy dochodzi do przekazania danych poza EOG. Jeżeli tak, podać odbiorcę, kraj, podstawę transferu i sposób uzyskania informacji o zabezpieczeniach, a przed udostępnieniem usługi zweryfikować warunek lokalizacji UZP.]**

## Przechowywanie, ochrona i uczenie modelu

Podczas generowania odpowiedzi serwer modelu wykorzystuje pamięć karty graficznej. Część przetworzonego tekstu, używana do obsługi powtarzających się początków żądań, pozostaje w pamięci do wyparcia lub restartu procesu. Serwer nie zapisuje tej pamięci podręcznej na dysk.

| Rodzaj danych | Stan dla usługi konkursowej |
|---|---|
| Tekst dokumentu, polecenia i odpowiedzi | Logowanie treści żądań w serwerze modelu jest wyłączone. Dziennik bramy Synaptivo pomija treść żądań i odpowiedzi. **[Claude — sprawdzić możliwy zapis treści w systemach pośrednika i monitoringu, także przy błędach. Podać cel i okres każdego zapisu.]** |
| Metadane dostępu i błędów | Brama i serwer modelu rejestrują wymienione wyżej dane techniczne. **[Claude — podać okres lub kryterium retencji i sposób usuwania dla dziennika systemowego bramy, serwera, Cloudflare i ewentualnych eksportów.]** |
| Kopie zapasowe i dane po zakończeniu oceny | **[Claude — określić, co wchodzi do kopii, gdzie są przechowywane i kiedy wygasają. Podać sposób zakończenia dostępu jury i usunięcia albo zwrotu powierzonych danych.]** |

Zaakceptowana przez Mateusza zasada przewiduje wykorzystanie treści dokumentów i odpowiedzi wyłącznie do wykonania żądań konkursowych. Wyklucza ich użycie do treningu, dostrajania, budowy zbiorów oraz ulepszania modeli przez Synaptivo i jego usługodawców. Telemetria serwera modelu vLLM jest wyłączona, a wagi są wczytywane lokalnie w trybie offline. **[Claude i Synaptivo — potwierdzić ustawienia i warunki dalszego użycia danych u pośredników.]**

**[Claude — potwierdzić szyfrowanie połączenia jury z usługą i połączenia bramy z serwerem, kontrolę dostępu kluczem oraz ograniczenie dostępu personelu. Podać wyłącznie potwierdzone środki ochrony.]**

## Odpowiedzialność i prawa osób

**Treść akt.** Proponowany model zakłada, że podmiot określający cel przekazania dokumentów do oceny jest administratorem, a Synaptivo wykonuje ekstrakcję na jego udokumentowane polecenie. **[Synaptivo — ustalić rzeczywiste role ze stroną przekazującą dane. Wpisać nazwę i kontakt administratora, cel i podstawę prawną przetwarzania lub odsyłacz do jego informacji. W przypadku powierzenia uzgodnić warunki z art. 28 RODO.]**

**Obsługa dostępu.** **[Synaptivo — wskazać, kto określa cele obsługi kluczy, zabezpieczenia usługi i obsługi zgłoszeń. Dla własnych celów spółki podać konkretne dane, podstawę prawną i retencję. Przy art. 6 ust. 1 lit. f RODO wskazać realizowany prawnie uzasadniony interes.]** Klucz jest potrzebny do połączenia z API, a tekst dokumentu do odczytania jego pól.

Osoba, której dane dotyczą, może zwrócić się do właściwego administratora o dostęp do danych, ich sprostowanie, usunięcie lub ograniczenie przetwarzania. Zależnie od podstawy i warunków określonych w RODO może jej także przysługiwać prawo do sprzeciwu, przenoszenia danych lub cofnięcia zgody, jeżeli przetwarzanie opiera się na zgodzie. Wniosek dotyczący powierzonych akt, który wpłynie do Synaptivo, spółka przekaże właściwemu administratorowi i pomoże w jego obsłudze. Można wnieść skargę do właściwego organu nadzorczego, w Polsce do Prezesa Urzędu Ochrony Danych Osobowych. [Składanie skarg do Prezesa UODO](https://uodo.gov.pl/pl/526/2464)

**[Synaptivo — wpisać datę obowiązywania i publiczny adres zatwierdzonej wersji.]**

---

## Do potwierdzenia przez Claude po uruchomieniu API

**Stan po uruchomieniu 21 listopada.** Claude potwierdził połączenie z `https://api.synaptivo.eu/v1` z innej maszyny przez Cloudflare, bramę Synaptivo i serwer modelu w Polsce. Klucz jury umożliwił wykonanie żądań. Bez klucza brama zwracała HTTP 401. W próbie z publicznymi materiałami UZP 747 wywołań modelu zakończyło się bez błędów. Operator sprawdził dzienniki bramy i vLLM, wyłączenie telemetrii modelu oraz zachowanie jego pamięci podręcznej. Do zamknięcia pozostają m.in. regionalizacja usług Cloudflare, okresy retencji, kopie, warunki dalszego użycia u pośredników i zakończenie dostępu jury.

Do pozostałych prób użyć dokumentu syntetycznego. Zachować wynik, datę, wersję wdrożenia i dowód bez kluczy, treści akt ani nagłówków autoryzacji.

| Co potwierdzić | Jakiego dowodu potrzebuje spółka |
|---|---|
| 1. Przepływ danych i lokalny OCR | Próba ze skanem i tekstowym PDF. Potwierdzić, że zdalny OCR jest wyłączony (`O2J_OCR_BASE` nieustawione), żądania do modelu zawierają tekst i pola formularza, a plik i obrazy stron pozostają na komputerze. Wystarczą nazwy pól, typy danych, typ treści i wynik testu. |
| 2. Kraje, podmioty i dostęp | Dla nazwy hosta udostępnionej jury wskazać operatora, kraje lub wiążące ograniczenie regionalne, zakres danych i dostęp serwisowy w każdym miejscu przetwarzania. Przy Cloudflare osobno potwierdzić region zakończenia szyfrowania TLS dla żądań HTTPS oraz lokalizację logów, również ich eksportów. Dołączyć ustawienia zastosowane dla tej usługi i warunki dostawcy. Pojedyncze połączenie przez węzeł w Polsce nie dowodzi ograniczenia wszystkich żądań do UE/EOG. [Cloudflare o regionalizacji HTTPS](https://developers.cloudflare.com/data-localization/regional-services/) · [Cloudflare o lokalizacji logów](https://developers.cloudflare.com/data-localization/metadata-boundary/) |
| 3. Zapisy, pamięć podręczna i usuwanie | **Potwierdzone przez operatora:** pola dziennika bramy, wyłączone logowanie treści żądań modelu oraz pamięć podręczna modelu w GPU do wyparcia lub restartu. Uzupełnić retencję logów systemowych i Cloudflare, zakres kopii, zasady usuwania i zachowanie przy błędzie. Do próby użyć żądania syntetycznego ze znacznikiem. |
| 4. Dalsze użycie danych | **Potwierdzone przez operatora:** telemetria vLLM jest wyłączona, a wagi są ładowane w trybie offline. Zweryfikować ustawienia oraz warunki dostawców pośrednich dotyczące telemetrii, analizy treści, treningu i udostępniania danych. |
| 5. Dostęp jury i jego zakończenie | **Potwierdzone przez Claude:** udane połączenie HTTPS spoza stacji modelu, odpowiedź z kluczem i odmowa HTTP 401 bez klucza. Uzupełnić dowód ochrony odcinka brama–model, sposób odwołania klucza i osobę obsługującą incydenty. |

**Przed publikacją.** Mateusz zaakceptował treść projektu. Spółka uzupełnia rzeczywiste role i podstawy prawne, kontakt, dane dostawców i informacje o ewentualnych transferach na podstawie ustaleń z operatorem oraz stroną przekazującą dane. Jeśli lokalizacja serwera obsługującego dane konkursowe pozostaje nieznana lub wypada poza UE/EOG, spółka uzgadnia odpowiednią konfigurację przed dopuszczeniem ruchu jury. Po weryfikacji uzupełnia pola robocze i publikuje zatwierdzony tekst do końca sekcji „Odpowiedzialność i prawa osób”. Jury otrzymuje adres obowiązującej polityki. UZP wymaga firmowego dostawcy, wskazania zakresu i miejsca przetwarzania w jego polityce, serwerów w UE/EOG oraz klucza testowego. [Wymagania UZP, część 6](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md?plain=1#L160) · [RODO, w szczególności art. 5–6, 12–14, 15–22, 28, 32 i 44–49](https://eur-lex.europa.eu/legal-content/PL/TXT/?uri=CELEX:32016R0679)
