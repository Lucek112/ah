# Copilot Instructions for this Repo

Goal: automate renaming product variant names in CSVs based on image color signatures and/or SKU prefixes.

## Big Picture
- Single-purpose Python script: `rename_variants.py` reads an input CSV and writes a new CSV with updated values in column `Option1 value`.
- Data flow:
  1) Read CSV (UTF-8) and header
  2) For each row, derive a block name from image average color or prefix fallback
  3) Extract piece count from the original value (pattern: `<number> PCS`)
  4) Build final name: `<Block Name> Set` or `<Block Name> Set (<n> pcs)`
  5) Save as `<input>_renamed.csv` (unless explicit output path provided)
- External calls: downloads the variant image via `requests` to estimate average color; uses Pillow if installed.

## CSV Schema Expectations
- Required header: `Option1 value` (source and destination of the name).
- Image URL column: first available among `{ "Variant image URL", "Product image URL" }`.
- Encoding: UTF-8; rows are written unchanged except `Option1 value`.

## Renaming Logic (key functions)
- Color signatures: `BLOCK_SIGNATURES` maps block names to 2 RGB reference triples; nearest signature wins.
- Color classification: `classify_color(avg_rgb)` with threshold `70`; above → no confident match.
- Fallback prefixes: `FALLBACK_PREFIX` maps leading codes (e.g., `RM`, `SJJ`, `YSSL`, `T0`, `T`) to labels.
- Pieces extraction: `extract_piece_count()` finds `<digits> PCS` case-insensitive.
- Final format: `build_new_name(block, pcs)` → `"{block} Set"` or `"{block} Set ({pcs} pcs)"`.

## Runtime Behavior & Assumptions
- Pillow optional: if `PIL` is missing, color-based detection is skipped; only prefix fallback applies.
- Network: image fetched via `requests.get(url, timeout=8)`; failures silently fall back to prefix.
- Performance: images are resized to `32x32` for average color; no caching; large CSVs may be network-bound.
- Localization: console messages are in Polish; keep UTF-8 I/O.

## Typical Workflows
- Install deps:
  ```bash
  pip install -r requirements.txt
  ```
- Run on bundled sample:
  ```bash
  python3 rename_variants.py product_1005007525021418.csv
  ```
  Output: `product_1005007525021418_renamed.csv`.
- Custom output path:
  ```bash
  python3 rename_variants.py input.csv output.csv
  ```

## Project-Specific Conventions
- Threshold tuning: adjust `classify_color` threshold (default `70`) to be stricter/looser.
- Extend signatures: add RGB tuples under `BLOCK_SIGNATURES` for better matching (2 samples per block typical).
- Prefix mapping: edit `FALLBACK_PREFIX` to map SKU prefixes to friendly names.
- Column names: if your CSV differs, update `image_candidates` set and required header `Option1 value` in `process_csv`.

## Examples
- Input `Option1 value`: `RM-42 250 PCS` → Fallback: `Rails & Minecart Set (250 pcs)`.
- If image avg ≈ water blues and count `120 PCS` → `Water Set (120 pcs)` even if no matching prefix.

## Key Files
- `rename_variants.py` — main script with logic and constants to tweak.
- `requirements.txt` — `requests`, `Pillow`.

## Guardrails for Agents
- Don’t change I/O columns without updating header detection accordingly.
- Preserve CSV structure; only mutate `Option1 value`.
- Handle missing/slow images gracefully; never crash on network/PIL errors.
