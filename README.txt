ANAK KRAKATAU 2026 IMPACT DASHBOARD - UPDATED BUILD

What changed:
1. Header now shows an explicit "UPDATED DATA AS OF" label with a standard date/time.
2. Impact Summary expanded from 3 to 6 cards so the section is not mostly empty space.
3. Airport Impact chart now shows only current operational impact:
   - Temporary Closure
   - Other Affected
   Previously affected airports remain in the table for historical context.
4. Impacted Area map now includes:
   - reported ash-affected corridor in Indonesia (approximate analytical polygon)
   - higher-level ash monitoring area offshore (approximate analytical polygon)
   - one Anak Krakatau mountain icon
   - plane icons for impacted Indonesian airports
   - Singapore Changi plane icon for documented Singapore-Jakarta aviation disruption
   - Malaysia monitoring icon, explicitly labelled as monitoring / low-risk rather than confirmed ashfall impact
5. Health Response includes hospitals, puskesmas, and cumulative ISPA context.
6. Footer credit is restored to Kelvin Irawan.
7. Scraper now collects regional references and writes both JSON and GeoJSON.

Run scraper:
  python -m pip install -r requirements.txt
  python scraper\scrape_anak_krakatau_2026.py

Then run the dashboard with VS Code Live Server and refresh the page.
