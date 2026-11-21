# Trudne dane testowe dla Odwołania2JSON

Przygotowane 21.11.2026 do testowania programu z repo `PapeMati98/Hacknation-ODWOLANIA2JSON`. W wygenerowanych dokumentach dane osobowe i numery są fikcyjne. Syntetyczne identyfikatory mają prefiks 999 i poprawne sumy kontrolne, tak jak w przykładach UZP. Zestaw zawiera również opublikowane orzeczenia KIO.

Kolejne syntetyczne sprawy dodawaj w osobnych podfolderach. PDF-y umieść w [syntetyczne/input](./syntetyczne/input), a sprawdzone wzorce JSON o tej samej nazwie w [syntetyczne/gold](./syntetyczne/gold), pod identyczną nazwą sprawy. Publiczne orzeczenia KIO mają [osobny katalog](./kio-orzeczenia) i [spis źródeł](./kio-orzeczenia/lista.csv).

## `syntetyczne/`: 12 spraw z gold JSON

```
syntetyczne/input/synt_XX/*.pdf    -> wejście programu (input/<sprawa>/*.pdf)
syntetyczne/gold/synt_XX/*.json    -> oczekiwany wynik w formacie organizatora
syntetyczne/gold/synt_XX/opis.json -> rodzaj sprawy, poziom, celowe trudności
```

| Sprawa | Rodzaj | Poziom | Czego dotyczy test |
|---|---|---|---|
| synt_01 | tekst | zwykła | odrzucenie oferty (powód 1), data słownie |
| synt_02 | tekst | zwykła | wybór oferty (2), numer TED `2026/S 145-890513` → `890513-2026` |
| synt_03 | tekst | zwykła | modyfikacja SWZ (5), dwóch zamawiających (lider prowadzący); **+ wezwanie do wyjaśnień (spoza klas)** |
| synt_04 | tekst | trudna | **powód 12** (projektowane postanowienia umowy), konsorcjum, pełnomocnicy w bierniku („Annę Kowalską”), nagłówek kancelarii, brak daty w nagłówku (data tylko na końcu → `data` i `miejscowosc` = null), Times; **+ przystąpienie do postępowania odwoławczego (spoza klas, bardzo podobne do odwołania)** |
| synt_05 | tekst | trudna | OPZ (11), strony w tabeli, NIP z myślnikami, BZP ze spacją i korektą `/01`, odwołujący jako osoba fizyczna (CEIDG, bez KRS), zamawiający bez KRS, kwota `10.000,00 PLN`, rachunki ze spacjami; **+ faktura kancelarii i prawdziwe postanowienie KIO (spoza klas)** |
| synt_06 | tekst | trudna | zaniechanie odrzucenia (7), zarzut z datą czynności dopiero na 2. stronie, PESEL pełnomocnika, przelew bez numeru transakcji, długi tytuł przelewu |
| synt_07 | skan | zwykła | wykluczenie (3); **+ prawdziwe postanowienie KIO jako skan (spoza klas)** |
| synt_08 | skan | zwykła | publikacja SWZ (4), TED, daty słownie |
| synt_09 | skan | zwykła | unieważnienie (9); **+ zawiadomienie o wyborze oferty (spoza klas)** |
| synt_10 | skan | trudna | odpowiedzi do SWZ (6), konsorcjum, odmiana nazwisk, pieczątka wpływu na dacie w nagłówku, BZP ze spacją |
| synt_11 | skan | trudna | zaniechanie unieważnienia (10), dwóch zamawiających, TED, tabela, Times, kwota w PLN; **+ odpowiedź na odwołanie (spoza klas)** |
| synt_12 | skan | trudna | zaniechanie wykluczenia (8), osoba fizyczna, data tylko na końcu, zarzut na 2. stronie, PESEL, bez numeru transakcji, NIP z myślnikami, pieczątka |

- **Skany** (synt_07–12) są obrazem bez warstwy tekstowej i mają średnią wyrazistość: 150 dpi, szarość, obrót do ±1,4°, lekkie rozmycie, szum, JPEG o jakości 45–60.
- **Sprawy zwykłe** (01–03, 07–09) mają poprawne, kompletne dane, z których powinien powstać normalny JSON.
- **Dokumenty spoza klas** mają gold `{}`, czyli pusty JSON, zgodnie z wymogiem UZP.

Ocena: wynik programu wrzucić do `output/` i porównać z `gold/`, np. narzędziem `tools/score.py` z repo Mateusza albo `tools/diff_pred.py`.

### Konwencje gold (wzięte z przykładów UZP)
- Konsorcjum: w `Odwolujacy` jest tylko Lider, a w pełnomocnictwie `mocodawca` ma obu członków.
- Pełnomocnik w odwołaniu: pierwszy wymieniony, imię i nazwisko w mianowniku, `nazwa` to kancelaria, `mail` to e-mail z adresu do korespondencji.
- Dwóch zamawiających: `prowadzacy_postepowanie` 1 dla lidera i 0 dla partnera; przy jednym zamawiającym `null`.
- Brak daty w nagłówku: `data` i `miejscowosc` = `null` (jak w `przyklad_48` UZP).

### Ponowne wygenerowanie
```bash
cd eval/trudne
python generator/generuj.py --out syntetyczne --kio kio-orzeczenia --seed 2026
```
Wymaga: `reportlab<4.3` (dla Pythona 3.9; na 3.10+ działa każda wersja), `pypdfium2`, `pillow`, `numpy`. Fonty Arial i Times są brane z macOS (`/System/Library/Fonts/Supplemental`). Inny `--seed` daje nowe dane.

## `kio-orzeczenia/`: 22 prawdziwe orzeczenia KIO
Pobrane z orzeczenia.uzp.gov.pl (spis i linki w `lista.csv`). Są to dokumenty spoza klas, więc oczekiwany wynik to `{}`. Używają słownictwa odwołań, więc dobrze testują, czy klasyfikator nie myli ich z odwołaniem.

Schematy i konwencje gold wzięto z publicznego repo organizatora (`Urzad-Zamowien-Publicznych/hacknation-2026`).
