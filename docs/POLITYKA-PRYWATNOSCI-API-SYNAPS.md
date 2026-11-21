# Polityka prywatności konkursowego API Synaps

**Projekt do zatwierdzenia przez Synaptivo sp. z o.o. · 21 listopada 2026 r.** Dotyczy wersji projektu ODWOŁANIA2JSON dla Urzędu Zamówień Publicznych podczas HackNation 2026. Działa serwer testowy. Dostęp dla jury jest w przygotowaniu. Pola w nawiasach kwadratowych wymagają uzupełnienia przed publikacją.

## Kto świadczy usługę i w jakim celu

Dostawcą jest **Synaptivo sp. z o.o.**, ul. Falista 168/9, 94-115 Łódź, KRS 0001147537. W sprawach prywatności można napisać na adres pocztowy spółki. **[Synaptivo — właściwy kontakt elektroniczny do spraw danych oraz kontakt do inspektora ochrony danych, jeśli został wyznaczony.]** [Dane kontaktowe spółki](https://synaptivo.eu/kontakt/)

API służy do oceny prototypu przez upoważnionych członków jury. Aplikacja odczytuje dane z odwołań do Krajowej Izby Odwoławczej, pełnomocnictw i potwierdzeń przelewów. Synaps-PL Small 4B, polski model językowy z rodziny Synaps opracowany przez Synaptivo, proponuje wartości do formularza. Osoba oceniająca może porównać wynik z dokumentem. Usługa nie rozstrzyga odwołań ani nie podejmuje decyzji wywołujących skutki prawne wobec osób wymienionych w aktach.

## Jakie dane trafiają do API

| Etap | Dane i sposób ich użycia |
|---|---|
| Na komputerze oceniającego | Aplikacja odczytuje tekst z PDF. Skany rozpoznaje lokalnie za pomocą OCR. Plik PDF i obrazy stron pozostają w środowisku oceniającego. Tam też zapisywane są wynikowy JSON, ślad odczytu i pola wymagające sprawdzenia. O czasie przechowywania tych lokalnych plików decyduje podmiot zarządzający tym środowiskiem. |
| Żądanie do modelu | Aplikacja przekazuje tekst odczytany z dokumentu, instrukcję, nazwy pól i ich dotychczas odczytane wartości. Krótki dokument może zmieścić się w żądaniu w całości jako tekst. Model odsyła proponowane wartości, a aplikacja sprawdza je i składa wynik. Ten sam tekst może wystąpić w kilku żądaniach dotyczących jednego dokumentu. |
| Dostęp techniczny | Aplikacja posługuje się kluczem testowym jury do uwierzytelnienia połączenia. Do obsługi żądania i błędów system przetwarza także dane połączenia. **[Claude — wpisać faktycznie utrwalane metadane, np. czas, adres IP lub ścieżkę żądania, status HTTP i identyfikator żądania, odpowiednio do konfiguracji.]** |

Dane o osobach wymienionych w aktach pochodzą z plików przekazanych przez oceniającego. Dane techniczne dotyczą użytkowników API i powstają podczas połączenia. Dane odczytane z akt, zależnie od ich treści, mogą obejmować imiona i nazwiska stron, pełnomocników, osób podpisujących i płatników, ich funkcje, adresy, dane kontaktowe, identyfikatory, dane rachunków, kwoty, daty i tytuły płatności oraz treść czynności procesowych. W tekście mogą też wystąpić informacje o innych osobach wymienionych w piśmie.

## Gdzie przetwarzamy dane i kto ma do nich dostęp

W konfiguracji testowej model działa na serwerze Synaptivo w **Polsce**, a OCR na komputerze oceniającego. Dla dostępu jury zespół planuje użyć usługi Cloudflare Tunnel przed serwerem Synaptivo. W proponowanej konfiguracji połączenie z aplikacji jest odszyfrowywane w warstwie Cloudflare, która może wówczas przetwarzać treść żądania i odpowiedzi. Region odszyfrowania i miejsca przechowywania logów wersji konkursowej czekają na weryfikację. Warunkiem UZP są serwery usługi w UE/EOG. Odbiorcami wyników są upoważnieni oceniający.

**[Claude — wersja dla jury: kraj serwera modelu, nazwa operatora i kraj, w którym brama lub tunel odszyfrowuje żądania. Podać również dostawców i kraje logów, monitoringu, kopii oraz dostępu serwisowego, zakres widocznych dla nich danych i krąg uprawnionych osób. Jeśli spółka nie korzysta z pośrednika na danym etapie, wpisać to po sprawdzeniu.]**

**[Synaptivo — na podstawie powyższych ustaleń podać, czy dochodzi do przekazania danych poza EOG. Jeżeli tak, podać odbiorcę, kraj, podstawę transferu i sposób uzyskania informacji o zabezpieczeniach, a przed udostępnieniem usługi zweryfikować warunek lokalizacji UZP.]**

## Przechowywanie, ochrona i uczenie modelu

Serwer używa pamięci operacyjnej do wygenerowania odpowiedzi. Okres przetwarzania zależy od tego, czy dane są też buforowane lub utrwalane przez serwer, bramę albo system monitoringu.

| Rodzaj danych | Informacja do wpisania dla uruchomionej usługi |
|---|---|
| Treść odczytana z dokumentu, polecenia i odpowiedzi | **[Claude — czas obecności w pamięci i pamięci podręcznej modelu, moment zwolnienia oraz informacja, czy treść jest utrwalana w którejkolwiek warstwie. Dla każdego zapisu podać cel i termin usunięcia albo kryterium jego ustalenia.]** |
| Metadane dostępu i błędów | **[Claude — wskazać okres lub kryterium retencji dla serwera, bramy i monitoringu oraz sposób usunięcia. Opisać również zachowanie przy błędnym żądaniu.]** |
| Kopie zapasowe i dane po zakończeniu oceny | **[Claude — określić, co wchodzi do kopii, gdzie są przechowywane i kiedy wygasają. Podać sposób zakończenia dostępu jury i usunięcia albo zwrotu powierzonych danych.]** |

Projekt polityki przewiduje wykorzystanie treści dokumentów i odpowiedzi wyłącznie do wykonania żądań konkursowych. Wyklucza ich użycie do treningu, dostrajania, budowy zbiorów oraz ulepszania modeli przez Synaptivo i jego usługodawców. **[Claude — potwierdzić ustawienia serwera i usług pośrednich, w tym telemetrię, przed przyjęciem tej deklaracji.]**

**[Claude — potwierdzić szyfrowanie połączenia jury z usługą i połączenia bramy z serwerem, kontrolę dostępu kluczem oraz ograniczenie dostępu personelu. Podać wyłącznie potwierdzone środki ochrony.]**

## Odpowiedzialność i prawa osób

**Treść akt.** Proponowany model zakłada, że podmiot określający cel przekazania dokumentów do oceny jest administratorem, a Synaptivo wykonuje ekstrakcję na jego udokumentowane polecenie. **[Synaptivo — ustalić rzeczywiste role ze stroną przekazującą dane. Wpisać nazwę i kontakt administratora, cel i podstawę prawną przetwarzania lub odsyłacz do jego informacji. W przypadku powierzenia uzgodnić warunki z art. 28 RODO.]**

**Obsługa dostępu.** **[Synaptivo — wskazać, kto określa cele obsługi kluczy, zabezpieczenia usługi i obsługi zgłoszeń. Dla własnych celów spółki podać konkretne dane, podstawę prawną i retencję. Przy art. 6 ust. 1 lit. f RODO wskazać realizowany prawnie uzasadniony interes.]** Klucz jest potrzebny do połączenia z API, a tekst dokumentu do odczytania jego pól.

Osoba, której dane dotyczą, może zwrócić się do właściwego administratora o dostęp do danych, ich sprostowanie, usunięcie lub ograniczenie przetwarzania. Zależnie od podstawy i warunków określonych w RODO może jej także przysługiwać prawo do sprzeciwu, przenoszenia danych lub cofnięcia zgody, jeżeli przetwarzanie opiera się na zgodzie. Wniosek dotyczący powierzonych akt, który wpłynie do Synaptivo, spółka przekaże właściwemu administratorowi i pomoże w jego obsłudze. Można wnieść skargę do właściwego organu nadzorczego, w Polsce do Prezesa Urzędu Ochrony Danych Osobowych. [Składanie skarg do Prezesa UODO](https://uodo.gov.pl/pl/526/2464)

**[Synaptivo — wpisać datę obowiązywania i publiczny adres zatwierdzonej wersji.]**

---

## Do potwierdzenia przez Claude po uruchomieniu API

To karta robocza zespołu. W sprawdzonym dzienniku serwera testowego Claude zaobserwował adres i status odpowiedzi, bez tekstu dokumentu. Wersja dostępna jury wymaga odrębnej próby na dokumencie syntetycznym. Do każdego punktu zapisać wynik, datę, wersję wdrożenia i dowód bez kluczy, treści akt ani nagłówków autoryzacji.

| Co potwierdzić | Jakiego dowodu potrzebuje spółka |
|---|---|
| 1. Przepływ danych i lokalny OCR | Próba ze skanem i tekstowym PDF. Potwierdzić, że zdalny OCR jest wyłączony (`O2J_OCR_BASE` nieustawione), żądania do modelu zawierają tekst i pola formularza, a plik i obrazy stron pozostają na komputerze. Wystarczą nazwy pól, typy danych, typ treści i wynik testu. |
| 2. Kraje, podmioty i dostęp | Dla nazwy hosta udostępnionej jury wskazać operatora, kraje lub wiążące ograniczenie regionalne, zakres danych i dostęp serwisowy w każdym miejscu przetwarzania. Przy Cloudflare osobno potwierdzić region zakończenia szyfrowania TLS dla żądań HTTPS oraz lokalizację logów, również ich eksportów. Dołączyć ustawienia zastosowane dla tej usługi i warunki dostawcy. Pojedyncze połączenie przez węzeł w Polsce nie dowodzi ograniczenia wszystkich żądań do UE/EOG. [Cloudflare o regionalizacji HTTPS](https://developers.cloudflare.com/data-localization/regional-services/) · [Cloudflare o lokalizacji logów](https://developers.cloudflare.com/data-localization/metadata-boundary/) |
| 3. Zapisy, pamięć podręczna i usuwanie | Wysłać syntetyczne żądanie ze znacznikiem i wywołać zwykły błąd walidacji. Sprawdzić ustawienia i próbki logów modelu, bramy i monitoringu, zasady pamięci podręcznej oraz zakres kopii. Zapisać pola, precyzyjny czas lub kryterium retencji i sposób usunięcia dla każdej warstwy. |
| 4. Dalsze użycie danych | Potwierdzić ustawienia i warunki operatorów dotyczące treningu, dostrajania, telemetrii, analizy treści i udostępniania żądań. Wskazać, czy dane opuszczają opisaną trasę. |
| 5. Dostęp jury i jego zakończenie | Z komputera spoza środowiska testowego sprawdzić właściwy adres HTTPS, prawidłowy certyfikat, odmowę bez klucza i odpowiedź Synapsa z kluczem. Potwierdzić ochronę połączenia z serwerem, sposób odwołania klucza i osobę obsługującą incydenty. Zachować datę i kody odpowiedzi. |

**Decyzja Synaptivo przed publikacją.** Na podstawie wyników spółka akceptuje role, podstawy prawne, kontakt, ewentualnych podwykonawców i transfery. Jeśli lokalizacja serwera obsługującego dane konkursowe pozostaje nieznana lub wypada poza UE/EOG, spółka uzgadnia odpowiednią konfigurację przed dopuszczeniem ruchu jury. Po weryfikacji uzupełnia pola robocze i publikuje zatwierdzony tekst do końca sekcji „Odpowiedzialność i prawa osób”. Jury otrzymuje adres obowiązującej polityki. UZP wymaga firmowego dostawcy, wskazania zakresu i miejsca przetwarzania w jego polityce, serwerów w UE/EOG oraz klucza testowego. [Wymagania UZP, część 6](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md?plain=1#L160) · [RODO, w szczególności art. 5–6, 12–14, 15–22, 28, 32 i 44–49](https://eur-lex.europa.eu/legal-content/PL/TXT/?uri=CELEX:32016R0679)
