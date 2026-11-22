# Polityka prywatności konkursowego API Synaps

**Mateusz zatwierdził projekt polityki 21 listopada 2026 r.** Akceptacja dotyczy [przedstawionej wersji 0e428bb](https://github.com/PapeMati98/Hacknation-ODWOLANIA2JSON/blob/0e428bb4c27d4ca0f2a162f1ab073880801565b2/docs/POLITYKA-PRYWATNOSCI-API-SYNAPS.md). Aktualizacja z 22 listopada obejmuje próbę API i informacje przekazane przez operatora bramy. Publiczna strona spółki w dniu kontroli zapowiadała publikację treści. Pola w nawiasach kwadratowych wskazują dane potrzebne do publikacji obowiązującej polityki.

## Kto świadczy usługę i w jakim celu

Dostawcą jest **Synaptivo sp. z o.o.**, ul. Falista 168/9, 94-115 Łódź, KRS 0001147537. W sprawach prywatności można napisać na adres pocztowy spółki. Spółka udostępnia również ogólny formularz kontaktowy. **[Synaptivo — potwierdzić obsługę wniosków o dane tą drogą i podać kontakt do inspektora ochrony danych, jeśli został wyznaczony.]** [Dane kontaktowe spółki](https://synaptivo.eu/kontakt/)

API służy do oceny prototypu przez upoważnionych członków jury. Aplikacja odczytuje dane z odwołań do Krajowej Izby Odwoławczej, pełnomocnictw i potwierdzeń przelewów. Synaps-PL Small 4B, polski model językowy z rodziny Synaps opracowany przez Synaptivo, proponuje wartości do formularza. Osoba oceniająca może porównać wynik z dokumentem. Usługa nie rozstrzyga odwołań ani nie podejmuje decyzji wywołujących skutki prawne wobec osób wymienionych w aktach.

## Jakie dane trafiają do API

| Etap | Dane i sposób ich użycia |
|---|---|
| Na komputerze oceniającego | Aplikacja odczytuje tekst z PDF. Skany rozpoznaje lokalnie za pomocą OCR. Plik PDF i obrazy stron pozostają w środowisku oceniającego. Tam też zapisywane są wynikowy JSON, ślad odczytu i pola wymagające sprawdzenia. O czasie przechowywania tych lokalnych plików decyduje podmiot zarządzający tym środowiskiem. |
| Żądanie do modelu | Aplikacja przekazuje tekst odczytany z dokumentu, instrukcję, nazwy pól i ich dotychczas odczytane wartości. Krótki dokument może zmieścić się w żądaniu w całości jako tekst. Model odsyła proponowane wartości, a aplikacja sprawdza je i składa wynik. Ten sam tekst może wystąpić w kilku żądaniach dotyczących jednego dokumentu. |
| Dostęp techniczny | Klucz testowy jury uwierzytelnia połączenie. Brama Synaptivo zapisuje czas żądania, ścieżkę, kod odpowiedzi, ośmioznakowy skrót klucza, czas obsługi w milisekundach i liczby tokenów na wejściu i wyjściu. Dziennik bramy pomija adres IP klienta oraz treść żądań i odpowiedzi. Dziennik serwera modelu zawiera adres połączenia lokalnego, kod odpowiedzi i zbiorcze statystyki przepustowości. **[Claude — uzupełnić zakres metadanych przetwarzanych przez Cloudflare, w tym sposób obsługi adresu IP klienta.]** |

Dane o osobach wymienionych w aktach pochodzą z plików przekazanych przez oceniającego. Dane techniczne dotyczą użytkowników API i powstają podczas połączenia. Dane odczytane z akt, zależnie od ich treści, mogą obejmować imiona i nazwiska stron, pełnomocników, osób podpisujących i płatników, ich funkcje, adresy, dane kontaktowe, identyfikatory, dane rachunków, kwoty, daty i tytuły płatności oraz treść czynności procesowych. W tekście mogą też wystąpić informacje o innych osobach wymienionych w piśmie.

## Gdzie przetwarzamy dane i kto ma do nich dostęp

Synaptivo wykonuje inferencję na własnym serwerze w **Polsce**. OCR odbywa się w środowisku oceniającego. W sprawdzonej konfiguracji ruch dla `api.synaptivo.eu` trafia do Cloudflare. Dostawca kończy połączenie TLS na swojej infrastrukturze i może przetwarzać tekst oraz wynik. Według operatora usługa działa w planie Free. Odszyfrowanie odbywa się w centrum obsługującym dane żądanie i nie ma gwarancji ograniczenia go do UE/EOG. Od Cloudflare do serwera w Polsce ruch przechodzi szyfrowanym tunelem. Automatyczny eksport logów przez Logpush jest wyłączony. Lokalizacja i retencja własnych logów Cloudflare pozostają nieustalone. Odbiorcami wyników są upoważnieni oceniający. [Regionalizacja HTTPS w Cloudflare](https://developers.cloudflare.com/data-localization/regional-services/) · [Lokalizacja metadanych](https://developers.cloudflare.com/data-localization/metadata-boundary/)

**[Claude i Synaptivo — dla konfiguracji wybranej do oceny przedstawić podstawę ograniczenia miejsc przetwarzania do UE/EOG, w tym miejsca odszyfrowania. Ustalić kraje i retencję logów, ewentualne inne eksporty, monitoring, kopie i dostęp personelu. Jeśli trasa się zmieni, zaktualizować jej opis i ponowić próbę na dokumencie testowym.]**

**[Synaptivo — na podstawie powyższych ustaleń podać, czy dochodzi do przekazania danych poza EOG. Jeżeli tak, podać odbiorcę, kraj, podstawę transferu i sposób uzyskania informacji o zabezpieczeniach, a przed udostępnieniem usługi zweryfikować warunek lokalizacji UZP.]**

## Przechowywanie, ochrona i uczenie modelu

Podczas generowania odpowiedzi serwer modelu wykorzystuje pamięć karty graficznej. Część przetworzonego tekstu, używana do obsługi powtarzających się początków żądań, pozostaje w pamięci do wyparcia lub restartu procesu. Serwer nie zapisuje tej pamięci podręcznej na dysk.

| Rodzaj danych | Stan dla usługi konkursowej |
|---|---|
| Tekst dokumentu, polecenia i odpowiedzi | Logowanie treści żądań w serwerze modelu jest wyłączone. Dziennik bramy Synaptivo pomija treść żądań i odpowiedzi. **[Claude — sprawdzić możliwy zapis treści w systemach pośrednika i monitoringu, także przy błędach. Podać cel i okres każdego zapisu.]** |
| Metadane dostępu i błędów | Dziennik systemowy bramy (`journald`) rotuje wpisy według rozmiaru. Operator nie ustalił stałego okresu w dniach. Eksport Cloudflare Logpush jest wyłączony. **[Claude — uzupełnić kryteria usuwania logów serwera modelu, Cloudflare i innych ewentualnych systemów oraz potwierdzić skonfigurowany limit rozmiaru dziennika bramy.]** |
| Kopie zapasowe i dane po zakończeniu oceny | Na polecenie Mateusza operator bramy może unieważnić klucz jury, usuwając jego wpis z listy uprawnionych kluczy i restartując bramę. **[Claude i Synaptivo — wskazać termin zakończenia dostępu, zakres i lokalizację kopii, ich wygasanie oraz sposób usunięcia lub zwrotu powierzonych danych.]** |

Zaakceptowana przez Mateusza zasada przewiduje wykorzystanie treści dokumentów i odpowiedzi wyłącznie do wykonania żądań konkursowych. Wyklucza ich użycie do treningu, dostrajania, budowy zbiorów oraz ulepszania modeli przez Synaptivo i jego usługodawców. Telemetria serwera modelu vLLM jest wyłączona, a wagi są wczytywane lokalnie w trybie offline. **[Claude i Synaptivo — potwierdzić ustawienia i warunki dalszego użycia danych u pośredników.]**

Test usługi potwierdził dostęp przez HTTPS z kluczem oraz odmowę połączenia z API bez klucza. Operator potwierdził szyfrowanie tunelu prowadzącego od Cloudflare do serwera. **[Claude — udokumentować uprawnienia personelu i zabezpieczenia pozostałych odcinków wewnętrznych.]**

## Odpowiedzialność i prawa osób

**Treść akt.** Proponowany model zakłada, że podmiot określający cel przekazania dokumentów do oceny jest administratorem, a Synaptivo wykonuje ekstrakcję na jego udokumentowane polecenie. **[Synaptivo — ustalić rzeczywiste role ze stroną przekazującą dane. Wpisać nazwę i kontakt administratora, cel i podstawę prawną przetwarzania lub odsyłacz do jego informacji. W przypadku powierzenia uzgodnić warunki z art. 28 RODO.]**

**Obsługa dostępu.** **[Synaptivo — wskazać, kto określa cele obsługi kluczy, zabezpieczenia usługi i obsługi zgłoszeń. Dla własnych celów spółki podać konkretne dane, podstawę prawną i retencję. Przy art. 6 ust. 1 lit. f RODO wskazać realizowany prawnie uzasadniony interes.]** Klucz jest potrzebny do połączenia z API, a tekst dokumentu do odczytania jego pól.

Osoba, której dane dotyczą, może zwrócić się do właściwego administratora o dostęp do danych, ich sprostowanie, usunięcie lub ograniczenie przetwarzania. Zależnie od podstawy i warunków określonych w RODO może jej także przysługiwać prawo do sprzeciwu, przenoszenia danych lub cofnięcia zgody, jeżeli przetwarzanie opiera się na zgodzie. Wniosek dotyczący powierzonych akt, który wpłynie do Synaptivo, spółka przekaże właściwemu administratorowi i pomoże w jego obsłudze. Można wnieść skargę do właściwego organu nadzorczego, w Polsce do Prezesa Urzędu Ochrony Danych Osobowych. [Składanie skarg do Prezesa UODO](https://uodo.gov.pl/pl/526/2464)

**[Synaptivo — wpisać datę obowiązywania i publiczny adres zatwierdzonej wersji.]**

---

## Do potwierdzenia przez Claude po uruchomieniu API

**Stan po kontroli 22 listopada.** W próbie z 21 listopada na publicznych przykładach UZP model obsłużył 747 wywołań bez błędów. Operator potwierdził serwer w Polsce, szyfrowanie tunelu, plan Free bez regionalnego ograniczenia TLS, wyłączony Logpush, pola i rotację logów bramy oraz sposób unieważnienia klucza. Dla obecnej trasy nie można potwierdzić warunku lokalizacji w UE/EOG. Nadal potrzebne są ustalenia o logach dostawcy, kopiach, warunkach dalszego użycia i dane spółki do publikacji.

Do pozostałych prób użyć dokumentu syntetycznego. Zachować wynik, datę, wersję wdrożenia i dowód bez kluczy, treści akt ani nagłówków autoryzacji.

| Co potwierdzić | Jakiego dowodu potrzebuje spółka |
|---|---|
| 1. Przepływ danych i lokalny OCR | Próba ze skanem i tekstowym PDF. Potwierdzić, że zdalny OCR jest wyłączony (`O2J_OCR_BASE` nieustawione), żądania do modelu zawierają tekst i pola formularza, a plik i obrazy stron pozostają na komputerze. Wystarczą nazwy pól, typy danych, typ treści i wynik testu. |
| 2. Kraje, podmioty i dostęp | W obecnej konfiguracji Cloudflare nie gwarantuje miejsca odszyfrowania żądań w UE/EOG. Dla trasy wybranej do oceny zachować dokumentację regionu zakończenia TLS, przetwarzania treści i lokalizacji metadanych. Udokumentować także monitoring, ewentualny eksport i dostęp serwisowy. |
| 3. Zapisy, pamięć podręczna i usuwanie | **Potwierdzone przez operatora:** pola dziennika bramy, wyłączone logowanie treści żądań modelu oraz pamięć podręczna modelu w GPU do wyparcia lub restartu. Brama rotuje wpisy według rozmiaru. Uzupełnić konfigurację rotacji, retencję logów modelu i Cloudflare, zakres kopii, zasady usuwania i zachowanie przy błędzie. Do próby użyć żądania syntetycznego ze znacznikiem. |
| 4. Dalsze użycie danych | **Potwierdzone przez operatora:** telemetria vLLM jest wyłączona, a wagi są ładowane w trybie offline. Zweryfikować ustawienia oraz warunki dostawców pośrednich dotyczące telemetrii, analizy treści, treningu i udostępniania danych. |
| 5. Dostęp jury i jego zakończenie | Próba wykazała odpowiedź z kluczem i HTTP 401 bez klucza. Operator podał sposób odwołania klucza. Przed oceną potwierdzić osobę odpowiedzialną za zgłoszenia, termin wyłączenia dostępu oraz próbę na ostatecznej trasie z hosta jury. |

**Przed publikacją.** Mateusz zaakceptował treść projektu. Spółka uzupełnia rzeczywiste role i podstawy prawne, kontakt, dane dostawców i informacje o ewentualnych transferach na podstawie ustaleń z operatorem oraz stroną przekazującą dane. Jeśli lokalizacja serwera obsługującego dane konkursowe pozostaje nieznana lub wypada poza UE/EOG, spółka uzgadnia odpowiednią konfigurację przed dopuszczeniem ruchu jury. Po weryfikacji uzupełnia pola robocze i publikuje zatwierdzony tekst do końca sekcji „Odpowiedzialność i prawa osób”. Jury otrzymuje adres obowiązującej polityki. UZP wymaga firmowego dostawcy, wskazania zakresu i miejsca przetwarzania w jego polityce, serwerów w UE/EOG oraz klucza testowego. [Wymagania UZP, część 6](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/README.md?plain=1#L160) · [RODO, w szczególności art. 5–6, 12–14, 15–22, 28, 32 i 44–49](https://eur-lex.europa.eu/legal-content/PL/TXT/?uri=CELEX:32016R0679)
