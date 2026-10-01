ANAK KRAKATAU 2026 — DASHBOARD + KEYWORD VALIDATION SCRAPER

Update in this build:
- Dashboard source cards no longer label every source as "Fallback data used".
- Source cards distinguish Validated source, Reference fallback, and Source unavailable.
- Initial dashboard language is English; user language choice is saved after explicit switching.
- Scraper performs keyword discovery + scoring + relevance threshold validation.
- If a candidate fails the threshold, the original fixed article URL is fetched and used as the reference fallback.
- Numeric fallback values are tracked separately from reference selection.

Workflow:
.github/workflows/update-dashboard.yml

The existing GitHub Actions workflow can run the scraper daily and commit updated JSON/GeoJSON data.
