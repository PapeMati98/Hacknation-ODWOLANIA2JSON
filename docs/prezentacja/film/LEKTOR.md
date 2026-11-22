# Film 45 s: tekst dla lektora i specyfikacja nagrań

Film składa się z 7 ujęć: okładki i 6 slajdów prezentacji. Każde ujęcie ma osobne nagranie. Ujęcie trwa tyle co nagranie plus krótki oddech, ale nie mniej niż 5 sekund. Cały film powinien mieć ok. 45 s.

## Tekst do nagrania

Wpisane czasy są orientacyjne, przy spokojnym tempie (ok. 150 słów na minutę). Można mówić trochę szybciej, wolniej nie warto, bo film urośnie ponad 45 s.

| Plik | Ujęcie | Tekst | Cel |
|---|---|---|---|
| `nagranie_0.wav` | Okładka | JSON, ja tu tylko parsuję. Projekt drużyny „Nie wiem, ale wygeneruję” dla Urzędu Zamówień Publicznych. | ≤ 7 s |
| `nagranie_1.wav` | Slajd 1: tytuł | Sprawa przed Krajową Izbą Odwoławczą to kilka plików PDF. Nasza aplikacja sama odczytuje z nich dane, z pomocą polskiego modelu językowego Synaps. | ≤ 9 s |
| `nagranie_2.wav` | Slajd 2: od PDF do JSON | Wgrywasz pliki sprawy, a dla każdego dokumentu dostajesz gotowy plik JSON. Pola niepewne trafiają do sprawdzenia przez człowieka. | ≤ 7,5 s |
| `nagranie_3.wav` | Slajd 3: skuteczność | Na trzydziestu skanach Urzędu wynik F1 przekracza zero przecinek dziewięćdziesiąt dziewięć. | ≤ 5 s |
| `nagranie_4.wav` | Slajd 4: YAML | Nowy rodzaj dokumentu dodajesz jednym plikiem konfiguracyjnym, bez programowania. | ≤ 4,5 s |
| `nagranie_5.wav` | Slajd 5: uruchomienie | Jury uruchamia ocenę całej partii jednym poleceniem. | ≤ 4 s |
| `nagranie_6.wav` | Slajd 6: źródła | Wszystkie składniki są otwarte. JSON, ja tu tylko parsuję. | ≤ 4 s |

### Wymowa

- **JSON**: „dżejson”.
- **PDF**: „pe-de-ef”.
- **F1**: „ef jeden”.
- **0,99**: „zero przecinek dziewięćdziesiąt dziewięć”.
- **Synaps**: „synaps”, jak w biologii.
- **KIO**: w tekście jest pełna nazwa, Krajowa Izba Odwoławcza, więc skrótu się nie czyta.
- **Nazwa drużyny**: „Nie wiem, ale wygeneruję”, z wyraźnym „ę” na końcu.

### Ton

Spokojny, rzeczowy, raczej urzędowy niż reklamowy, z lekkim uśmiechem przy tytule „JSON, ja tu tylko parsuję”. Po każdym zdaniu krótka pauza, bez przeciągania.

## Specyfikacja nagrań

| Parametr | Wymaganie |
|---|---|
| Liczba plików | 7, po jednym na ujęcie, nazwy `nagranie_0` … `nagranie_6` |
| Format | **WAV** (PCM), najlepiej 48 kHz, 16 lub 24 bit, mono. Przyjmę też MP3 ≥ 192 kb/s lub M4A/AAC ≥ 192 kb/s. |
| Cisza | Do 0,2 s na początku i końcu pliku. Odstępy przed i po mowie dodaje skrypt. |
| Głośność | Średnio ok. −16 LUFS, szczyty nie wyżej niż −1 dBFS. Wszystkie pliki w tej samej głośności. |
| Tło | Bez muzyki i efektów. Cicho w tle, bez pogłosu pomieszczenia (najlepiej mówić do mikrofonu słuchawek z bliska, w małym pokoju). |
| Jedno nagranie zamiast siedmiu | Też się nada. Wtedy między ujęciami trzeba zrobić wyraźną pauzę ok. 1 s, a ja potnę nagranie. |

Pliki wrzuć do jednego folderu, np. `docs/prezentacja/film/nagrania/`, albo prześlij w czacie.

## Składanie filmu

Skrypt [`generuj_film.py`](./generuj_film.py) dopasowuje długość każdego ujęcia do nagrania i robi przejścia między slajdami:

```bash
python generuj_film.py okladka.png prezentacja.pdf film.mp4 nagrania/
```

Bez czwartego argumentu skrypt nagrywa tekst syntezatorem macOS (głos Zosia). Wynik: MP4 1920×1080, 30 kl./s, H.264 + AAC, gotowy do wrzucenia na YouTube jako „Listed”.
