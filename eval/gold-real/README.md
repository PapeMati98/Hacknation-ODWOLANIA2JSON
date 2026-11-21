# Złoty zestaw na realnych dokumentach (tylko do OCENY)

Etykiety przygotował Claude (model z subskrypcji). Zgodnie z zasadą właściciela służą **wyłącznie do pomiaru F1**, nie do treningu.
Trening: gold JSON organizatora (`dane/uzp-hacknation-2026/dane`) + etykiety od otwartego nauczyciela (lokalny Qwen3.8-27B).

Struktura jak w kontrakcie UZP: `gold-real/<sprawa>/<nazwa PDF>.json`; źródłowe PDF-y leżą w repo UZP / `input/`.

## case1 — `szablon-aplikacja/input/case1/przyklad odwolanie.pdf` (skan, 7 str., bez warstwy tekstowej)
Oceniono strony 1–3 (2026-11-21).

| Pole | Wartość | Pewność | Uwagi |
|---|---|---|---|
| data / miejscowosc | 2025-06-16 / Warszawa | wysoka | „Warszawa, dnia 16 czerwca 2025 r.” |
| czynnosc_dzien | 2025-06-10 | wysoka | „Zamawiający zamieścił ogłoszenie wraz z dokumentami w dniu 10 czerwca 2025 r.” |
| czynnosc_powod_id | 4 | **średnia** | Odwołanie „wobec treści dokumentów zamówienia – SWZ”, ale naruszenie „w zakresie Części II SWZ – OPZ” i żądanie modyfikacji OPZ. Alternatywa: 11. Pytanie do mentorów. |
| Odwołujący.nazwa | BIOARCUS Spółka z ograniczoną odpowiedzialnością | średnia | Nazwa w nagłówku zakryta, ale jawna w treści („w imieniu wykonawcy „BIOARCUS” Spółka z o.o.”). Normalizacja formy prawnej (Sp. z o.o. vs pełna) nieznana. |
| KRS, NIP, REGON, pełnomocnik, e-mail | null | wysoka | **Zakryte czarnymi prostokątami (anonimizacja).** |
| przez-pelnomocnika | 1 | wysoka | „reprezentowany przez radcę prawnego …” |
| numer_bzp | 2025/BZP00270698 | wysoka | w dokumencie ze spacją „2025/BZP 00270698” |
| numer_postepowania | RZP.27.29.2025.KD | wysoka | |
| numer_ted | null | wysoka | brak |

## Wnioski dla architektury
1. **Realne dokumenty są zanonimizowane** (czarne prostokąty). Model musi zwracać `null` dla zakrytych pól, bez halucynacji.
2. **Syntetyki są szablonowe**: powód czynności wynika z jednego zdania szablonu („Zamawiający w dniu X opublikował SWZ / udostępnił OPZ”); treść zarzutów dla id 4 i 11 jest identyczna. Fine-tuning tylko na syntetykach nauczy szablonu, nie rozumienia → ryzyko spadku F1 na realnych sprawach.
3. Realne skany: czysty druk, ~1737×2456 px przy skali 1,4 — szybki OCR CPU powinien wystarczyć.
