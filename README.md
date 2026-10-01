# Anak Krakatau 2026 — Keyword Search + Relevance Validation Scraper

This is a replacement for the previous `scrape_anak_krakatau_2026.py`.

## Why the old version failed

The existing script imports:

```python
from bs4 import BeautifulSoup
```

so the environment must have the `beautifulsoup4` package installed. The included `requirements.txt` fixes that dependency.

## New source-selection flow

```text
Existing fixed reference URL
          │
          │  kept as fallback
          ▼
Search official source by keywords
          │
          ▼
Get candidate URLs
          │
          ▼
Fetch candidate page
          │
          ▼
Relevance scoring
  - core event keywords
  - impact/topic keywords
  - dates / 2026
  - expected numeric/context keywords
  - official domain validation
          │
      ┌───┴──────────┐
      │              │
  Score passes    Score fails
      │              │
      ▼              ▼
Use searched      Use original
reference         fixed reference
      │              │
      └──────┬───────┘
             ▼
      Extract dashboard data
             ▼
        Write JSON/GeoJSON
```

## Validation rule

A candidate is accepted only when **both** conditions are met:

1. All required keyword groups are present.
2. The relevance score is at or above the source's `min_score`.

Otherwise the original fixed reference is used.

The generated JSON records:

- `selection_method`
- `relevance_score`
- `minimum_score`
- `validation_passed`
- `matched_keywords`
- `fixed_reference`
- `candidate_count`
- `best_candidate`

This makes the source-selection logic visible and auditable.

## Run

Double-click:

```text
run_scraper.bat
```

or run:

```powershell
python -m pip install -r requirements.txt
python scraper\scrape_anak_krakatau_2026.py
```

## Important limitation

Keyword discovery cannot guarantee that a search engine will return every newly published article. Search-engine HTML can change or be rate-limited. That is why the fixed links remain in the configuration and are automatically used when discovery is unavailable or a candidate does not pass validation.

## Dashboard compatibility

The script keeps the same output filenames:

```text
data\anak_krakatau_2026.json

data\impacted_areas.geojson
```

so your existing `index.html` / `dashboard.js` can continue using the same data paths.
