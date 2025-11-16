import csv, re, sys, io, requests, os
from typing import List, Tuple, Optional
try:
    from PIL import Image
except ImportError:
    Image = None

# AVIF/HEIF support
try:
    import pillow_avif  # noqa: F401
except Exception:
    try:
        from pillow_heif import register_heif_opener  # type: ignore
        register_heif_opener()
    except Exception:
        pass

# OCR (optional)
try:
    import pytesseract
except ImportError:
    pytesseract = None


def parse_block_table(img: Image.Image) -> dict:
    """Parsuje dolną tabelkę na obrazie - wyciąga listę bloków (ikony + liczby)."""
    w, h = img.size
    table_region = img.crop((0, int(h * 0.65), w, h))
    
    blocks_found = {}
    
    # OCR dla liczb przy blokach (np. "x24", "x60")
    if pytesseract:
        try:
            text = pytesseract.image_to_string(table_region)
            matches = re.findall(r'x(\d+)', text)
            if matches:
                blocks_found['total_pieces'] = sum(int(m) for m in matches)
        except Exception:
            pass
    
    # Analiza kolorów ikon bloków
    small_table = table_region.resize((200, 50))
    pixels = list(small_table.getdata())
    
    color_counts = {}
    for p in pixels:
        if p[0] > 220 and p[1] > 200 and p[2] < 180:  # beżowe tło tabelki
            continue
        key = (p[0]//40, p[1]//40, p[2]//40)
        color_counts[key] = color_counts.get(key, 0) + 1
    
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    
    for (r, g, b), count in sorted_colors:
        if g > r and g > b:  # zielony
            blocks_found['grass'] = blocks_found.get('grass', 0) + count
        elif b > r and b > g:  # niebieski
            blocks_found['water'] = blocks_found.get('water', 0) + count
        elif r > 3 and g > 1 and b < 2:  # brązowy
            blocks_found['dirt_or_wood'] = blocks_found.get('dirt_or_wood', 0) + count
        elif abs(r-g) < 1 and abs(g-b) < 1:  # szary
            blocks_found['stone'] = blocks_found.get('stone', 0) + count
        elif r > g + 1 and r > b + 1:  # czerwony
            blocks_found['tnt_or_lava'] = blocks_found.get('tnt_or_lava', 0) + count
    
    return blocks_found


def analyze_built_structure(img: Image.Image) -> dict:
    """Analizuje CO KONKRETNIE jest zbudowane na obrazie - rozpoznaje kształty i struktury."""
    w, h = img.size
    scene = img.crop((int(w*0.08), int(h*0.05), int(w*0.92), int(h*0.62)))
    
    # Większa rozdzielczość dla lepszego rozpoznawania kształtów
    analysis_img = scene.convert("RGB").resize((150, 100))
    pixels = list(analysis_img.getdata())
    
    # Konwertuj na macierz 2D dla analizy kształtów
    sw, sh = analysis_img.size
    pixel_matrix = []
    for y in range(sh):
        row = []
        for x in range(sw):
            p = pixels[y * sw + x]
            row.append(p)
        pixel_matrix.append(row)
    
    structure = {}
    
    # === WYKRYWANIE KONKRETNYCH BUDOWLI ===
    
    # Wykryj DOM/CHATĘ - prostokątne struktury z dachem
    house_score = detect_house_shape(pixel_matrix)
    if house_score > 0.3:
        structure['building_type'] = 'house'
        structure['house_complexity'] = house_score
    
    # Wykryj ZAMEK/WIEŻĘ - wysokie pionowe struktury
    tower_score = detect_tower_shape(pixel_matrix)
    if tower_score > 0.4:
        structure['building_type'] = 'tower'
        structure['tower_height'] = tower_score
    
    # Wykryj MOST - poziome struktury nad wodą/przepaścią
    bridge_score = detect_bridge_shape(pixel_matrix)
    if bridge_score > 0.3:
        structure['has_bridge'] = True
        structure['bridge_length'] = bridge_score
    
    # Wykryj FARMĘ - regularne pola z roślinami
    farm_score = detect_farm_pattern(pixel_matrix)
    if farm_score > 0.25:
        structure['has_farm'] = True
        structure['farm_size'] = farm_score
    
    # Wykryj KOPALNIĘ - pionowe szyby/tunele
    mine_score = detect_mine_structure(pixel_matrix)
    if mine_score > 0.3:
        structure['has_mine'] = True
        structure['mine_depth'] = mine_score
    
    # Wykryj WODOSPAD - pionowy przepływ wody
    waterfall_score = detect_waterfall(pixel_matrix)
    if waterfall_score > 0.4:
        structure['has_waterfall'] = True
        structure['waterfall_height'] = waterfall_score
    
    # Wykryj LAS/DRZEWA - skupiska zieleni z "koronami"
    forest_score = detect_forest_pattern(pixel_matrix)
    if forest_score > 0.3:
        structure['has_forest'] = True
        structure['forest_density'] = forest_score
    
    # Wykryj JEZIORO - duże skupisko niebieskiego
    lake_score = detect_lake_shape(pixel_matrix)
    if lake_score > 0.25:
        structure['has_lake'] = True
        structure['lake_size'] = lake_score
    
    # Wykryj GÓRY/WZGÓRZA - warstwy o różnych wysokościach
    mountain_score = detect_mountain_layers(pixel_matrix)
    if mountain_score > 0.3:
        structure['has_mountains'] = True
        structure['mountain_height'] = mountain_score
    
    return structure

def detect_house_shape(matrix):
    """Wykrywa kształt domu - prostokąty z trójkątnym dachem."""
    h, w = len(matrix), len(matrix[0])
    score = 0.0
    
    # Szukaj prostokątnych struktur w środkowej części
    for y in range(h//4, 3*h//4):
        for x in range(w//4, 3*w//4):
            if is_building_block(matrix[y][x]):  # brązowy/szary blok
                # Sprawdź czy to część prostokątnej struktury
                if (x + 3 < w and y + 3 < h and
                    is_building_block(matrix[y][x+3]) and
                    is_building_block(matrix[y+3][x])):
                    score += 0.1
                    
                    # Bonus za "dach" - ciemniejsze bloki nad budynkiem
                    if y > 2 and is_roof_block(matrix[y-1][x]):
                        score += 0.15
    
    return min(score, 1.0)

def detect_tower_shape(matrix):
    """Wykrywa wysokie pionowe struktury."""
    h, w = len(matrix), len(matrix[0])
    score = 0.0
    
    for x in range(w//4, 3*w//4):
        vertical_blocks = 0
        for y in range(h//4, 3*h//4):
            if is_building_block(matrix[y][x]):
                vertical_blocks += 1
        
        if vertical_blocks > h//3:  # Wysoka pionowa struktura
            score += 0.2
    
    return min(score, 1.0)

def detect_bridge_shape(matrix):
    """Wykrywa mosty - poziome struktury."""
    h, w = len(matrix), len(matrix[0])
    score = 0.0
    
    # Szukaj poziomych linii bloków w środkowej wysokości
    for y in range(h//3, 2*h//3):
        horizontal_blocks = 0
        for x in range(w//4, 3*w//4):
            if is_building_block(matrix[y][x]):
                horizontal_blocks += 1
        
        if horizontal_blocks > w//3:  # Długa pozioma struktura
            # Sprawdź czy pod mostem jest przestrzeń/woda
            space_below = 0
            if y + 2 < h:
                for x in range(w//4, 3*w//4):
                    if is_water_block(matrix[y+2][x]) or is_air_block(matrix[y+2][x]):
                        space_below += 1
            
            if space_below > w//6:
                score += 0.3
    
    return min(score, 1.0)

def detect_farm_pattern(matrix):
    """Wykrywa regularne pola uprawne."""
    h, w = len(matrix), len(matrix[0])
    score = 0.0
    
    # Szukaj regularnych wzorów zieleni (rośliny)
    for y in range(h//2, h):  # Dolna część (poziom gruntu)
        green_patches = 0
        brown_patches = 0
        
        for x in range(w):
            if is_plant_block(matrix[y][x]):
                green_patches += 1
            elif is_dirt_block(matrix[y][x]):
                brown_patches += 1
        
        # Farma = mieszanka zieleni (rośliny) i brązu (ziemia)
        if green_patches > w//6 and brown_patches > w//6:
            score += 0.2
    
    return min(score, 1.0)

def detect_mine_structure(matrix):
    """Wykrywa struktury kopalni - tunele, szyby."""
    h, w = len(matrix), len(matrix[0])
    score = 0.0
    
    # Szukaj ciemnych "otworów" - skupisk czarnych/ciemnych bloków
    for y in range(h//3, h):
        for x in range(w//4, 3*w//4):
            if is_dark_block(matrix[y][x]):
                # Sprawdź czy to część większego ciemnego obszaru
                dark_neighbors = 0
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if (0 <= y+dy < h and 0 <= x+dx < w and
                            is_dark_block(matrix[y+dy][x+dx])):
                            dark_neighbors += 1
                
                if dark_neighbors >= 4:  # Skupisko ciemnych bloków
                    score += 0.1
    
    return min(score, 1.0)

def detect_waterfall(matrix):
    """Wykrywa wodospady - pionowe przepływy wody."""
    h, w = len(matrix), len(matrix[0])
    score = 0.0
    
    for x in range(w//4, 3*w//4):
        water_column = 0
        for y in range(h//4, 3*h//4):
            if is_water_block(matrix[y][x]):
                water_column += 1
        
        if water_column > h//4:  # Długa pionowa linia wody
            score += 0.3
            
            # Bonus jeśli woda "spada" z góry na dół
            if (water_column > h//3 and
                is_water_block(matrix[h//4][x]) and
                is_water_block(matrix[2*h//3][x])):
                score += 0.2
    
    return min(score, 1.0)

def detect_forest_pattern(matrix):
    """Wykrywa lasy - skupiska zielonych "koron" drzew."""
    h, w = len(matrix), len(matrix[0])
    score = 0.0
    
    # Szukaj zielonych skupisk w górnej części (korony drzew)
    for y in range(h//4, h//2):
        for x in range(w//4, 3*w//4):
            if is_leaf_block(matrix[y][x]):
                # Sprawdź czy pod zielenią jest "pień"
                trunk_below = False
                for dy in range(1, 4):
                    if y+dy < h and is_wood_block(matrix[y+dy][x]):
                        trunk_below = True
                        break
                
                if trunk_below:
                    score += 0.1
    
    return min(score, 1.0)

def detect_lake_shape(matrix):
    """Wykrywa jeziora - duże skupiska wody."""
    h, w = len(matrix), len(matrix[0])
    water_blocks = 0
    
    for y in range(h):
        for x in range(w):
            if is_water_block(matrix[y][x]):
                water_blocks += 1
    
    return min(water_blocks / (w * h * 0.15), 1.0)  # % wody w obrazie

def detect_mountain_layers(matrix):
    """Wykrywa góry - warstwy bloków na różnych wysokościach."""
    h, w = len(matrix), len(matrix[0])
    score = 0.0
    
    # Analizuj profil wysokości
    for x in range(w):
        height_changes = 0
        prev_solid = False
        
        for y in range(h):
            current_solid = is_solid_block(matrix[y][x])
            
            if current_solid != prev_solid:
                height_changes += 1
            prev_solid = current_solid
        
        if height_changes > 3:  # Wiele zmian wysokości = góry
            score += 0.1
    
    return min(score / 2.0, 1.0)

# === POMOCNICZE FUNKCJE ROZPOZNAWANIA BLOKÓW ===

def is_building_block(pixel):
    """Bloki budowlane - szare (kamień), brązowe (drewno)."""
    r, g, b = pixel
    # Szary kamień
    if abs(r-g) < 30 and abs(g-b) < 30 and 80 < r < 160:
        return True
    # Brązowe drewno
    if r > g > b and r > 80 and g > 50:
        return True
    return False

def is_roof_block(pixel):
    """Bloki dachu - ciemniejsze odcienie."""
    r, g, b = pixel
    return (r + g + b) < 200 and not is_water_block(pixel)

def is_water_block(pixel):
    """Woda - niebieski."""
    r, g, b = pixel
    return b > r + 20 and b > g + 10 and b > 100

def is_plant_block(pixel):
    """Rośliny - jasna zieleń."""
    r, g, b = pixel
    return g > r + 15 and g > b + 10 and g > 80

def is_dirt_block(pixel):
    """Ziemia - brązowy."""
    r, g, b = pixel
    return r > b + 15 and abs(r - g) < 40 and g > b and r > 60

def is_wood_block(pixel):
    """Drewno - brązowy pień."""
    r, g, b = pixel
    return r > g > b and 60 < r < 150 and g > 40

def is_leaf_block(pixel):
    """Liście - ciemna zieleń."""
    r, g, b = pixel
    return g > r + 10 and g > b + 5 and 50 < g < 120

def is_dark_block(pixel):
    """Ciemne bloki - kopalnie, jaskinie."""
    r, g, b = pixel
    return (r + g + b) < 120

def is_air_block(pixel):
    """Powietrze - jasne kolory."""
    r, g, b = pixel
    return (r + g + b) > 600

def is_solid_block(pixel):
    """Stałe bloki - nie powietrze, nie woda."""
    return not is_air_block(pixel) and not is_water_block(pixel)


# Globalny licznik dla unikalnych nazw
name_counter = {}

def generate_unique_name_from_structure(structure: dict, blocks_info: dict, original_sku: str) -> str:
    """Generuje UNIKALNĄ nazwę na podstawie wykrytej struktury + SKU."""
    global name_counter
    
    base_name = determine_base_name(structure, blocks_info)
    
    # Jeśli nazwa już była użyta, dodaj unikalny wariant
    if base_name in name_counter:
        name_counter[base_name] += 1
        variant_num = name_counter[base_name]
        
        # Utwórz unikalną nazwę na podstawie SKU lub licznika
        if 'T0' in original_sku:
            unique_name = create_themed_variant(base_name, original_sku)
        elif 'RM' in original_sku:
            unique_name = create_railway_variant(base_name, variant_num)
        elif 'SJJ' in original_sku:
            unique_name = create_creative_variant(base_name, variant_num)
        else:
            unique_name = create_numbered_variant(base_name, variant_num)
    else:
        name_counter[base_name] = 1
        unique_name = base_name
    
    return unique_name

def determine_base_name(structure: dict, blocks_info: dict) -> str:
    """Określa podstawową nazwę na podstawie wykrytej struktury."""
    
    # === KONKRETNE BUDOWLE ===
    building_type = structure.get('building_type', '')
    
    if building_type == 'house':
        complexity = structure.get('house_complexity', 0)
        if complexity > 0.7:
            return "Wielka Rezydencja"
        elif complexity > 0.5:
            return "Rodzinny Dom"
        else:
            return "Przytulna Chatka"
    
    elif building_type == 'tower':
        height = structure.get('tower_height', 0)
        if height > 0.8:
            return "Strażnicza Wieża"
        elif height > 0.6:
            return "Obronna Wieża"
        else:
            return "Kamienna Wieża"
    
    # === SPECJALISTYCZNE KONSTRUKCJE ===
    if structure.get('has_bridge'):
        length = structure.get('bridge_length', 0)
        if length > 0.7:
            return "Wielki Most"
        else:
            return "Kamiennym Most"
    
    if structure.get('has_farm'):
        size = structure.get('farm_size', 0)
        if size > 0.6:
            return "Rozległa Farma"
        else:
            return "Rolnicza Osada"
    
    if structure.get('has_mine'):
        depth = structure.get('mine_depth', 0)
        if depth > 0.6:
            return "Głęboka Kopalnia"
        else:
            return "Górnicza Szybka"
    
    if structure.get('has_waterfall'):
        height = structure.get('waterfall_height', 0)
        if height > 0.7:
            return "Majestatyczny Wodospad"
        else:
            return "Leśny Wodospad"
    
    # === NATURALNE KRAJOBRAZY ===
    if structure.get('has_forest'):
        density = structure.get('forest_density', 0)
        if density > 0.6:
            return "Gęsty Las"
        else:
            return "Zielony Gaj"
    
    if structure.get('has_lake'):
        size = structure.get('lake_size', 0)
        if size > 0.5:
            return "Błękitne Jezioro"
        else:
            return "Górski Staw"
    
    if structure.get('has_mountains'):
        height = structure.get('mountain_height', 0)
        if height > 0.6:
            return "Wysokie Szczyty"
        else:
            return "Skaliste Wzgórza"
    
    # === KOMBINACJE ===
    if structure.get('has_waterfall') and structure.get('has_forest'):
        return "Leśna Dolina"
    
    if structure.get('building_type') and structure.get('has_forest'):
        return "Leśna Osada"
    
    if structure.get('has_lake') and structure.get('has_mountains'):
        return "Alpejska Kraina"
    
    # === FALLBACK ===
    return "Kreatywna Budowa"

def create_themed_variant(base_name: str, sku: str) -> str:
    """Tworzy wariant tematyczny na podstawie SKU."""
    theme_map = {
        "T059": "Wschodnią",
        "T086": "Zachodnią", 
        "T065": "Północną",
        "T110": "Południową",
        "T111": "Centralną",
        "T058": "Górską",
        "T080": "Nadmorską",
        "T043": "Pustynną",
        "T038": "Śnieżną",
        "T009": "Tropikalną",
        "T050": "Starożytną",
        "T027": "Magiczną"
    }
    
    for code, theme in theme_map.items():
        if code in sku:
            return f"{theme} {base_name}"
    
    return f"Tajemniczą {base_name}"

def create_railway_variant(base_name: str, variant_num: int) -> str:
    """Tworzy wariant kolejowy."""
    railway_themes = [
        f"Kolejową {base_name}",
        f"Dworcową {base_name}",
        f"Mechaniczną {base_name}",
        f"Przemysłową {base_name}",
        f"Transportową {base_name}"
    ]
    return railway_themes[variant_num % len(railway_themes)]

def create_creative_variant(base_name: str, variant_num: int) -> str:
    """Tworzy wariant kreatywny."""
    creative_themes = [
        f"Artystyczną {base_name}",
        f"Kolorową {base_name}",
        f"Designerską {base_name}",
        f"Stylową {base_name}",
        f"Elegancką {base_name}"
    ]
    return creative_themes[variant_num % len(creative_themes)]

def create_numbered_variant(base_name: str, variant_num: int) -> str:
    """Tworzy wariant numerowany."""
    size_variants = [
        f"Małą {base_name}",
        f"Średnią {base_name}",
        f"Dużą {base_name}",
        f"Ogromną {base_name}",
        f"Gigantyczną {base_name}"
    ]
    
    if variant_num <= len(size_variants):
        return size_variants[variant_num - 1]
    else:
        return f"{base_name} nr {variant_num}"


def classify_scene_top_k(img: Image.Image, k: int = 3, original_sku: str = "") -> List[Tuple[str, float]]:
    """Generuje unikalne nazwy na podstawie rzeczywistej analizy sceny."""
    # 1. Parsuj tabelkę (pomocniczo)
    blocks_info = parse_block_table(img)
    
    # 2. DOKŁADNA analiza sceny - rozpoznaj kształty i struktury
    structure = analyze_built_structure(img)
    
    # 3. Generuj UNIKALNĄ nazwę
    primary = generate_unique_name_from_structure(structure, blocks_info, original_sku)
    
    # Oblicz pewność klasyfikacji
    confidence = calculate_detection_confidence(structure)
    
    names = [(primary, confidence)]
    
    # Generuj alternatywne nazwy tylko jeśli potrzeba
    if k > 1:
        alt_name = generate_alternative_name(structure, blocks_info, original_sku)
        if alt_name != primary:
            names.append((alt_name, confidence - 0.5))
    
    if k > 2:
        generic_name = f"Zestaw {len(blocks_info)} Elementów"
        names.append((generic_name, 2.0))
    
    return names[:k]

def calculate_detection_confidence(structure: dict) -> float:
    """Oblicza pewność detekcji na podstawie wykrytych cech."""
    confidence = 3.0
    
    # Wysokie wyniki za konkretne budowle
    if structure.get('building_type'):
        confidence += 2.0
    
    if structure.get('has_waterfall'):
        confidence += 1.5
        
    if structure.get('has_bridge'):
        confidence += 1.5
        
    if structure.get('has_farm'):
        confidence += 1.2
        
    if structure.get('has_mine'):
        confidence += 1.0
    
    # Średnie wyniki za krajobrazy
    if structure.get('has_forest'):
        confidence += 0.8
        
    if structure.get('has_lake'):
        confidence += 0.6
        
    if structure.get('has_mountains'):
        confidence += 0.5
    
    return min(confidence, 8.0)

def generate_alternative_name(structure: dict, blocks_info: dict, sku: str) -> str:
    """Generuje alternatywną nazwę."""
    # Użyj bardziej ogólnego opisu
    if structure.get('building_type') == 'house':
        return "Mieszkalna Budowa"
    elif structure.get('building_type') == 'tower':
        return "Obronna Konstrukcja" 
    elif structure.get('has_waterfall'):
        return "Wodna Atrakcja"
    elif structure.get('has_farm'):
        return "Rolnicza Przestrzeń"
    elif structure.get('has_forest'):
        return "Naturalna Sceneria"
    else:
        return "Architektoniczny Projekt"


def extract_piece_count(text: str) -> Optional[int]:
    """Wyciąga liczbę PCS z tekstu."""
    match = re.search(r'(\d+)\s*PCS', text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def build_new_name_pl(name: str, pcs: Optional[int]) -> str:
    """Buduje pełną nazwę: {nazwa} {liczba}PCS."""
    if pcs:
        return f"{name} {pcs}PCS"
    return name


def fetch_image(url: str) -> Optional[Image.Image]:
    """Pobiera obraz z URL lub otwiera lokalny plik."""
    if not Image:
        print("Brak PIL/Pillow.", file=sys.stderr)
        return None
    
    # Lokalny plik
    if os.path.exists(url):
        try:
            return Image.open(url)
        except Exception as e:
            print(f"Błąd otwierania {url}: {e}", file=sys.stderr)
            return None
    
    # URL
    headers = {'User-Agent': 'Mozilla/5.0'}
    for attempt in range(2):
        try:
            resp = requests.get(url.strip(), timeout=15, headers=headers)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content))
        except Exception as e:
            if attempt == 0:
                continue
            print(f"Błąd pobierania {url}: {e}", file=sys.stderr)
            return None
    return None


def process_csv(input_path: str, output_path: Optional[str] = None):
    """Przetwarza CSV: pobiera obrazy, generuje nazwy, zapisuje wynik."""
    if not output_path:
        base = os.path.splitext(input_path)[0]
        output_path = f"{base}_renamed.csv"
    
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    
    if not rows:
        print("Plik CSV jest pusty.", file=sys.stderr)
        return
    
    header = rows[0]
    
    # Znajdź kolumny
    try:
        option1_idx = header.index("Option1 value")
    except ValueError:
        print("Brak kolumny 'Option1 value'.", file=sys.stderr)
        return
    
    image_candidates = {"Variant image URL", "Product image URL"}
    image_idx = None
    product_image_idx = None
    for i, col in enumerate(header):
        if col == "Variant image URL":
            image_idx = i
        elif col == "Product image URL":
            product_image_idx = i
    
    if image_idx is None and product_image_idx is None:
        print("Brak kolumny z URL obrazu.", file=sys.stderr)
        return
    
    # Przetwarzaj wiersze
    for i, row in enumerate(rows[1:], start=2):
        if len(row) <= max(option1_idx, image_idx or 0, product_image_idx or 0):
            continue
        
        original_value = row[option1_idx]
        
        # Wybierz URL obrazu (priorytet: Variant image URL, potem Product image URL)
        image_url = ""
        if image_idx and len(row) > image_idx:
            image_url = row[image_idx].strip()
        if not image_url and product_image_idx and len(row) > product_image_idx:
            image_url = row[product_image_idx].strip()
        
        # Wyciągnij liczbę PCS
        pcs = extract_piece_count(original_value)
        
        # Pobierz obraz i wygeneruj nazwę
        img = fetch_image(image_url)
        if img:
            names = classify_scene_top_k(img, k=1, original_sku=original_value)
            new_name = names[0][0] if names else "Minecraft Zestaw"
            score = names[0][1] if names else 0.0
            print(f"Wiersz {i}: {original_value} → {new_name} (pewność: {score:.1f})")
        else:
            # Fallback bez obrazu - unikalny na podstawie SKU
            global name_counter
            fallback_base = "Kreatywny Zestaw"
            if fallback_base in name_counter:
                name_counter[fallback_base] += 1
                new_name = f"Kreatywny Zestaw {name_counter[fallback_base]}"
            else:
                name_counter[fallback_base] = 1
                new_name = fallback_base
            print(f"Wiersz {i}: {original_value} → {new_name} (brak obrazu)")
        
        # Zbuduj finalną nazwę
        row[option1_idx] = build_new_name_pl(new_name, pcs)
    
    # Zapisz
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    
    print(f"\n✅ Zapisano: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie: python3 rename_variants.py <input.csv> [output.csv]")
        sys.exit(1)
    
    input_csv = sys.argv[1]
    output_csv = sys.argv[2] if len(sys.argv) > 2 else None
    
    process_csv(input_csv, output_csv)
