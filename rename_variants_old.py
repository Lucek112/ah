import csv, re, sys, io, math, requests, os
from dataclasses import dataclass
from typing import List, Tuple, Optional
try:
    from PIL import Image
except ImportError:
    Image = None

# Opcjonalna rejestracja pluginów do AVIF/HEIF, jeśli dostępne
try:
    import pillow_avif  # noqa: F401
except Exception:
    try:
        from pillow_heif import register_heif_opener  # type: ignore
        register_heif_opener()
    except Exception:
        pass

try:
    import pytesseract
except ImportError:
    pytesseract = None

# Precyzyjne sygnatury bloków Minecraft (RGB) - dokładne kolory
MINECRAFT_BLOCKS = {
    # Naturalne bloki
    "grass_top": [(95, 135, 60), (107, 142, 35), (85, 125, 50)],  # góra trawy
    "dirt": [(134, 96, 67), (120, 85, 60), (110, 80, 50)],  # ziemia/brąz
    "stone": [(127, 127, 127), (115, 115, 115), (100, 100, 100)],  # szary kamień
    "water": [(62, 118, 190), (50, 100, 180), (38, 92, 255)],  # niebieski
    "oak_log": [(108, 76, 41), (145, 105, 70), (120, 85, 50)],  # pń drewna
    "oak_leaves": [(60, 100, 40), (50, 85, 35), (70, 110, 50)],  # liście
    
    # Specjalne bloki
    "tnt": [(219, 50, 50), (200, 40, 40)],  # czerwony TNT
    "lava": [(207, 101, 0), (235, 110, 15)],  # pomarańczowa lawa
    "obsidian": [(16, 12, 26), (25, 20, 35)],  # czarny
    "coal_ore": [(84, 84, 84), (70, 70, 70)],  # ciemny szary
    
    # Dekoracyjne
    "cake": [(255, 255, 255), (230, 200, 180)],  # białe ciasto
    "melon": [(145, 200, 60), (130, 190, 50)],  # zielony arbuz
    "pumpkin": [(210, 125, 30), (200, 115, 25)],  # pomarańczowa dynia
}

FALLBACK_PREFIX = {
    "RM": "Kolejowa Przygoda",
    "SJJ": "Kreatywny Zestaw",
    "YSSL": "Magiczny Dodatek",
    "T0": "Startowy Pakiet",
    "T": "Tematyczny Zestaw"
}

@dataclass
class VariantRow:
    row: List[str]
    option1_idx: int
    image_idx: int

def avg_color(img: Image.Image) -> Tuple[int,int,int]:
    img = img.convert("RGB").resize((32,32))
    pixels = list(img.getdata())
    r = sum(p[0] for p in pixels)//len(pixels)
    g = sum(p[1] for p in pixels)//len(pixels)
    b = sum(p[2] for p in pixels)//len(pixels)
    return r,g,b

def parse_block_table(img: Image.Image) -> dict:
    """Wyciąga listę bloków z dolnej tabelki (ikony+liczby)."""
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
    """Analizuje scenę 3D: CO zbudowano (dom, wodospad, las, jaskinia...)."""
    # Przytnij do sceny (usuń dolną tabelkę i ramki)
    w, h = img.size
    scene = img.crop((int(w*0.05), int(h*0.05), int(w*0.95), int(h*0.65)))
    
    # Zmniejsz dla wydajności
    small = scene.convert("RGB").resize((120, 80))
    pixels = list(small.getdata())
    
    # Zlicz dopasowania do bloków
    block_counts = {block: 0 for block in MINECRAFT_BLOCKS}
    threshold = 35  # ścisła tolerancja
    
    for pixel in pixels:
        # Pomiń bardzo jasne (białe tło/mgła)
        if pixel[0] > 230 and pixel[1] > 230 and pixel[2] > 230:
            continue
        
        for block_name, signatures in MINECRAFT_BLOCKS.items():
            for sig in signatures:
                if dist(pixel, sig) < threshold:
                    block_counts[block_name] += 1
                    break  # jeden blok per piksel
    
    # Filtruj bloki z minimalnym progiem (>0.5% pikseli)
    total = len([p for p in pixels if sum(p) < 690])
    significant = {block: count for block, count in block_counts.items() 
                   if count > total * 0.005}
    
    return significant
    """Analizuje elementy sceny 3D (centralna część obrazu, bez tła/UI)."""
    # Przytnij do centralnych 60% obrazu (unikaj ramek i tabel)
    w, h = img.size
    crop_margin_x = int(w * 0.2)
    crop_margin_y = int(h * 0.25)  # większa góra/dół (tabele)
    cropped = img.crop((crop_margin_x, crop_margin_y, w - crop_margin_x, h - crop_margin_y))
    
    # Zmniejsz do analizy
    small = cropped.convert("RGB").resize((80, 80))
    pixels = list(small.getdata())
    
    # Podziel obraz na regiony (góra, środek, dół) — 3D ma charakterystyczną strukturę
    sw, sh = small.size
    top_pixels = pixels[:sw * sh // 3]
    mid_pixels = pixels[sw * sh // 3: 2 * sw * sh // 3]
    bot_pixels = pixels[2 * sw * sh // 3:]
    
    def analyze_region(region_pixels):
        """Wykrywa cechy regionu."""
        # Pomiń bardzo jasne (tło > 220,220,220)
        filtered = [p for p in region_pixels if not (p[0] > 220 and p[1] > 220 and p[2] > 220)]
        if not filtered:
            return {'dominant': None, 'brightness': 255}
        
        avg_r = sum(p[0] for p in filtered) // len(filtered)
        avg_g = sum(p[1] for p in filtered) // len(filtered)
        avg_b = sum(p[2] for p in filtered) // len(filtered)
        brightness = (avg_r + avg_g + avg_b) // 3
        
        # Zlicz piksele każdego typu
        blue_count = sum(1 for p in filtered if p[2] > p[0] + 20 and p[2] > p[1] + 10)
        green_count = sum(1 for p in filtered if p[1] > p[0] + 10 and p[1] > p[2] + 5)
        brown_count = sum(1 for p in filtered if p[0] > p[2] + 10 and p[1] > p[2] and abs(p[0] - p[1]) < 30)
        gray_count = sum(1 for p in filtered if abs(p[0] - p[1]) < 20 and abs(p[1] - p[2]) < 20)
        red_count = sum(1 for p in filtered if p[0] > p[1] + 40 and p[0] > p[2] + 40)
        
        total = len(filtered)
        percentages = {
            'niebieski': blue_count / total if total > 0 else 0,
            'zielony': green_count / total if total > 0 else 0,
            'brązowy': brown_count / total if total > 0 else 0,
            'szary': gray_count / total if total > 0 else 0,
            'czerwony': red_count / total if total > 0 else 0,
        }
        
        # Dominujący = największy procent
        dominant = max(percentages.items(), key=lambda x: x[1])
        
        return {
            'dominant': dominant[0] if dominant[1] > 0.15 else 'mieszany',
            'brightness': brightness,
            'percentages': percentages
        }
    
    top = analyze_region(top_pixels)
    mid = analyze_region(mid_pixels)
    bot = analyze_region(bot_pixels)
    
    # Wykryj wodę: jeśli niebieski >10% w dowolnym regionie
    has_water = (top['percentages'].get('niebieski', 0) > 0.10 or 
                 mid['percentages'].get('niebieski', 0) > 0.10 or
                 bot['percentages'].get('niebieski', 0) > 0.10)
    
    # Wykryj zieleń: jeśli zielony dominuje lub >20% w top/mid
    has_greenery = (top['dominant'] == 'zielony' or mid['dominant'] == 'zielony' or
                    top['percentages'].get('zielony', 0) > 0.20 or
                    mid['percentages'].get('zielony', 0) > 0.20)
    
    # Wykryj kamień: szary >15% lub dominuje
    has_stone = (mid['dominant'] == 'szary' or bot['dominant'] == 'szary' or
                 mid['percentages'].get('szary', 0) > 0.15)
    
    # Drewno/ziemia: brązowy dominuje lub >30%
    has_wood = (any(r['dominant'] == 'brązowy' for r in [top, mid, bot]) or
                bot['percentages'].get('brązowy', 0) > 0.30)
    
    # Lawa: czerwony >5%
    has_lava = any(r['percentages'].get('czerwony', 0) > 0.05 for r in [top, mid, bot])
    
    return {
        'top': top,
        'mid': mid,
        'bot': bot,
        'has_water': has_water,
        'has_greenery': has_greenery,
        'has_stone': has_stone,
        'has_wood': has_wood,
        'has_lava': has_lava,
    }

def dominant_colors(img: Image.Image, k: int = 5) -> List[Tuple[int,int,int]]:
    """Wydobywa k dominujących kolorów z obrazu (poza białym tłem)."""
    img_small = img.convert("RGB").resize((64,64))
    pixels = list(img_small.getdata())
    # Filtruj bardzo jasne piksele (tło/watermark)
    filtered = [p for p in pixels if sum(p) < 700]  # suma RGB < 700 wykluczy białe
    if not filtered:
        filtered = pixels
    
    # Prosty clustering: grupuj kolory w przedziałach 40-punktowych
    buckets = {}
    for r,g,b in filtered:
        key = (r//40, g//40, b//40)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append((r,g,b))
    
    # Sortuj grupy według liczebności
    sorted_groups = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)
    result = []
    for (rk,gk,bk), group in sorted_groups[:k]:
        # Średni kolor w grupie
        avg_r = sum(p[0] for p in group)//len(group)
        avg_g = sum(p[1] for p in group)//len(group)
        avg_b = sum(p[2] for p in group)//len(group)
        result.append((avg_r, avg_g, avg_b))
    return result

def dist(c1, c2):
    return math.sqrt(sum((a-b)**2 for a,b in zip(c1,c2)))

def generate_name_from_structure(structure: dict, blocks_info: dict) -> str:
    """Generuje nazwę opisującą zbudowaną strukturę."""
    if not structure:
        return "Kreatywny Zestaw"
    
    # === SCENARIUSZE Z WODĄ ===
    if structure.get('has_water_flow'):
        if structure.get('has_trees'):
            return "Leśny Wodospad"
        if structure.get('has_building'):
            return "Dom nad Rzeką"
        if structure.get('has_landscape'):
            return "Górski Strumień"
        return "Wodna Kaskada"
    
    # === BUDYNKI I KONSTRUKCJE ===
    if structure.get('has_building'):
        if structure.get('has_trees'):
            return "Chatka w Lesie"
        if blocks_info.get('stone', 0) > blocks_info.get('dirt_or_wood', 0):
            return "Kamienny Zamek"
        return "Drewniana Wieża"
    
    # === KRAJOBRAZY NATURALNE ===
    if structure.get('has_trees'):
        if structure.get('has_platforms'):
            return "Tarasowy Gaj"
        if structure.get('has_landscape'):
            return "Zielona Dolina"
        return "Gaj Drzew"
    
    if structure.get('has_landscape'):
        if structure.get('has_platforms'):
            return "Wzgórza Terasowe"
        return "Trawiaste Wzgórze"
    
    # === KOPALNIE I NIEBEZPIECZEŃSTWA ===
    if structure.get('has_lava'):
        return "Ognista Jaskinia"
    
    if blocks_info.get('tnt_or_lava', 0) > 0:
        return "Wybuchowa Kopalnia"
    
    # === PLATFORMY I KONSTRUKCJE ===
    if structure.get('has_platforms'):
        return "Platformy Budowlane"
    
    # === DOMYŚLNE ===
    if blocks_info.get('grass', 0) > blocks_info.get('stone', 0):
        return "Zielony Krajobraz"
    if blocks_info.get('stone', 0) > 0:
        return "Kamienne Ruiny"
    
    return "Minecraft Scenka"
    """Generuje kreatywną nazwę opisującą zestaw na podstawie bloków."""
    if not blocks:
        return "Kreatywny Zestaw"
    
    # Sortuj bloki wg częstości
    sorted_blocks = sorted(blocks.items(), key=lambda x: x[1], reverse=True)
    top_blocks = [b[0] for b in sorted_blocks[:6]]
    
    # Funkcje pomocnicze
    has = lambda *names: any(n in top_blocks for n in names)
    dominant = lambda name: name in top_blocks[:2]
    
    # === SCENARIUSZE Z WODĄ ===
    if has('water'):
        if has('grass_top') and has('oak_leaves', 'oak_log'):
            return "Leśny Wodospad"
        if has('grass_top', 'oak_leaves'):
            return "Trawiasta Struga"
        if has('stone'):
            return "Kamienny Wodospad"
        if dominant('water'):
            return "Basen Wodny"
        return "Wodna Przygoda"
    
    # === SCENARIUSZE LEŚNE ===
    if has('oak_leaves') and has('oak_log'):
        if has('grass_top'):
            return "Zielony Gaj"
        return "Las Drzew"
    
    if has('grass_top') and has('oak_log'):
        return "Polana z Chatką"
    
    # === KONSTRUKCJE I BUDOWLE ===
    if has('stone') and blocks.get('stone', 0) > sum(blocks.values()) * 0.25:
        if has('oak_log'):
            return "Kamienny Dom"
        return "Forteca ze Skał"
    
    if has('dirt', 'grass_top') and has('oak_log'):
        return "Farma na Wzgórzu"
    
    # === KOPALNIE I NIEBEZPIECZEŃSTWA ===
    if has('lava'):
        if has('obsidian'):
            return "Portal do Netheru"
        if has('stone'):
            return "Jaskinia Lawy"
        return "Ognisty Krater"
    
    if has('tnt'):
        if has('coal_ore', 'stone'):
            return "Wybuchowa Kopalnia"
        return "Fabryka TNT"
    
    if has('obsidian'):
        return "Głęboka Kopalnia"
    
    # === DEKORACJE I TEMATYKA ===
    if has('cake'):
        return "Urodzinowa Chatka"
    
    if has('pumpkin', 'melon'):
        return "Farma Warzyw"
    
    # === DOMYŚLNE NA PODSTAWIE DOMINUJĄCYCH ===
    if dominant('grass_top'):
        return "Zielone Wzgórze"
    if dominant('dirt'):
        return "Ziemna Platforma"
    if dominant('stone'):
        return "Kamienna Ruina"
    if dominant('oak_log'):
        return "Drewniana Budowa"
    
    # Ogólne
    if has('grass_top', 'dirt'):
        return "Naturalna Kraina"
    
    return "Minecraft Sceneria"
    """Generuje nazwę na podstawie kompozycji przestrzennej sceny."""
    if not scene:
        return "Kreatywny Zestaw"
    
    # Scenariusze z wodą
    if scene.get('has_water'):
        if scene.get('has_greenery'):
            return "Leśny Wodospad"
        if scene.get('has_stone'):
            return "Górski Strumień"
        return "Wodna Oaza"
    
    # Leśne sceny
    if scene.get('has_greenery'):
        if scene.get('has_wood'):
            return "Zielona Polana"
        return "Trawiaste Wzgórze"
    
    # Konstrukcje kamienne
    if scene.get('has_stone'):
        if scene.get('has_wood'):
            return "Kamienna Wieża"
        return "Szara Forteca"
    
    # Lawa/ogien
    if scene.get('has_lava'):
        return "Ognista Kopalnia"
    
    # Drewniane budowle
    if scene.get('has_wood'):
        return "Drewniana Chatka"
    
    # Analiza jasności dla scenariuszy ogólnych
    if scene['top'].get('brightness', 200) < 100:
        return "Mroczna Jaskinia"
    
    return "Minecraft Sceneria"

def classify_scene_top_k(img: Image.Image, k: int = 3) -> List[Tuple[str, float]]:
    """Generuje nazwy na podstawie analizy zbudowanej struktury."""
    # 1. Parsuj tabelkę (jakie bloki są w zestawie)
    blocks_info = parse_block_table(img)
    
    # 2. Analizuj scenę 3D (co zostało zbudowane)
    structure = analyze_built_structure(img)
    
    # 3. Generuj nazwę
    primary = generate_name_from_structure(structure, blocks_info)
    
    names = [primary]
    
    # Alternatywne nazwy
    if structure.get('has_water_flow') and structure.get('has_trees'):
        names.append("Naturalna Kraina")
    elif structure.get('has_building'):
        names.append("Budowlany Projekt")
    elif structure.get('has_trees'):
        names.append("Leśna Sceneria")
    
    # Uzupełnij generycznymi
    fallbacks = ["Kreatywna Budowa", "Minecraft Zestaw", "Budowlana Przygoda"]
    for fb in fallbacks:
        if len(names) >= k:
            break
        if fb not in names:
            names.append(fb)
    
    return [(name, 5.0 + i*0.3) for i, name in enumerate(names[:k])]

def extract_piece_count(code: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*PCS", code.upper())
    return int(m.group(1)) if m else None

def guess_from_prefix(code: str) -> str:
    for pref, label in FALLBACK_PREFIX.items():
        if code.upper().startswith(pref):
            return label
    return "Building Blocks Set"

def build_new_name(block: str, pcs: Optional[int]) -> str:
    if pcs:
        return f"{block} Set ({pcs} pcs)"
    return f"{block} Set"

def build_new_name_pl(block_pl: str, pcs: int) -> str:
    # Zawsze: "<polska nazwa> <liczba>PCS"
    return f"{block_pl} {pcs}PCS"

def fetch_image(url: str) -> Optional[Image.Image]:
    if not url or not Image:
        return None
    try:
        if url.lower().startswith("http://") or url.lower().startswith("https://"):
            # Retry logic dla stabilności
            for attempt in range(2):
                try:
                    r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                    r.raise_for_status()
                    return Image.open(io.BytesIO(r.content))
                except Exception as e:
                    if attempt == 0:
                        continue  # spróbuj ponownie
                    print(f"  [!] Błąd pobierania {url[:50]}: {e}")
                    return None
        # traktuj jako ścieżkę lokalną
        if os.path.exists(url):
            return Image.open(url)
        return None
    except Exception as e:
        print(f"  [!] Błąd {url[:40]}: {e}")
        return None

def extract_pcs_from_image(img: Image.Image) -> Optional[int]:
    """Wydobywa liczbę elementów z tekstu na obrazie używając OCR."""
    if not pytesseract:
        return None
    try:
        text = pytesseract.image_to_string(img)
        # Szukaj wzorców: "128 PCS", "128PCS", "128 szt" itp.
        m = re.search(r'(\d+)\s*(?:PCS|pcs|szt|pieces)', text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        # Fallback: szukaj samej liczby w zakresie rozsądnym (50-1000)
        nums = re.findall(r'\b(\d{2,4})\b', text)
        for n in nums:
            val = int(n)
            if 50 <= val <= 1000:
                return val
        return None
    except Exception:
        return None

def process_csv(in_path: str, out_path: str):
    with open(in_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        print("Pusty CSV")
        return
    header = rows[0]
    # Lokalizacja kolumn
    try:
        option1_idx = header.index("Option1 value")
    except ValueError:
        print("Brak kolumny Option1 value")
        return
    image_candidates = {
        "Variant image URL",
        "Product image URL"
    }
    image_idx = next((header.index(c) for c in image_candidates if c in header), -1)
    if image_idx == -1:
        print("Brak kolumny z URL obrazka")
        return

    updated = [header]
    for i, r in enumerate(rows[1:], start=2):
        if not r or len(r) <= option1_idx:
            updated.append(r)
            continue
        original_code = r[option1_idx].strip()
        if not original_code:
            updated.append(r)
            continue
        img_url = r[image_idx].strip() if image_idx >= 0 and image_idx < len(r) else ""
        pcs = extract_piece_count(original_code)
        
        # Nowa logika: pobierz obraz i użyj klasyfikacji scen
        scene_name = None
        img = fetch_image(img_url) if img_url else None
        if img:
            # Użyj najlepszej klasyfikacji sceny
            top_scenes = classify_scene_top_k(img, k=1)
            if top_scenes:
                scene_name = top_scenes[0][0]
                print(f"Wiersz {i}: {original_code} → {scene_name} (score: {top_scenes[0][1]:.1f})")
        
        # Fallback: jeśli brak obrazu lub klasyfikacja się nie udała
        if not scene_name:
            scene_name = guess_from_prefix(original_code)
            print(f"Wiersz {i}: {original_code} → {scene_name} [fallback]")
        
        new_name = build_new_name_pl(scene_name, pcs) if pcs else scene_name
        r[option1_idx] = new_name
        updated.append(r)

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerows(updated)
    print(f"\nZapisano: {out_path}")

def main():
    if len(sys.argv) < 2:
        print("Użycie: python rename_variants.py input.csv [output.csv]")
        return
    in_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else in_path.rsplit(".",1)[0] + "_renamed.csv"
    process_csv(in_path, out_path)

if __name__ == "__main__":
    main()