# Polityka prywatności API Synapsa

**Projekt z 22 listopada 2026 r.** Dokument opisuje konkursową usługę odczytu pól z dokumentów spraw Krajowej Izby Odwoławczej w aplikacji Odwołania2JSON. Dotyczy konfiguracji z lokalnym OCR i modelem Synaps-PL Small 4B udostępnianym przez API.

## Dostawca i kontakt

Usługę świadczy Synaptivo sp. z o.o., ul. Falista 168/9, 94-115 Łódź, KRS 0001147537. W sprawach dotyczących danych w API, dostępu jury i wniosków osób, których dane dotyczą, kontakt przyjmuje **Mateusz Pietrzak, Prezes Zarządu**, tel. +48 531 936 973. Można także napisać na adres pocztowy spółki. [mateusz.pietrzak@synaptivo.eu](mailto:mateusz.pietrzak@synaptivo.eu)

## Jakie dane przetwarzamy i w jakim celu

- **Dokumenty.** Aplikacja odczytuje PDF lub wykonuje OCR na komputerze oceniającego. Plik i obrazy stron pozostają na tym komputerze. Do API trafiają odczytany tekst, instrukcja, nazwy pól i wcześniej odczytane wartości. W przypadku krótkiego pisma żądanie może zawierać cały jego tekst.
- **Odczyt pól.** Model zwraca proponowane wartości. Zależnie od dokumentu mogą to być m.in. dane stron, pełnomocników, podpisujących i płatników, dane adresowe i identyfikacyjne, numery rachunków, daty i kwoty. Aplikacja sprawdza odpowiedź i zapisuje wynik JSON oraz ślad odczytu w środowisku oceniającego. Oceniający może sprawdzić wynik w dokumencie. Usługa nie wydaje rozstrzygnięć w sprawach odwoławczych.
- **Dostęp i kontakt.** Klucz testowy służy do uwierzytelniania wywołań. Dane techniczne służą zabezpieczeniu dostępu i wykrywaniu awarii. Jeżeli ktoś pisze do spółki, Synaptivo korzysta z przekazanych danych kontaktowych, aby obsłużyć jego sprawę.

## Gdzie odbywa się przetwarzanie

Model działa w Polsce. Brama HTTPS odszyfrowuje żądania w sieci globalnej. Dostawca bramy przesyła je następnie zaszyfrowanym tunelem do serwera Synaptivo.

## Logi, przechowywanie i uczenie modelu

Dziennik bramy Synaptivo zapisuje czas, ścieżkę wywołania, status, skrócony identyfikator klucza, czas obsługi oraz liczbę tokenów. Przy błędach może zapisać rozmiar żądania lub krótką przyczynę odrzucenia, w tym nazwę nierozpoznanego parametru. Przy prawidłowym wywołaniu dziennik pomija treść dokumentu, odpowiedź, pełny klucz i adres IP klienta. Wpisy rotują po osiągnięciu limitu rozmiaru. Daje to zmienny czas przechowywania. Okres przechowywania logów u pośrednika i zakres kopii zapasowych pozostają do potwierdzenia.

Serwer modelu ma wyłączone rejestrowanie treści żądań. Fragmenty przetworzonego kontekstu pozostają w pamięci roboczej karty graficznej do ich zastąpienia lub restartu procesu. Synaptivo wykorzystuje treść i odpowiedzi do realizacji żądania i nie używa ich do treningu ani dostrajania modeli. Za czas przechowywania wejściowych PDF-ów, wyników i śladów zapisanych przez aplikację odpowiada podmiot zarządzający komputerem oceniającego.

## Role i prawa osób

Synaptivo obsługuje własne klucze, bezpieczeństwo usługi i korespondencję. Dla akt zawierających dane osobowe należy przed ich przekazaniem ustalić z podmiotem przekazującym dokumenty, kto określa cel i podstawę przetwarzania oraz na jakich warunkach spółka wykonuje ekstrakcję. Na dzień tej wersji uzgodnienia dotyczące rzeczywistych akt pozostają otwarte.

Osoba, której dane dotyczą, może wystąpić do właściwego administratora o dostęp do danych, ich sprostowanie, usunięcie lub ograniczenie przetwarzania. W zależności od podstawy przetwarzania może jej również przysługiwać prawo do sprzeciwu lub przenoszenia danych. Wniosek można skierować do wskazanego powyżej kontaktu Synaptivo. Gdy sprawa dotyczy danych przetwarzanych na rzecz innego administratora, spółka pomoże przekazać mu wniosek. Osoba może także wnieść skargę do Prezesa Urzędu Ochrony Danych Osobowych. [Prawa osób w RODO](https://eur-lex.europa.eu/legal-content/PL/TXT/?uri=CELEX:32016R0679) · [Składanie skarg do Prezesa UODO](https://uodo.gov.pl/pl/526/2464)
