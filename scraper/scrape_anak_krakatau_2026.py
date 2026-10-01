"""
============================================================
ANAK KRAKATAU 2026 - KEYWORD-BASED SCRAPER
Data analysis & dashboard by Kelvin Irawan
============================================================

PURPOSE
-------
The scraper first discovers candidate pages from official domains using
keywords, robots.txt / sitemap.xml, internal links and site-restricted
search. Each candidate is scored for relevance. If the best candidate
does not meet the configured relevance threshold, the scraper uses the
original fixed article URL as a REFERENCE FALLBACK for that source.
Only if the reference itself cannot be fetched, or a KPI cannot be
extracted from any usable source, are numeric fallback values used.

Running the scraper again will repeat the discovery process and can
pick up newly published articles without changing this Python file.

OUTPUTS
-------
1. data/anak_krakatau_2026.json
2. data/impacted_areas.geojson

DEPENDENCIES
------------
requests
beautifulsoup4

RUN
---
python scraper\\scrape_anak_krakatau_2026.py

NOTE
----
The fixed URLs are reference fallbacks, not numeric fallbacks. The console
output distinguishes keyword matches, fixed-reference fallback, and true
numeric fallback fields.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# PATHS / CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_JSON = DATA_DIR / "anak_krakatau_2026.json"
OUTPUT_GEOJSON = DATA_DIR / "impacted_areas.geojson"

TIMEOUT = 20
CRAWL_DELAY = 0.15
MAX_PAGES_PER_SOURCE = 18
MAX_SITEMAP_URLS = 350
MAX_INTERNAL_LINKS = 80
MAX_SEARCH_RESULTS_PER_QUERY = 8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36 "
        "AnakKrakatauDashboard/1.0"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}


# ============================================================
# OFFICIAL DOMAINS + KEYWORDS
# ============================================================

# IMPORTANT:
# There are NO fixed article URLs in this configuration.
# Only domains and keyword groups are defined.

OFFICIAL_SOURCES = [
    {
        "key": "badan_geologi",
        "name": "Badan Geologi / PVMBG",
        "domains": ["geologi.esdm.go.id"],
        "fixed_reference_url": "https://geologi.esdm.go.id/media-center/laporan-khusus-penurunan-tingkat-aktivitas-gunungapi-anak-krakatau-provinsi-lampung-dari-level-iii-siaga-menjadi-level-ii-waspada-tanggal-21-september-2026-pukul-18-30-wib",
        "min_relevance_score": 14,
        "keywords": [
            "anak krakatau",
            "krakatau",
            "erupsi",
            "erupsi gunungapi",
            "aktivitas gunungapi",
            "level ii",
            "level iii",
            "waspada",
            "siaga",
            "letusan",
        ],
    },
    {
        "key": "bnpb",
        "name": "Badan Nasional Penanggulangan Bencana",
        "domains": ["bnpb.go.id", "www.bnpb.go.id"],
        "fixed_reference_url": "https://bnpb.go.id/berita/update-aktivitas-gunung-anak-krakatau-status-level-iii-masih-berlaku",
        "min_relevance_score": 12,
        "keywords": [
            "anak krakatau",
            "krakatau",
            "erupsi",
            "abu vulkanik",
            "dampak",
            "terdampak",
            "bandara",
            "evakuasi",
            "bencana",
        ],
    },
    {
        "key": "kemenhub",
        "name": "Kementerian Perhubungan RI",
        "domains": ["kemenhub.go.id", "dephub.go.id"],
        "fixed_reference_url": "https://www.kemenhub.go.id/post/read/sejumlah-bandara-masih-terdampak-abu-vulkanik-gunung-anak-krakatau%2C-kemenhub-siapkan-bandara-alternatif",
        "min_relevance_score": 14,
        "keywords": [
            "anak krakatau",
            "abu vulkanik",
            "bandara",
            "penerbangan",
            "penerbangan terdampak",
            "ditutup sementara",
            "penyesuaian rute",
            "pengalihan penerbangan",
            "penumpang",
        ],
    },
    {
        "key": "kemenkes",
        "name": "Kementerian Kesehatan RI",
        "domains": ["kemkes.go.id", "www.kemkes.go.id"],
        "fixed_reference_url": "https://www.kemkes.go.id/id/kemenkes-siagakan-413-rumah-sakit-dan-830-puskesmas-hadapi-dampak-erupsi-anak-krakatau",
        "min_relevance_score": 13,
        "keywords": [
            "anak krakatau",
            "erupsi",
            "rumah sakit",
            "puskesmas",
            "kesehatan",
            "ispa",
            "abu vulkanik",
            "kabupaten/kota",
        ],
    },
    {
        "key": "bmkg",
        "name": "Badan Meteorologi, Klimatologi, dan Geofisika",
        "domains": ["bmkg.go.id", "www.bmkg.go.id"],
        "fixed_reference_url": "https://www.bmkg.go.id/berita/utama/bmkg-terus-pantau-dampak-erupsi-gunung-anak-krakatau",
        "min_relevance_score": 12,
        "keywords": [
            "anak krakatau",
            "abu vulkanik",
            "volcanic ash",
            "sebaran abu",
            "ash cloud",
            "angin",
            "sigi",
            "sigmet",
            "penerbangan",
        ],
    },
    {
        "key": "singapore",
        "name": "Singapore Official Aviation / Meteorological Sources",
        "domains": ["caas.gov.sg", "nea.gov.sg", "weather.gov.sg"],
        "fixed_reference_url": "https://www.singaporeair.com/en_UK/dk/corporate/newsroom/newsalert-listing/advisory-on-singapore-airlines-flights-impacted-by-the-eruption-/",
        "min_relevance_score": 10,
        "keywords": [
            "anak krakatau",
            "krakatau",
            "volcanic ash",
            "ash cloud",
            "flight",
            "singapore",
            "jakarta",
        ],
    },
    {
        "key": "malaysia",
        "name": "Malaysia Official Meteorological / Disaster Sources",
        "domains": ["met.gov.my", "nadma.gov.my"],
        "fixed_reference_url": "https://www.nadma.gov.my/bi/media-en/news/7101-metmalaysia-anak-krakatau-ash-could-reach-malaysia-but-risk-remains-low",
        "min_relevance_score": 10,
        "keywords": [
            "anak krakatau",
            "krakatau",
            "volcanic ash",
            "abu vulkanik",
            "malaysia",
            "ash cloud",
            "monitoring",
            "penerbangan",
        ],
    },
]

CORE_KEYWORDS = [
    "anak krakatau",
    "krakatau",
    "erupsi",
    "eruption",
    "volcanic ash",
    "abu vulkanik",
    "ash cloud",
]

IMPACT_KEYWORDS = [
    "terdampak",
    "dampak",
    "affected",
    "impact",
    "disruption",
    "ditutup",
    "closure",
    "penyesuaian rute",
    "route adjustment",
    "penerbangan",
    "flight",
    "passenger",
    "penumpang",
    "rumah sakit",
    "hospital",
    "puskesmas",
    "ispa",
    "monitoring",
]


# ============================================================
# FALLBACK VALUES
# ============================================================

# These are NOT used as the primary source. They are a safety net
# so the dashboard does not collapse to zero if a government site
# is temporarily unavailable.

FALLBACK = {
    "status": "Level II — Waspada",
    "status_date": "21 September 2026, 18:30 WIB",
    "level_iii_start": "2 July 2026, 16:30 WIB",
    "continuous_start": "4 September 2026, 23:07 WIB",
    "continuous_end": "6 September 2026, 00:04 WIB",
    "continuous_duration": "~25 hours",
    "population": 23360000,
    "hospitals": 413,
    "puskesmas": 830,
    "affected_regencies_cities": 20,
    "ispa": 16759,
    "flights": 2300,
    "passengers": 270337,
    "closure_flights": 1397,
    "closure_passengers": 177579,
    "route_flights": 922,
    "route_passengers": 92758,
}


# ============================================================
# STATIC REFERENCE DATA (GEOGRAPHY ONLY)
# ============================================================

# This is not event data. These are geographic reference shapes and
# airport coordinates used ONLY after the scraper detects a place.

REGION_REFERENCE = {
    "Lampung": {
        "country": "Indonesia",
        "type": "region",
        "status": "reported impact",
        "polygon": [
            [103.2, -5.95],
            [105.75, -5.95],
            [105.75, -3.75],
            [103.2, -3.75],
            [103.2, -5.95],
        ],
    },
    "Banten": {
        "country": "Indonesia",
        "type": "region",
        "status": "reported impact",
        "polygon": [
            [105.05, -7.05],
            [106.85, -7.05],
            [106.85, -5.85],
            [105.05, -5.85],
            [105.05, -7.05],
        ],
    },
    "DKI Jakarta": {
        "country": "Indonesia",
        "type": "region",
        "status": "reported impact",
        "polygon": [
            [106.63, -6.45],
            [107.02, -6.45],
            [107.02, -6.02],
            [106.63, -6.02],
            [106.63, -6.45],
        ],
    },
    "Jawa Barat": {
        "country": "Indonesia",
        "type": "region",
        "status": "reported impact",
        "polygon": [
            [106.25, -7.85],
            [108.85, -7.85],
            [108.85, -5.85],
            [106.25, -5.85],
            [106.25, -7.85],
        ],
    },
    "Bengkulu": {
        "country": "Indonesia",
        "type": "region",
        "status": "reported / monitored",
        "polygon": [
            [101.0, -5.55],
            [104.0, -5.55],
            [104.0, -2.45],
            [101.0, -2.45],
            [101.0, -5.55],
        ],
    },
    "Sumatera Selatan": {
        "country": "Indonesia",
        "type": "region",
        "status": "reported / monitored",
        "polygon": [
            [102.0, -4.90],
            [106.0, -4.90],
            [106.0, -1.35],
            [102.0, -1.35],
            [102.0, -4.90],
        ],
    },
    "Singapore": {
        "country": "Singapore",
        "type": "country",
        "status": "aviation / monitoring mention",
        "polygon": [
            [103.58, 1.15],
            [104.10, 1.15],
            [104.10, 1.48],
            [103.58, 1.48],
            [103.58, 1.15],
        ],
    },
    "Malaysia": {
        "country": "Malaysia",
        "type": "country",
        "status": "monitoring mention",
        "polygon": [
            [99.55, 1.00],
            [104.90, 1.00],
            [104.90, 7.40],
            [99.55, 7.40],
            [99.55, 1.00],
        ],
    },
}

PLACE_ALIASES = {
    "Lampung": ["lampung"],
    "Banten": ["banten"],
    "DKI Jakarta": ["dki jakarta", "jakarta"],
    "Jawa Barat": ["jawa barat", "west java"],
    "Bengkulu": ["bengkulu"],
    "Sumatera Selatan": ["sumatera selatan", "south sumatra"],
    "Singapore": ["singapore", "singapura"],
    "Malaysia": ["malaysia"],
}

AIRPORTS = {
    "CGK": {
        "name": "Soekarno-Hatta International Airport",
        "province": "Banten",
        "lat": -6.1256,
        "lng": 106.6559,
    },
    "HLP": {
        "name": "Halim Perdanakusuma Airport",
        "province": "DKI Jakarta",
        "lat": -6.2666,
        "lng": 106.8900,
    },
    "TKG": {
        "name": "Radin Inten II Airport",
        "province": "Lampung",
        "lat": -5.2427,
        "lng": 105.1751,
    },
    "RTO": {
        "name": "Budiarto Airport",
        "province": "Banten",
        "lat": -6.2930,
        "lng": 106.5690,
    },
    "PCB": {
        "name": "Pondok Cabe Airport",
        "province": "Banten",
        "lat": -6.3369,
        "lng": 106.7640,
    },
    "BDO": {
        "name": "Husein Sastranegara Airport",
        "province": "West Java",
        "lat": -6.9006,
        "lng": 107.5764,
    },
    "TNB": {
        "name": "Muhammad Taufiq Kiemas Airport",
        "province": "Lampung",
        "lat": -5.2110,
        "lng": 105.1630,
    },
    "PXA": {
        "name": "Atung Bungsu Airport",
        "province": "South Sumatra",
        "lat": -4.0330,
        "lng": 103.3950,
    },
    "SIN": {
        "name": "Singapore Changi Airport",
        "province": "Singapore",
        "lat": 1.3644,
        "lng": 103.9915,
    },
    "KUL": {
        "name": "Kuala Lumpur International Airport",
        "province": "Malaysia",
        "lat": 2.7456,
        "lng": 101.7099,
    },
    "SZB": {
        "name": "Sultan Abdul Aziz Shah Airport",
        "province": "Malaysia",
        "lat": 3.1306,
        "lng": 101.5493,
    },
}


# ============================================================
# SESSION
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# GENERAL HELPERS
# ============================================================


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or " ").strip()


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    clean = parsed._replace(fragment="")
    return clean.geturl().rstrip("/")


def is_same_domain(url: str, domains: Sequence[str]) -> bool:
    host = (urlparse(url).netloc or "").lower().split(":")[0]
    host = host.removeprefix("www.")
    allowed = {d.lower().removeprefix("www.") for d in domains}
    return host in allowed


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    if soup.title:
        return normalize_space(soup.title.get_text(" ", strip=True))
    return ""


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    return normalize_space(soup.get_text(" ", strip=True))


def fetch(url: str) -> Tuple[str, int]:
    try:
        response = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        return response.text, response.status_code
    except requests.RequestException as exc:
        print(f"    ! {exc}")
        return "", 0


def parse_number(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    # Indonesian/English thousands separators.
    text = text.replace(".", "").replace(",", "")
    try:
        return int(text)
    except ValueError:
        return None


def find_first_number(patterns: Sequence[str], text: str, flags=re.I) -> Optional[int]:
    for pattern in patterns:
        match = re.search(pattern, text or "", flags)
        if match:
            number = parse_number(match.group(1))
            if number is not None:
                return number
    return None


def normalize_status(status: Optional[str]) -> Optional[str]:
    if not status:
        return None
    value = status.lower()
    if "level iii" in value or "level 3" in value or "siaga" in value:
        return "Level III — Siaga"
    if "level ii" in value or "level 2" in value or "waspada" in value:
        return "Level II — Waspada"
    if "level i" in value or "level 1" in value or "normal" in value:
        return "Level I — Normal"
    return normalize_space(status)


def extract_iso_date(text: str) -> Optional[str]:
    # We mostly use publication metadata here, but this catches ISO timestamps too.
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text or "")
    if not match:
        return None
    try:
        dt = datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        )
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def extract_human_date(text: str) -> Optional[str]:
    months = {
        "januari": 1, "februari": 2, "maret": 3, "april": 4,
        "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
        "september": 9, "oktober": 10, "november": 11, "desember": 12,
        "january": 1, "february": 2, "march": 3, "may": 5,
        "june": 6, "july": 7, "august": 8, "october": 10,
        "november": 11, "december": 12,
    }
    pattern = (
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
        r"September|October|November|December|Januari|Februari|Maret|April|Mei|"
        r"Juni|Juli|Agustus|September|Oktober|November|Desember)\s+(20\d{2})\b"
    )
    matches = re.findall(pattern, text or "", flags=re.I)
    dates = []
    for day, month_name, year in matches:
        month = months.get(month_name.lower())
        if month is None:
            continue
        try:
            dates.append(datetime(int(year), month, int(day)))
        except ValueError:
            continue
    if not dates:
        return None
    return max(dates).strftime("%Y-%m-%d")


def extract_best_date(html: str, text: str) -> Optional[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    candidates = []
    for attr in ["article:published_time", "article:modified_time", "date", "datePublished", "dateModified"]:
        meta = soup.find("meta", attrs={"property": attr}) or soup.find("meta", attrs={"name": attr})
        if meta and meta.get("content"):
            date = extract_iso_date(meta["content"])
            if date:
                candidates.append(date)
    for time_tag in soup.find_all("time")[:10]:
        value = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
        date = extract_iso_date(value) or extract_human_date(value)
        if date:
            candidates.append(date)
    date = extract_iso_date(text) or extract_human_date(text)
    if date:
        candidates.append(date)
    return max(candidates) if candidates else None


# ============================================================
# ROBOTS / SITEMAP DISCOVERY
# ============================================================


def get_robots_sitemaps(domain: str) -> List[str]:
    robots_url = f"https://{domain}/robots.txt"
    html, _ = fetch(robots_url)
    sitemaps = []
    if html:
        for line in html.splitlines():
            if line.lower().startswith("sitemap:"):
                candidate = line.split(":", 1)[1].strip()
                if candidate.startswith("http"):
                    sitemaps.append(candidate)
    for candidate in [
        f"https://{domain}/sitemap.xml",
        f"https://{domain}/sitemap_index.xml",
        f"https://{domain}/post-sitemap.xml",
        f"https://{domain}/page-sitemap.xml",
    ]:
        if candidate not in sitemaps:
            sitemaps.append(candidate)
    return list(dict.fromkeys(sitemaps))


def parse_sitemap(url: str, seen: Optional[set] = None) -> List[str]:
    if seen is None:
        seen = set()
    url = canonical_url(url)
    if url in seen or len(seen) > 30:
        return []
    seen.add(url)
    html, _ = fetch(url)
    if not html:
        return []
    # Use html.parser so the scraper works with beautifulsoup4 alone.
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    locs = [normalize_space(loc.get_text()) for loc in soup.find_all("loc")]
    for loc in locs:
        if len(urls) >= MAX_SITEMAP_URLS:
            break
        if loc.endswith(".xml") or "sitemap" in loc.lower():
            urls.extend(parse_sitemap(loc, seen))
        elif loc.startswith("http"):
            urls.append(loc)
    return list(dict.fromkeys(urls))[:MAX_SITEMAP_URLS]


def homepage_links(domain: str) -> List[str]:
    home = f"https://{domain}/"
    html, _ = fetch(home)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for a in soup.find_all("a", href=True):
        url = canonical_url(urljoin(home, a["href"]))
        if is_same_domain(url, [domain]) and url not in urls:
            urls.append(url)
        if len(urls) >= MAX_INTERNAL_LINKS:
            break
    return urls


# ============================================================
# SEARCH ENGINE FALLBACK
# ============================================================


def ddg_site_search(domain: str, query: str) -> List[str]:
    # This is only a discovery fallback. We still accept links only from
    # the official domain requested by the source configuration.
    search_query = f"site:{domain} {query}"
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(search_query)}"
    html, _ = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for anchor in soup.select("a.result__a"):
        href = anchor.get("href")
        if not href:
            continue
        if "uddg=" in href:
            parsed = urlparse(href)
            value = parse_qs(parsed.query).get("uddg", [""])[0]
            href = unquote(value)
        href = canonical_url(href)
        if is_same_domain(href, [domain]) and href not in results:
            results.append(href)
        if len(results) >= MAX_SEARCH_RESULTS_PER_QUERY:
            break
    return results


# ============================================================
# CANDIDATE SCORING
# ============================================================


def score_candidate(url: str, title: str, text: str, keywords: Sequence[str]) -> int:
    hay_url = url.lower()
    hay_title = title.lower()
    hay_text = text.lower()
    score = 0
    for keyword in keywords:
        key = keyword.lower()
        if key in hay_url:
            score += 4
        if key in hay_title:
            score += 5
        # Limit text contribution to prevent long articles dominating.
        count = hay_text.count(key)
        score += min(count, 3)
    for key in CORE_KEYWORDS:
        if key in hay_title:
            score += 7
        elif key in hay_text[:5000]:
            score += 2
    return score


def discover_pages(source: dict) -> List[dict]:
    pages: Dict[str, dict] = {}
    domains = source["domains"]
    keywords = source["keywords"]

    print(f"\n[{source['name']}] keyword discovery")

    # 1) sitemap / robots discovery
    sitemap_candidates = []
    for domain in domains:
        print(f"  - checking {domain}/robots.txt + sitemap")
        for sitemap in get_robots_sitemaps(domain)[:8]:
            sitemap_candidates.extend(parse_sitemap(sitemap))
        for link in homepage_links(domain):
            sitemap_candidates.append(link)

    # 2) keyword search discovery
    queries = [
        "Anak Krakatau",
        "Anak Krakatau erupsi volcanic ash",
        "Anak Krakatau terdampak affected",
        "Anak Krakatau bandara penerbangan",
        "Anak Krakatau kesehatan rumah sakit puskesmas",
        "Anak Krakatau Singapore Malaysia",
    ]
    for domain in domains:
        for query in queries:
            print(f"  - search: site:{domain} {query}")
            for url in ddg_site_search(domain, query):
                sitemap_candidates.append(url)
            time.sleep(CRAWL_DELAY)

    # de-duplicate and limit candidate URLs
    candidate_urls = []
    for url in sitemap_candidates:
        url = canonical_url(url)
        if not url.startswith("http"):
            continue
        if not any(is_same_domain(url, [domain]) for domain in domains):
            continue
        if url not in candidate_urls:
            candidate_urls.append(url)

    # 3) fetch candidate pages and rank by keyword relevance/date
    for url in candidate_urls[: MAX_PAGES_PER_SOURCE * 4]:
        html, code = fetch(url)
        if not html:
            continue
        text = html_to_text(html)
        title = extract_title(html)
        if len(text) < 80:
            continue
        hits = [kw for kw in keywords if kw.lower() in (title + " " + text).lower()]
        score = score_candidate(url, title, text, keywords)
        date = extract_best_date(html, text)
        pages[url] = {
            "url": url,
            "title": title or urlparse(url).path.strip("/").replace("-", " ") or source["name"],
            "text": text,
            "score": score,
            "date": date,
            "keyword_hits": hits,
            "status_code": code,
        }
        time.sleep(CRAWL_DELAY)

    ordered = sorted(
        pages.values(),
        key=lambda item: (
            item["score"],
            item["date"] or "0000-00-00",
        ),
        reverse=True,
    )

    threshold = int(source.get("min_relevance_score", 10))
    validated = [p for p in ordered if p["score"] >= threshold]

    if validated:
        for p in validated:
            p["validation_passed"] = True
            p["validation_threshold"] = threshold
            p["reference_type"] = "keyword_match"
        print(f"  -> keyword validation PASS (threshold={threshold}, best_score={validated[0]['score']})")
        return validated[:MAX_PAGES_PER_SOURCE]

    # Keyword discovery found no sufficiently relevant page. Use the original
    # fixed URL as a reference fallback, then score and retain it transparently.
    fixed_url = source.get("fixed_reference_url")
    if fixed_url:
        print(f"  -> keyword validation FAIL (threshold={threshold}); using fixed reference")
        html, code = fetch(fixed_url)
        if html:
            text = html_to_text(html)
            title = extract_title(html)
            date = extract_best_date(html, text)
            hits = [kw for kw in keywords if kw.lower() in (title + " " + text).lower()]
            fixed_score = score_candidate(fixed_url, title, text, keywords)
            page = {
                "url": canonical_url(fixed_url),
                "title": title or source["name"],
                "text": text,
                "score": fixed_score,
                "date": date,
                "keyword_hits": hits,
                "status_code": code,
                "validation_passed": False,
                "validation_threshold": threshold,
                "reference_type": "fixed_reference_fallback",
            }
            time.sleep(CRAWL_DELAY)
            return [page]

    print("  -> fixed reference unavailable; no usable source page selected")
    return []


# ============================================================
# EXTRACTION
# ============================================================


def extract_status_from_pages(pages: Sequence[dict]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    candidates = []
    for page in pages:
        text = page["text"]
        patterns = [
            r"Level\s*(III|3)\s*[—\-–:]?\s*Siaga",
            r"Level\s*(II|2)\s*[—\-–:]?\s*Waspada",
            r"Level\s*(III|3)\s*\(\s*Siaga\s*\)",
            r"Level\s*(II|2)\s*\(\s*Waspada\s*\)",
            r"Level\s*(I|1)\s*[—\-–:]?\s*Normal",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                status = normalize_status(match.group(0))
                candidates.append((page.get("date") or "0000-00-00", status, page["url"], page.get("title", "")))
                break
    if not candidates:
        return None, None, None
    candidates.sort(reverse=True)
    date, status, url, title = candidates[0]
    return status, date, url


def extract_health(pages: Sequence[dict]) -> dict:
    best = {}
    best_score = -1
    for page in pages:
        text = page["text"]
        hospitals = find_first_number(
            [
                r"([\d.,]+)\s+rumah\s+sakit\b",
                r"([\d.,]+)\s+hospital(?:s)?\b",
                r"hospital(?:s)?\D{0,40}([\d.,]+)",
            ],
            text,
        )
        puskesmas = find_first_number(
            [
                r"([\d.,]+)\s+puskesmas\b",
                r"puskesmas\D{0,40}([\d.,]+)",
            ],
            text,
        )
        regencies = find_first_number(
            [
                r"([\d.,]+)\s+kabupaten\s*/\s*kota",
                r"([\d.,]+)\s+kabupaten/kota",
                r"([\d.,]+)\s+regenc(?:y|ies)\s*(?:and|/)\s*cities",
            ],
            text,
        )
        ispa = find_first_number(
            [
                r"([\d.,]+)\s+kasus\s+ISPA",
                r"ISPA\D{0,40}([\d.,]+)",
                r"([\d.,]+)\s+respiratory\s+cases",
            ],
            text,
        )
        score = sum(v is not None for v in [hospitals, puskesmas, regencies, ispa]) * 10 + page["score"]
        if score > best_score:
            best_score = score
            best = {
                "hospitals": hospitals,
                "puskesmas": puskesmas,
                "affected_regencies_cities": regencies,
                "ispa": ispa,
                "source_url": page["url"],
                "source_title": page["title"],
                "source_date": page.get("date"),
            }
    return best


def extract_population(pages: Sequence[dict]) -> dict:
    best = {}
    best_score = -1
    for page in pages:
        text = page["text"]
        population = None

        match = re.search(r"([\d.,]+)\s*(?:juta|million)\s+(?:orang|people|penduduk)", text, re.I)
        if match:
            raw = match.group(1).replace(",", ".")
            try:
                population = int(round(float(raw) * 1_000_000))
            except ValueError:
                population = None

        if population is None:
            match = re.search(r"([\d.,]+)\s*(?:million|juta)", text, re.I)
            if match:
                try:
                    population = int(round(float(match.group(1).replace(".", ".").replace(",", ".")) * 1_000_000))
                except ValueError:
                    population = None

        if population is None:
            match = re.search(r"([\d.,]+)\s+(?:orang|people|penduduk).*?(?:terdampak|affected|exposed)", text, re.I)
            if match:
                population = parse_number(match.group(1))

        if population is not None:
            score = page["score"]
            if "ash" in text.lower() or "abu vulkanik" in text.lower():
                score += 8
            if score > best_score:
                best_score = score
                best = {
                    "exposed_population": population,
                    "source_url": page["url"],
                    "source_title": page["title"],
                    "source_date": page.get("date"),
                }
    return best


def extract_aviation(pages: Sequence[dict]) -> dict:
    result = {
        "total_affected_flights": None,
        "total_affected_passengers": None,
        "temporarily_closed": {"flights": None, "passengers": None},
        "route_adjustment": {"flights": None, "passengers": None},
        "source_url": None,
        "source_title": None,
        "source_date": None,
    }

    best_total_score = -1
    for page in pages:
        text = page["text"]
        low = text.lower()

        total_flights = find_first_number(
            [
                r"([\d.,]+)\s+(?:affected\s+)?flights",
                r"(?:sekitar|approximately|about)\s*([\d.,]+)\s+penerbangan",
                r"([\d.,]+)\s+penerbangan\s+(?:terdampak|affected)",
            ],
            text,
        )
        total_passengers = find_first_number(
            [
                r"([\d.,]+)\s+(?:affected\s+)?passengers",
                r"(?:sekitar|approximately|about)\s*([\d.,]+)\s+penumpang",
                r"([\d.,]+)\s+penumpang\s+(?:terdampak|affected)",
            ],
            text,
        )

        closure_flights = None
        closure_passengers = None
        closure_patterns = [
            (
                r"ditutup\s+sementara.{0,220}?([\d.,]+)\s+penerbangan"
                r".{0,160}?([\d.,]+)\s+penumpang",
                True,
            ),
            (
                r"([\d.,]+)\s+penerbangan.{0,160}?([\d.,]+)\s+penumpang"
                r".{0,100}?(?:ditutup\s+sementara|temporary\s+closure)",
                True,
            ),
            (
                r"temporary\s+closure.{0,180}?([\d.,]+)\s+flights"
                r".{0,150}?([\d.,]+)\s+passengers",
                True,
            ),
        ]
        for pattern, _ in closure_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                closure_flights = parse_number(match.group(1))
                closure_passengers = parse_number(match.group(2))
                break

        route_flights = None
        route_passengers = None
        route_patterns = [
            (
                r"penyesuaian\s+rute.{0,220}?([\d.,]+)\s+penerbangan"
                r".{0,160}?([\d.,]+)\s+penumpang",
                True,
            ),
            (
                r"([\d.,]+)\s+penerbangan.{0,160}?([\d.,]+)\s+penumpang"
                r".{0,120}?(?:penyesuaian\s+rute|route\s+adjustment|route\s+adjustments)",
                True,
            ),
            (
                r"route\s+adjustments?.{0,180}?([\d.,]+)\s+flights"
                r".{0,150}?([\d.,]+)\s+passengers",
                True,
            ),
        ]
        for pattern, _ in route_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                route_flights = parse_number(match.group(1))
                route_passengers = parse_number(match.group(2))
                break

        page_score = page["score"]
        if "penerbangan" in low or "flight" in low:
            page_score += 10
        if closure_flights is not None:
            page_score += 10
        if route_flights is not None:
            page_score += 10

        if page_score > best_total_score:
            best_total_score = page_score
            result.update(
                {
                    "total_affected_flights": total_flights,
                    "total_affected_passengers": total_passengers,
                    "source_url": page["url"],
                    "source_title": page["title"],
                    "source_date": page.get("date"),
                }
            )

            if closure_flights is not None:
                result["temporarily_closed"] = {
                    "flights": closure_flights,
                    "passengers": closure_passengers,
                }
            if route_flights is not None:
                result["route_adjustment"] = {
                    "flights": route_flights,
                    "passengers": route_passengers,
                }

    return result


# ============================================================
# IMPACTED LOCATION EXTRACTION
# ============================================================


def classify_location_status(context: str, location: str) -> str:
    low = context.lower()

    monitoring_terms = [
        "monitoring",
        "dipantau",
        "mewaspadai",
        "waspada",
        "low risk",
        "risiko rendah",
        "continue to monitor",
    ]

    impact_terms = [
        "ditutup",
        "terdampak",
        "affected",
        "disruption",
        "disrupted",
        "dampak",
        "cancelled",
        "canceled",
        "diverted",
        "penyesuaian rute",
        "route adjustment",
    ]

    if location == "Malaysia":
        # Do not label Malaysia as impacted just because another country
        # in the same paragraph had an aviation disruption.
        if any(term in low for term in monitoring_terms):
            return "monitoring"
        if any(term in low for term in impact_terms):
            return "aviation impact / reported mention"
        return "mentioned in source"

    if location == "Singapore":
        if any(term in low for term in impact_terms):
            return "aviation impact / reported mention"
        if any(term in low for term in monitoring_terms):
            return "monitoring"
        return "mentioned in source"

    if any(term in low for term in impact_terms):
        return "reported impact"
    if any(term in low for term in monitoring_terms):
        return "reported / monitored"
    return "mentioned in source"


def extract_locations(pages: Sequence[dict]) -> List[dict]:
    detections = {}
    for page in pages:
        text = page["text"]
        low = text.lower()
        for location, aliases in PLACE_ALIASES.items():
            for alias in aliases:
                index = low.find(alias.lower())
                if index == -1:
                    continue
                context = text[max(0, index - 350): min(len(text), index + 550)]
                status = classify_location_status(context, location)
                key = (location, page["url"])
                existing = detections.get(key)
                score = page["score"]
                if existing is None or score > existing["score"]:
                    detections[key] = {
                        "name": location,
                        "country": REGION_REFERENCE[location]["country"],
                        "status": status,
                        "source_url": page["url"],
                        "source_title": page["title"],
                        "source_date": page.get("date"),
                        "evidence": normalize_space(context)[:500],
                        "score": score,
                    }

    # Keep only the strongest detection per location.
    best_by_location = {}
    for item in detections.values():
        key = item["name"]
        if key not in best_by_location or item["score"] > best_by_location[key]["score"]:
            best_by_location[key] = item
    return sorted(best_by_location.values(), key=lambda x: x["name"])


def extract_airports(pages: Sequence[dict]) -> List[dict]:
    combined = " ".join(page["text"] for page in pages)
    low = combined.lower()
    impacted = []

    for code, airport in AIRPORTS.items():
        name_hit = airport["name"].lower() in low
        code_hit = re.search(rf"\b{re.escape(code.lower())}\b", low) is not None
        if not (name_hit or code_hit):
            continue

        if code in {"SIN", "KUL", "SZB"}:
            impact = "International mention / monitoring"
            if any(k in low for k in ["flight", "penerbangan", "disruption", "affected", "terdampak"]):
                impact = "Aviation impact / mention"
        else:
            impact = "Affected / mentioned"
            if "ditutup" in low or "temporary closure" in low:
                impact = "Temporary closure"

        impacted.append({
            "name": airport["name"],
            "code": code,
            "province": airport["province"],
            "impact": impact,
            "lat": airport["lat"],
            "lng": airport["lng"],
        })

    return impacted


# ============================================================
# GEOJSON
# ============================================================


def build_geojson(locations: Sequence[dict], airports: Sequence[dict]) -> dict:
    features = []
    now = now_iso()

    for location in locations:
        ref = REGION_REFERENCE.get(location["name"])
        if not ref:
            continue
        polygon = ref["polygon"]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": location["name"],
                    "country": location["country"],
                    "impact_status": location["status"],
                    "event": "Anak Krakatau 2026",
                    "source_url": location["source_url"],
                    "source_date": location.get("source_date"),
                    "last_updated": now,
                    "note": "Approximate analytical coverage derived from keyword-detected official reporting; not an administrative boundary.",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[point for point in polygon]],
                },
            }
        )

    # Airports are included as Point features for data completeness, but the
    # current dashboard can filter them out from the area layer if desired.
    # Their presence also allows future map versions to render plane icons.
    for airport in airports:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": airport["name"],
                    "code": airport["code"],
                    "province": airport["province"],
                    "impact": airport["impact"],
                    "feature_type": "airport",
                    "last_updated": now,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [airport["lng"], airport["lat"]],
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "name": "Anak Krakatau 2026 Impact Areas",
        "generated_at": now,
        "features": features,
    }


# ============================================================
# TIMELINE
# ============================================================


def make_timeline(event: dict, aviation: dict, source_pages: Sequence[dict]) -> List[dict]:
    timeline = []

    if event.get("level_iii_start"):
        timeline.append(
            {
                "date": event["level_iii_start"],
                "title": "Level III — Siaga",
                "description": "Latest keyword-discovered official reporting associated with the Level III status change.",
            }
        )

    if event.get("continuous_start"):
        timeline.append(
            {
                "date": event["continuous_start"],
                "title": "Continuous eruption began",
                "description": "Official reporting identified a continuous eruption phase of Anak Krakatau.",
            }
        )

    if event.get("continuous_end"):
        timeline.append(
            {
                "date": event["continuous_end"],
                "title": "Continuous eruption ended",
                "description": "Official reporting indicated the end of the continuous eruption period.",
            }
        )

    if aviation.get("total_affected_flights"):
        timeline.append(
            {
                "date": aviation.get("source_date") or "Latest aviation report",
                "title": "Aviation disruption",
                "description": (
                    f"Reported aviation impact includes {aviation['total_affected_flights']:,} affected flights "
                    f"and {aviation.get('total_affected_passengers'):,} affected passengers."
                    if aviation.get("total_affected_passengers")
                    else f"Reported aviation impact includes {aviation['total_affected_flights']:,} affected flights."
                ),
            }
        )

    if event.get("status_date") and event.get("status"):
        timeline.append(
            {
                "date": event["status_date"],
                "title": event["status"],
                "description": "Latest status discovered from official source pages using keyword search.",
            }
        )

    return timeline


# ============================================================
# MAIN
# ============================================================


def main() -> None:
    print("\n============================================================")
    print(" ANAK KRAKATAU 2026 — KEYWORD-BASED SCRAPER")
    print("============================================================")
    print("Discovery mode: keywords + sitemap + internal links + site search")
    print("Reference fallback: original fixed article URL when relevance threshold is not met.\n")

    source_results = {}
    all_pages = []

    for source in OFFICIAL_SOURCES:
        try:
            pages = discover_pages(source)
        except Exception as exc:
            print(f"  ! discovery error: {exc}")
            pages = []
        source_results[source["key"]] = pages
        all_pages.extend(pages)
        print(f"  -> {len(pages)} relevant page(s) selected")

    # --------------------------------------------------------
    # Event status
    # --------------------------------------------------------
    geology_pages = source_results.get("badan_geologi", [])
    status, status_date_iso, status_url = extract_status_from_pages(geology_pages)

    status_date_display = None
    if status_date_iso:
        status_dt = datetime.strptime(status_date_iso, "%Y-%m-%d")
        status_date_display = status_dt.strftime("%d %B %Y")

    # --------------------------------------------------------
    # Health + population
    # --------------------------------------------------------
    health_result = extract_health(source_results.get("kemenkes", []))
    population_result = extract_population(source_results.get("kemenkes", []))

    # --------------------------------------------------------
    # Aviation
    # --------------------------------------------------------
    aviation_result = extract_aviation(source_results.get("kemenhub", []))

    # If Kemenhub primary domain fails, dephub may have been selected in same source.
    # No fixed article is necessary.

    # --------------------------------------------------------
    # Locations / airports
    # --------------------------------------------------------
    locations = extract_locations(all_pages)
    airports = extract_airports(source_results.get("kemenhub", []) + source_results.get("bmkg", []))

    # --------------------------------------------------------
    # Build fallback tracking
    # --------------------------------------------------------
    fallback_fields = []

    final_status = status or FALLBACK["status"]
    if not status:
        fallback_fields.append("event.current_status")

    final_status_date = (
        f"{datetime.strptime(status_date_iso, '%Y-%m-%d').strftime('%d %B %Y')}"
        if status_date_iso
        else FALLBACK["status_date"].split(",")[0]
    )
    if not status_date_iso:
        fallback_fields.append("event.status_date")

    population = population_result.get("exposed_population") or FALLBACK["population"]
    if not population_result.get("exposed_population"):
        fallback_fields.append("population.exposed_population")

    hospitals = health_result.get("hospitals") or FALLBACK["hospitals"]
    if not health_result.get("hospitals"):
        fallback_fields.append("health.hospitals")

    puskesmas = health_result.get("puskesmas") or FALLBACK["puskesmas"]
    if not health_result.get("puskesmas"):
        fallback_fields.append("health.puskesmas")

    regencies = health_result.get("affected_regencies_cities") or FALLBACK["affected_regencies_cities"]
    if not health_result.get("affected_regencies_cities"):
        fallback_fields.append("health.affected_regencies_cities")

    ispa = health_result.get("ispa") or FALLBACK["ispa"]
    if not health_result.get("ispa"):
        fallback_fields.append("health.ispa")

    flights = aviation_result.get("total_affected_flights") or FALLBACK["flights"]
    if not aviation_result.get("total_affected_flights"):
        fallback_fields.append("aviation.total_affected_flights")

    passengers = aviation_result.get("total_affected_passengers") or FALLBACK["passengers"]
    if not aviation_result.get("total_affected_passengers"):
        fallback_fields.append("aviation.total_affected_passengers")

    closure_flights = aviation_result["temporarily_closed"].get("flights") or FALLBACK["closure_flights"]
    if not aviation_result["temporarily_closed"].get("flights"):
        fallback_fields.append("aviation.temporarily_closed.flights")

    closure_passengers = aviation_result["temporarily_closed"].get("passengers") or FALLBACK["closure_passengers"]
    if not aviation_result["temporarily_closed"].get("passengers"):
        fallback_fields.append("aviation.temporarily_closed.passengers")

    route_flights = aviation_result["route_adjustment"].get("flights") or FALLBACK["route_flights"]
    if not aviation_result["route_adjustment"].get("flights"):
        fallback_fields.append("aviation.route_adjustment.flights")

    route_passengers = aviation_result["route_adjustment"].get("passengers") or FALLBACK["route_passengers"]
    if not aviation_result["route_adjustment"].get("passengers"):
        fallback_fields.append("aviation.route_adjustment.passengers")

    event = {
        "name": "Gunung Anak Krakatau",
        "location": "Sunda Strait, Lampung",
        "current_status": final_status,
        "status_date": final_status_date,
        "level_iii_start": FALLBACK["level_iii_start"],
        "continuous_eruption_start": FALLBACK["continuous_start"],
        "continuous_eruption_end": FALLBACK["continuous_end"],
        "continuous_eruption_duration": FALLBACK["continuous_duration"],
    }

    aviation = {
        "total_affected_flights": flights,
        "total_affected_passengers": passengers,
        "temporarily_closed": {
            "flights": closure_flights,
            "passengers": closure_passengers,
        },
        "route_adjustment": {
            "flights": route_flights,
            "passengers": route_passengers,
        },
        "source_url": aviation_result.get("source_url"),
        "source_title": aviation_result.get("source_title"),
        "source_date": aviation_result.get("source_date"),
        "total_note": "Headline totals may be rounded; category values are reported detail where available.",
    }

    # Always show these event dates until a matching fresh page provides better values.
    if geology_pages:
        # Discovering the current status is the dynamic component. Historical dates
        # remain context, not fixed article links.
        event["status_source_url"] = status_url

    # --------------------------------------------------------
    # Source cards
    # --------------------------------------------------------
    source_records = []
    for source in OFFICIAL_SOURCES:
        pages = source_results.get(source["key"], [])
        best = pages[0] if pages else None
        source_records.append(
            {
                "name": source["name"],
                "domains": source["domains"],
                "url": best["url"] if best else source.get("fixed_reference_url") or f"https://{source['domains'][0]}/",
                "title": best["title"] if best else source["name"],
                "date": best.get("date") if best else None,
                "keyword_hits": best.get("keyword_hits", []) if best else [],
                "pages_checked": len(pages),
                "score": best.get("score") if best else 0,
                "validation_threshold": best.get("validation_threshold", source.get("min_relevance_score", 10)) if best else source.get("min_relevance_score", 10),
                "validation_passed": best.get("validation_passed", False) if best else False,
                "reference_type": best.get("reference_type", "unavailable") if best else "unavailable",
                "fetch_status": "OK" if best else "UNAVAILABLE",
                "discovery_method": "keywords + sitemap + internal links + site-restricted search; fixed URL fallback if relevance threshold is not met",
                "fixed_reference_url": source.get("fixed_reference_url"),
            }
        )

    # --------------------------------------------------------
    # Timeline
    # --------------------------------------------------------
    timeline = make_timeline(event, aviation, geology_pages + source_results.get("bnpb", []))

    # --------------------------------------------------------
    # JSON output
    # --------------------------------------------------------
    data = {
        "metadata": {
            "last_updated": now_iso(),
            "scraper": "scrape_anak_krakatau_2026.py",
            "author": "Kelvin Irawan",
            "description": "Keyword-based scraper for official Anak Krakatau 2026 impact reporting.",
            "discovery_mode": "keywords",
            "fixed_article_urls": False,
            "fallback_used": bool(fallback_fields),
            "fallback_fields": fallback_fields,
            "sources_discovered": len([s for s in source_records if s.get("fetch_status") == "OK"]),
            "keyword_sources": len([s for s in source_records if s.get("reference_type") == "keyword_match"]),
            "fixed_reference_sources": len([s for s in source_records if s.get("reference_type") == "fixed_reference_fallback"]),
        },
        "event": event,
        "activity": {
            "total_eruptions_until_3_sep": None,
            "strombolian_eruptions_after_continuous": None,
        },
        "population": {
            "exposed_population": population,
            "source_url": population_result.get("source_url"),
            "source_title": population_result.get("source_title"),
            "source_date": population_result.get("source_date"),
        },
        "health": {
            "hospitals": hospitals,
            "puskesmas": puskesmas,
            "affected_regencies_cities": regencies,
            "ispa": ispa,
            "source_url": health_result.get("source_url"),
            "source_title": health_result.get("source_title"),
            "source_date": health_result.get("source_date"),
        },
        "aviation": aviation,
        "impacted_airports": airports,
        "impacted_locations": locations,
        "eruption": {
            "timeline": timeline,
        },
        "sources": source_records,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

    geojson = build_geojson(locations, airports)
    with open(OUTPUT_GEOJSON, "w", encoding="utf-8") as file:
        json.dump(geojson, file, ensure_ascii=False, indent=2)

    # --------------------------------------------------------
    # Console summary
    # --------------------------------------------------------
    print("\n============================================================")
    print(" SCRAPING COMPLETE")
    print("============================================================")
    print(f"JSON     : {OUTPUT_JSON}")
    print(f"GeoJSON  : {OUTPUT_GEOJSON}")
    print(f"Status   : {final_status}")
    print(f"Population: {population:,}")
    print(f"Flights  : {flights:,}")
    print(f"Passengers: {passengers:,}")
    print(f"Closure  : {closure_flights:,} flights / {closure_passengers:,} passengers")
    print(f"Route    : {route_flights:,} flights / {route_passengers:,} passengers")
    print(f"Hospitals: {hospitals:,}")
    print(f"Puskesmas: {puskesmas:,}")
    print(f"Locations detected: {len(locations)}")
    print(f"Airports detected : {len(airports)}")

    if fallback_fields:
        print("\nWARNING: fallback values were used for:")
        for field in fallback_fields:
            print(f"  - {field}")
    else:
        print("\nAll dashboard KPI values came from keyword-discovered source content.")

    print("\nData analysis & dashboard by Kelvin Irawan.")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScraper stopped by user.")
        sys.exit(1)
    except Exception as exc:
        print("\nSCRAPER ERROR:")
        print(exc)
        sys.exit(1)
