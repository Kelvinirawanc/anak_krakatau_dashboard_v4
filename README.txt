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


REGIONAL AVIATION REFERENCES (updated)
--------------------------------------
Singapore: The Straits Times — Anak Krakatau eruption: SIA adds 8 relief flights between Jakarta and Singapore.
https://www.straitstimes.com/singapore/anak-krakatau-eruption-sia-adds-8-relief-flights-between-jakarta-and-singapore

Malaysia: The Star — Malaysia Airlines cancels 12 Jakarta flights after Anak Krakatau eruption.
https://www.thestar.com.my/news/nation/2026/09/06/malaysia-airlines-cancels-12-jakarta-flights-after-anak-krakatau-eruption

The previous Singapore Airlines fixed URL was removed because the page is no longer valid. The dashboard now treats the two news articles above as documented regional aviation references and keeps the NADMA/MetMalaysia page as a separate monitoring reference.
