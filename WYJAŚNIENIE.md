# Jak działa nowy system nazewnictwa

## Przepływ danych:

1. **Pobierz obraz produktu** (z URL w CSV)

2. **Parsuj dolną tabelkę** (`parse_block_table`)
   - Wycina dolne 35% obrazu (tabelka z blokami)
   - Używa OCR do wykrycia liczb ("x24", "x60" itp.)
   - Analizuje kolory ikon bloków
   - Zwraca: `{'grass': 1200, 'water': 450, 'stone': 300, ...}`

3. **Analizuj scenę 3D** (`analyze_built_structure`)
   - Wycina górne 60% obrazu (scena 3D, bez tabelki)
   - Dzieli na 3 regiony: góra, środek, dół
   - Liczy kolory w każdym regionie
   - Wykrywa cechy:
     - `has_water_flow`: niebieski w górze/środku → wodospad/rzeka
     - `has_building`: szary/brązowy w środku → dom/zamek
     - `has_trees`: zielony w górze → las/drzewa
     - `has_landscape`: zieleń+brąz w dole → wzgórza/krajobraz
     - `has_lava`: czerwony → lawa/ogień
     - `has_platforms`: warstwy kolorów → platformy/tarasy

4. **Generuj nazwę** (`generate_name_from_structure`)
   - Priorytet scenariuszy:
     1. **Woda + drzewa** → "Leśny Wodospad"
     2. **Woda + budynek** → "Dom nad Rzeką"
     3. **Budynek + drzewa** → "Chatka w Lesie"
     4. **Budynek + kamień** → "Kamienny Zamek"
     5. **Budynek** → "Drewniana Wieża"
     6. **Drzewa + platformy** → "Tarasowy Gaj"
     7. **Drzewa** → "Gaj Drzew"
     8. **Krajobraz + platformy** → "Wzgórza Terasowe"
     9. **Lawa** → "Ognista Jaskinia"
     10. Fallback → "Kreatywny Zestaw"

## Przykłady z CSV:

- `T059-128PCS` → **Leśny Wodospad 128PCS** (wykryto: woda + drzewa)
- `T086-200PCS` → **Chatka w Lesie 200PCS** (wykryto: budynek + drzewa)
- `T110-132PCS` → **Dom nad Rzeką 132PCS** (wykryto: woda + budynek)
- `RM-100PCS` → **Kamienny Zamek 100PCS** (wykryto: budynek + kamień)
- `T050-80PCS` → **Drewniana Wieża 80PCS** (wykryto: budynek bez kamienia)

## Kluczowe zmiany:

✅ **Używa tabelki** do identyfikacji bloków (ikony + liczby)
✅ **Patrzy na scenę 3D** aby określić CO zbudowano
✅ **Deterministyczne** (ten sam obraz = ta sama nazwa)
✅ **Gramatycznie poprawne** polskie nazwy
✅ **Opisowe** (nazwa mówi co można zbudować)
