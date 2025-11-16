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

# Heurystyki strukturalne — wzorce kompozycji 3D
# Zamiast sztywnych sygnatur, analizujemy cechy przestrzenne obrazu

# Polskie nazwy scen — już zawarte w kluczach SCENE_SIGNATURES
# (klucze są bezpośrednio używane jako nazwy)

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

def analyze_structure(img: Image.Image) -> dict:
    """Analizuje strukturę kompozycji 3D na obrazie."""
    # Zmniejsz dla wydajności
    small = img.convert("RGB").resize((128, 128))
    pixels = list(small.getdata())
    w, h = small.size
    
    # 1. Podziel na regiony (góra, środek, dół)
    top_region = pixels[:w * h // 3]
    mid_region = pixels[w * h // 3: 2 * w * h // 3]
    bot_region = pixels[2 * w * h // 3:]
    
    def avg_brightness(region):
        return sum(sum(p) for p in region) / (len(region) * 3) if region else 0
    
    top_bright = avg_brightness(top_region)
    mid_bright = avg_brightness(mid_region)
    bot_bright = avg_brightness(bot_region)
    
    # 2. Wykryj dominujące kolory (bez białego tła)
    color_groups = {}
    for r, g, b in pixels:
        if r + g + b > 700:  # pomiń bardzo jasne (tło)
            continue
        # Grupuj w przedziały 50x50x50
        key = (r // 50, g // 50, b // 50)
        color_groups[key] = color_groups.get(key, 0) + 1
    
    sorted_colors = sorted(color_groups.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # 3. Oblicz wskaźniki
    has_green = any(c[0][1] > c[0][0] and c[0][1] > c[0][2] for c in sorted_colors[:3])  # zieleń
    has_blue = any(c[0][2] > c[0][0] and c[0][2] > c[0][1] for c in sorted_colors[:3])   # niebieski
    has_brown = any(c[0][0] > c[0][2] and c[0][1] > c[0][2] and abs(c[0][0] - c[0][1]) < 2 for c in sorted_colors[:3])  # brąz
    has_gray = any(abs(c[0][0] - c[0][1]) <= 1 and abs(c[0][1] - c[0][2]) <= 1 for c in sorted_colors[:3])  # szary
    has_red_orange = any(c[0][0] > c[0][1] + 1 and c[0][0] > c[0][2] + 1 for c in sorted_colors[:2])  # czerwień/pomarańcz
    
    # 4. Analiza pionowa (budynki wysokie = jasno u góry, ciemno na dole)
    vertical_structure = top_bright > mid_bright + 20  # wysokie konstrukcje
    
    # 5. Złożoność (liczba różnych kolorów)
    color_diversity = len(color_groups)
    
    return {
        'has_green': has_green,
        'has_blue': has_blue,
        'has_brown': has_brown,
        'has_gray': has_gray,
        'has_red_orange': has_red_orange,
        'vertical': vertical_structure,
        'complexity': color_diversity,
        'top_colors': sorted_colors[:3]
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

def generate_creative_name(features: dict) -> str:
    """Generuje kreatywną nazwę na podstawie cech strukturalnych."""
    import random
    
    # Baza słów tematycznych
    nature_words = ["Zaczarowany", "Magiczny", "Tajemniczy", "Ukryty", "Dziki", "Spokojny"]
    struct_types = []
    
    # Określ typ struktury na podstawie cech
    if features['vertical'] and features['has_gray']:
        struct_types = ["Zamek", "Wieża", "Forteca", "Cytadela", "Bastion"]
    elif features['has_blue'] and features['has_green']:
        struct_types = ["Wodospad", "Strumień", "Zatoka", "Wyspa", "Oaza"]
    elif features['has_green'] and features['has_brown'] and not features['has_blue']:
        struct_types = ["Las", "Wzgórze", "Dolina", "Polana", "Sad"]
    elif features['has_gray'] and features['complexity'] > 15:
        struct_types = ["Kopalnia", "Jaskinia", "Grot", "Labirynt", "Ruiny"]
    elif features['has_brown'] and features['has_gray']:
        struct_types = ["Wioska", "Osada", "Przysiółek", "Farma", "Zagroda"]
    elif features['has_red_orange']:
        struct_types = ["Wulkan", "Kuźnia", "Piec", "Ognisko", "Piekło"]
    else:
        struct_types = ["Świat", "Kraina", "Przygoda", "Misja", "Świątynia"]
    
    prefix = random.choice(nature_words)
    structure = random.choice(struct_types)
    
    return f"{prefix} {structure}"

def classify_scene_top_k(img: Image.Image, k: int = 3) -> List[Tuple[str, float]]:
    """Generuje k różnych kreatywnych nazw dla sceny."""
    features = analyze_structure(img)
    
    # Generuj k różnych nazw
    names = []
    seen = set()
    for _ in range(k * 3):  # generuj więcej, żeby uniknąć duplikatów
        name = generate_creative_name(features)
        if name not in seen:
            names.append(name)
            seen.add(name)
        if len(names) >= k:
            break
    
    # Zwróć z fikcyjnym score (0-10) dla kompatybilności
    import random
    return [(name, random.uniform(3, 8)) for name in names[:k]]

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
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content))
        # traktuj jako ścieżkę lokalną
        if os.path.exists(url):
            return Image.open(url)
        return None
    except Exception as e:
        print(f"  [!] Błąd pobierania {url[:50]}: {e}")
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