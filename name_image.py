import sys
from typing import Optional

from rename_variants import Image, classify_scene_top_k, build_new_name_pl, extract_pcs_from_image


def main():
    if len(sys.argv) < 2:
        print("Użycie: python name_image.py <ścieżka_lub_URL_do_obrazu> [pcs]")
        print("  Jeśli pcs nie podane, spróbuje wydobyć z OCR obrazu.")
        return
    path = sys.argv[1]
    pcs: Optional[int] = None
    if len(sys.argv) >= 3:
        try:
            pcs = int(sys.argv[2])
        except Exception:
            pass

    if Image is None:
        print("Brak biblioteki Pillow — zainstaluj zależności.")
        return

    try:
        if path.lower().startswith("http://") or path.lower().startswith("https://"):
            from rename_variants import fetch_image
            img = fetch_image(path)
        else:
            img = Image.open(path)
        if not img:
            print("Nie udało się wczytać obrazu.")
            return
        
        # OCR: wydobądź liczbę elementów z obrazu, jeśli nie podano
        if pcs is None:
            pcs = extract_pcs_from_image(img)
            if pcs:
                print(f"[OCR] Wykryto liczbę elementów: {pcs}")
            else:
                print("[OCR] Nie wykryto liczby elementów, użyj drugiego argumentu.")
                return
        
        top3 = classify_scene_top_k(img, k=3)
        # Wypisz 3 nazwy scen z liczbą PCS
        for scene_name, score in top3:
            print(build_new_name_pl(scene_name, pcs))
    except Exception as e:
        print(f"Błąd: {e}")


if __name__ == "__main__":
    main()
