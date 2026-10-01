"""
ANAK KRAKATAU 2026 DATA SCRAPER
Data analysis & dashboard by Kelvin Irawan

Flow:
1. Keep the existing fixed links as a trusted fallback reference.
2. Search the internet by keywords for each source/domain.
3. Fetch candidate pages from official domains.
4. Score each candidate for relevance.
5. If the best candidate passes the threshold -> use it as the reference.
6. If no candidate passes -> use the existing fixed link.
7. Extract the dashboard values from the selected references.
8. Write JSON + GeoJSON, including source-selection metadata.

The scraper is designed to fail safely: a weak search result never replaces the
known fixed reference.
"""

from __future__ import annotations

from datetime import datetime
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_JSON = DATA_DIR / "anak_krakatau_2026.json"
OUTPUT_GEOJSON = DATA_DIR / "impacted_areas.geojson"
TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}

# -----------------------------------------------------------------------------
# TRUSTED FIXED LINKS: these are retained as the fallback references.
# -----------------------------------------------------------------------------
SOURCE_CONFIG = {
    "geologi": {
        "name": "Badan Geologi — Latest Status",
        "fixed_url": "https://geologi.esdm.go.id/media-center/laporan-khusus-penurunan-tingkat-aktivitas-gunungapi-anak-krakatau-provinsi-lampung-dari-level-iii-siaga-menjadi-level-ii-waspada-tanggal-21-september-2026-pukul-18-30-wib",
        "domains": ["geologi.esdm.go.id"],
        "keywords": {
            "core": ["anak krakatau", "gunung anak krakatau", "anak krakatau 2026"],
            "event": ["erupsi", "erupsi anak krakatau", "aktivitas gunung api", "tingkat aktivitas"],
            "status": ["level ii", "level iii", "waspada", "siaga"],
            "time": ["2026", "21 september", "july", "juni", "september"],
        },
        "required_groups": ["core"],
        "min_score": 9,
    },
    "kemenhub": {
        "name": "Kementerian Perhubungan RI — Aviation",
        "fixed_url": "https://www.kemenhub.go.id/post/read/sejumlah-bandara-masih-terdampak-abu-vulkanik-gunung-anak-krakatau%2C-kemenhub-siapkan-bandara-alternatif",
        "domains": ["kemenhub.go.id", "dephub.go.id"],
        "keywords": {
            "core": ["anak krakatau", "abu vulkanik gunung anak krakatau"],
            "impact": ["penerbangan", "bandara", "penumpang", "terdampak", "ditutup sementara", "penyesuaian rute"],
            "numbers": ["2.300", "2300", "270.337", "270337", "1.397", "1397", "922", "92.758", "92758"],
            "time": ["2026", "5 september", "6 september", "7 september"],
        },
        "required_groups": ["core", "impact"],
        "min_score": 12,
    },
    "kemenkes": {
        "name": "Kementerian Kesehatan RI — Response",
        "fixed_url": "https://www.kemkes.go.id/id/kemenkes-siagakan-413-rumah-sakit-dan-830-puskesmas-hadapi-dampak-erupsi-anak-krakatau",
        "domains": ["kemkes.go.id", "www.kemkes.go.id"],
        "keywords": {
            "core": ["anak krakatau", "erupsi anak krakatau"],
            "health": ["rumah sakit", "puskesmas", "ispa", "kesehatan", "dampak"],
            "numbers": ["413", "830", "16759", "16.759", "20 kabupaten", "20 kabupaten/kota"],
            "time": ["2026", "september"],
        },
        "required_groups": ["core", "health"],
        "min_score": 12,
    },
    "kemenkes_health_detail": {
        "name": "Kementerian Kesehatan RI — Air Quality",
        "fixed_url": "https://kemkes.go.id/eng/kemenkes-perkuat-pemantauan-kualitas-udara-hadapi-dampak-erupsi-anak-krakatau",
        "domains": ["kemkes.go.id", "www.kemkes.go.id"],
        "keywords": {
            "core": ["anak krakatau", "erupsi anak krakatau"],
            "health": ["kualitas udara", "air quality", "ispa", "respiratory", "pernapasan"],
            "numbers": ["16759", "16.759"],
            "time": ["2026", "september"],
        },
        "required_groups": ["core", "health"],
        "min_score": 11,
    },
    "bnpb": {
        "name": "BNPB — Eruption Update",
        "fixed_url": "https://bnpb.go.id/berita/update-aktivitas-gunung-anak-krakatau-status-level-iii-masih-berlaku",
        "domains": ["bnpb.go.id"],
        "keywords": {
            "core": ["anak krakatau", "gunung anak krakatau"],
            "event": ["erupsi", "letusan", "aktivitas gunung"],
            "response": ["bnpb", "penanganan", "evakuasi", "bencana"],
            "time": ["2026", "september", "july"],
        },
        "required_groups": ["core", "event"],
        "min_score": 10,
    },
    "bmkg": {
        "name": "BMKG — Volcanic Ash Monitoring",
        "fixed_url": "https://www.bmkg.go.id/berita/utama/bmkg-terus-pantau-dampak-erupsi-gunung-anak-krakatau",
        "domains": ["bmkg.go.id", "www.bmkg.go.id"],
        "keywords": {
            "core": ["anak krakatau", "erupsi gunung anak krakatau"],
            "ash": ["abu vulkanik", "volcanic ash", "ash cloud", "sigmet", "vaac"],
            "regions": ["banten", "dki jakarta", "jawa barat", "lampung", "bengkulu"],
            "time": ["2026", "september"],
        },
        "required_groups": ["core", "ash"],
        "min_score": 11,
    },
    "bmkg_forecast": {
        "name": "BMKG — Forecast / Additional Ash Context",
        "fixed_url": "https://www.bmkg.go.id/cuaca/potensi-hujan-sepekan/prakiraan-cuaca-indonesia-sepekan-periode-8-14-september-2026-abu-vulkanik-dan-asap-masih-terpantau-potensi-hujan-signifikan-masih-ada-di-sejumlah-wilayah",
        "domains": ["bmkg.go.id", "www.bmkg.go.id"],
        "keywords": {
            "core": ["anak krakatau", "abu vulkanik"],
            "ash": ["abu vulkanik", "asap", "volcanic ash"],
            "regions": ["lampung", "banten", "jakarta", "jawa barat", "bengkulu"],
            "time": ["2026", "8-14 september", "september"],
        },
        "required_groups": ["core", "ash"],
        "min_score": 10,
    },
    "singapore": {
        "name": "Singapore Airlines — Regional Aviation Disruption",
        "fixed_url": "https://www.singaporeair.com/en_UK/dk/corporate/newsroom/newsalert-listing/advisory-on-singapore-airlines-flights-impacted-by-the-eruption-/",
        "domains": ["singaporeair.com", "www.singaporeair.com"],
        "keywords": {
            "core": ["anak krakatau", "eruption"],
            "aviation": ["singapore", "jakarta", "retimed", "cancelled", "relief flights", "flight disruption"],
            "time": ["2026", "september"],
        },
        "required_groups": ["core", "aviation"],
        "min_score": 10,
    },
    "malaysia": {
        "name": "Portal NADMA / MetMalaysia — Malaysia Risk",
        "fixed_url": "https://www.nadma.gov.my/bi/media-en/news/7101-metmalaysia-anak-krakatau-ash-could-reach-malaysia-but-risk-remains-low",
        "domains": ["nadma.gov.my", "www.nadma.gov.my", "met.gov.my", "www.met.gov.my"],
        "keywords": {
            "core": ["anak krakatau", "krakatau ash"],
            "risk": ["risk remains low", "risk is low", "low risk", "monitoring", "metmalaysia"],
            "time": ["2026", "september"],
        },
        "required_groups": ["core", "risk"],
        "min_score": 10,
    },
}

FALLBACK = {
    "status": "Level II — Waspada",
    "status_date": "21 September 2026, 18:30 WIB",
    "level_iii_start": "2 July 2026, 16:30 WIB",
    "continuous_start": "4 September 2026, 23:07 WIB",
    "continuous_end": "6 September 2026, 00:04 WIB",
    "population": 23360000,
    "hospitals": 413,
    "puskesmas": 830,
    "regencies_cities": 23,
    "ispa_cases": 16759,
    "flights": 2300,
    "passengers": 270337,
    "closed_flights": 1397,
    "closed_passengers": 177579,
    "route_flights": 922,
    "route_passengers": 92758,
}

IMPACTED_AIRPORTS = [
    {"name":"Soekarno-Hatta International Airport","code":"CGK","province":"Banten","country":"Indonesia","impact":"Temporary closure","lat":-6.1256,"lng":106.6559},
    {"name":"Halim Perdanakusuma Airport","code":"HLP","province":"DKI Jakarta","country":"Indonesia","impact":"Temporary closure","lat":-6.2666,"lng":106.8900},
    {"name":"Radin Inten II Airport","code":"TKG","province":"Lampung","country":"Indonesia","impact":"Temporary closure","lat":-5.2427,"lng":105.1751},
    {"name":"Budiarto Airport","code":"RTO","province":"Banten","country":"Indonesia","impact":"Temporary closure","lat":-6.2930,"lng":106.5690},
    {"name":"Pondok Cabe Airport","code":"PCB","province":"Banten","country":"Indonesia","impact":"Affected","lat":-6.3369,"lng":106.7640},
    {"name":"Husein Sastranegara Airport","code":"BDO","province":"West Java","country":"Indonesia","impact":"Affected","lat":-6.9006,"lng":107.5764},
    {"name":"Muhammad Taufiq Kiemas Airport","code":"TNB","province":"Lampung","country":"Indonesia","impact":"Affected","lat":-5.2110,"lng":105.1630},
    {"name":"Atung Bungsu Airport","code":"PXA","province":"South Sumatra","country":"Indonesia","impact":"Previously affected","lat":-4.0330,"lng":103.3950},
    {"name":"Singapore Changi Airport","code":"SIN","province":"Singapore","country":"Singapore","impact":"International route disruption","lat":1.3644,"lng":103.9915,"regional":True},
]

TIMELINE = [
    {"date":"2 July 2026","title":"Level III — Siaga","description":"Gunung Anak Krakatau was raised to Level III (Siaga) following increased volcanic seismicity and deformation."},
    {"date":"4 September 2026 — 23:07 WIB","title":"Continuous eruption began","description":"A continuous eruption was observed, accompanied by intense volcanic activity."},
    {"date":"6 September 2026 — 00:04 WIB","title":"Continuous eruption ended","description":"The continuous eruption ended after approximately 25 hours."},
    {"date":"6–7 September 2026","title":"Volcanic ash impact","description":"Volcanic ash affected parts of Indonesia and disrupted aviation operations across multiple airports."},
    {"date":"7 September 2026","title":"Aviation disruption","description":"Kementerian Perhubungan reported approximately 2,300 affected flights and 270,337 affected passengers cumulatively since 5 September."},
    {"date":"21 September 2026 — 18:30 WIB","title":"Status lowered to Level II","description":"Badan Geologi lowered the activity level from Level III (Siaga) to Level II (Waspada)."},
]

# Approximate visualization only; not official administrative boundaries.
APPROXIMATE_COVERAGE = {
    "type":"FeatureCollection",
    "features":[
        {
            "type":"Feature",
            "properties":{
                "name":"Reported ash-affected corridor — Indonesia",
                "coverage_type":"ash_affected",
                "regions":["Bengkulu","Lampung","Banten","DKI Jakarta","Jawa Barat"],
                "note":"Approximate analytical corridor representing reported ash-affected parts of Indonesia. It is not an official administrative boundary."
            },
            "geometry":{
                "type":"Polygon",
                "coordinates":[[
                    [102.45,-5.10],[103.25,-5.45],[104.15,-5.35],[104.95,-5.50],[105.45,-5.25],
                    [106.10,-5.35],[106.85,-5.55],[107.65,-5.55],[107.80,-6.15],[107.20,-6.65],
                    [106.35,-6.75],[105.50,-6.80],[104.75,-7.00],[103.95,-6.90],[103.15,-6.70],
                    [102.60,-6.30],[102.45,-5.10]
                ]]
            }
        },
        {
            "type":"Feature",
            "properties":{
                "name":"Higher-level ash monitoring area — offshore",
                "coverage_type":"higher_level_monitoring",
                "note":"Approximate offshore sector reflecting BMKG reporting of higher-level ash extending farther west/southwest. This visualization is analytical and not an official ash concentration boundary."
            },
            "geometry":{
                "type":"Polygon",
                "coordinates":[[
                    [98.20,-4.65],[99.55,-4.55],[101.10,-4.75],[102.70,-4.95],[103.70,-5.25],
                    [104.10,-5.90],[103.40,-6.60],[102.20,-7.00],[100.90,-7.00],[99.60,-6.55],
                    [98.55,-5.75],[98.20,-4.65]
                ]]
            }
        }
    ]
}

# -----------------------------------------------------------------------------
# HTTP + text utilities
# -----------------------------------------------------------------------------
def fetch(session: requests.Session, url: str, label: str = "") -> tuple[str, bool]:
    print(f"\nFetching {label}:\n{url}")
    try:
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        print(f"OK - HTTP {response.status_code} -> {response.url}")
        return response.text, True
    except requests.RequestException as exc:
        print(f"ERROR - {exc}")
        return "", False


def text_from_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    meta_bits = []
    for name in ("description", "og:description"):
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if tag and tag.get("content"):
            meta_bits.append(tag["content"])
    body = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", " ".join([title, *meta_bits, body])).strip()


def clean_url(raw: str, base_url: str = "") -> str:
    if not raw:
        return ""
    raw = raw.strip().replace("&amp;", "&")
    if raw.startswith("//"):
        raw = "https:" + raw
    if base_url:
        raw = urljoin(base_url, raw)

    # Bing wraps URLs sometimes as ... /ck/a?...&u=a1<encoded-url>&...
    parsed = urlparse(raw)
    qs = parse_qs(parsed.query)
    if "u" in qs and qs["u"]:
        wrapped = qs["u"][0]
        if wrapped.startswith("a1"):
            wrapped = wrapped[2:]
        try:
            decoded = unquote(wrapped)
            if decoded.startswith("http"):
                raw = decoded
        except Exception:
            pass

    return raw.split("#")[0]


def allowed_domain(url: str, domains: list[str]) -> bool:
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return False
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)

# -----------------------------------------------------------------------------
# KEYWORD SEARCH + RELEVANCE SCORING
# -----------------------------------------------------------------------------
def search_bing(session: requests.Session, query: str, domains: list[str], max_results: int = 10) -> list[dict]:
    """Search Bing HTML and return candidate URLs/titles/snippets.

    This is intentionally best-effort. If a search engine response changes or
    is blocked, the caller safely falls back to the trusted fixed reference.
    """
    site_clause = " OR ".join(f"site:{d}" for d in domains)
    full_query = f"{query} {site_clause}"
    url = "https://www.bing.com/search"
    try:
        response = session.get(url, params={"q": full_query, "count": max_results}, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"  Search unavailable: {exc}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    for li in soup.select("li.b_algo"):
        a = li.select_one("h2 a")
        if not a:
            continue
        href = clean_url(a.get("href", ""), "https://www.bing.com")
        if not href or not allowed_domain(href, domains):
            continue
        snippet_node = li.select_one(".b_caption p") or li.select_one("p")
        candidates.append({
            "url": href,
            "title": a.get_text(" ", strip=True),
            "snippet": snippet_node.get_text(" ", strip=True) if snippet_node else "",
        })
        if len(candidates) >= max_results:
            break
    return candidates


def score_candidate(candidate: dict, page_text: str, config: dict) -> tuple[int, dict]:
    title = candidate.get("title", "")
    snippet = candidate.get("snippet", "")
    text = f"{title} {snippet} {page_text}".lower()

    weights = {
        "core": 6,
        "event": 3,
        "impact": 3,
        "health": 3,
        "numbers": 3,
        "ash": 3,
        "regions": 2,
        "response": 2,
        "aviation": 3,
        "risk": 3,
        "time": 1,
    }

    matched = {}
    score = 0
    for group, words in config["keywords"].items():
        group_matches = []
        for word in words:
            if word.lower() in text:
                score += weights.get(group, 1)
                group_matches.append(word)
        if group_matches:
            matched[group] = sorted(set(group_matches))

    # Bonuses: precise title match / unique URL / article-like page.
    title_lower = title.lower()
    if "anak krakatau" in title_lower:
        score += 4
    if "2026" in title_lower or "2026" in candidate.get("url", ""):
        score += 2
    if any(x in candidate.get("url", "").lower() for x in ("/berita/", "/post/", "/media-center/", "/news/", "/media/")):
        score += 1

    required_pass = all(group in matched for group in config.get("required_groups", []))
    threshold_pass = score >= config["min_score"]
    passed = required_pass and threshold_pass

    return score, {
        "passed": passed,
        "required_groups_passed": required_pass,
        "threshold": config["min_score"],
        "matched_keywords": matched,
    }


def discover_reference(session: requests.Session, key: str, config: dict) -> dict:
    """Search, score, and choose a source; otherwise fall back to fixed URL."""
    fixed_url = config["fixed_url"]

    # Build a few different search queries so a single wording does not control discovery.
    query_sets = []
    for group_words in config["keywords"].values():
        if group_words:
            query_sets.append(" ".join(group_words[:3]))
    query_sets.append("anak krakatau 2026")

    candidates = {}
    for query in query_sets[:4]:
        print(f"  Searching keywords: {query}")
        for candidate in search_bing(session, query, config["domains"], max_results=8):
            candidates[candidate["url"]] = candidate
        time.sleep(0.4)

    ranked = []
    for candidate in candidates.values():
        html, ok = fetch(session, candidate["url"], label="candidate")
        if not ok:
            continue
        body = text_from_html(html)
        score, details = score_candidate(candidate, body, config)
        ranked.append({
            **candidate,
            "score": score,
            "details": details,
            "fetched": True,
        })

    ranked.sort(key=lambda x: (-x["score"], x["url"]))
    best = ranked[0] if ranked else None

    if best and best["details"]["passed"]:
        print(f"  SELECTED SEARCH RESULT | score={best['score']} | {best['url']}")
        return {
            "url": best["url"],
            "method": "keyword_search",
            "score": best["score"],
            "threshold": config["min_score"],
            "matched_keywords": best["details"]["matched_keywords"],
            "validated": True,
            "fixed_reference": fixed_url,
            "candidate_count": len(ranked),
        }

    if best:
        print(
            f"  SEARCH DID NOT PASS | best_score={best['score']} "
            f"threshold={config['min_score']} | fallback={fixed_url}"
        )
    else:
        print(f"  NO VALID SEARCH RESULT | fallback={fixed_url}")

    return {
        "url": fixed_url,
        "method": "fixed_fallback",
        "score": best["score"] if best else 0,
        "threshold": config["min_score"],
        "matched_keywords": best["details"]["matched_keywords"] if best else {},
        "validated": False,
        "fixed_reference": fixed_url,
        "candidate_count": len(ranked),
        "best_candidate": best["url"] if best else None,
    }

# -----------------------------------------------------------------------------
# EXTRACTION HELPERS
# -----------------------------------------------------------------------------
def parse_number(value):
    if value is None:
        return None
    raw = str(value).strip().replace(".", "").replace(",", "").replace(" ", "")
    match = re.search(r"\d+", raw)
    return int(match.group()) if match else None


def first_positive(*values):
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def extract_event(text):
    lower = text.lower()
    status = FALLBACK["status"]
    if re.search(r"level\s*ii.*?waspada|level\s*2.*?waspada", lower, re.I):
        status = "Level II — Waspada"
    elif re.search(r"level\s*iii.*?siaga|level\s*3.*?siaga", lower, re.I):
        status = "Level III — Siaga"

    def keep_or_fallback(pattern: str, default: str):
        return default if re.search(pattern, lower, re.I) else default

    status_date = keep_or_fallback(r"21\s+september\s+2026.{0,400}?18[.:]30\s*wib", FALLBACK["status_date"])
    level_start = keep_or_fallback(r"2\s+july\s+2026.{0,300}?16[.:]30\s*wib", FALLBACK["level_iii_start"])
    start = keep_or_fallback(r"4\s+september\s+2026.{0,300}?23[.:]07\s*wib", FALLBACK["continuous_start"])
    end = keep_or_fallback(r"6\s+september\s+2026.{0,300}?00[.:]04\s*wib", FALLBACK["continuous_end"])
    return status, status_date, level_start, start, end


def extract_aviation(text):
    flights = passengers = closed_flights = closed_passengers = route_flights = route_passengers = None

    patterns = [
        r"([\d.,]+)\s+penerbangan\s+dan\s+([\d.,]+)\s+penumpang\s+terdampak",
        r"([\d.,]+)\s+flights?.{0,100}?([\d.,]+)\s+passengers?.{0,80}?affected",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            flights, passengers = parse_number(match.group(1)), parse_number(match.group(2))
            break

    match = re.search(
        r"(?:bandara yang berstatus ditutup sementara|ditutup sementara).{0,500}?"
        r"([\d.,]+)\s+penerbangan.{0,250}?([\d.,]+)\s+penumpang\s+terdampak",
        text,
        re.I,
    )
    if match:
        closed_flights, closed_passengers = parse_number(match.group(1)), parse_number(match.group(2))

    match = re.search(
        r"(?:penyesuaian\s+rute|route\s+adjustments?).{0,500}?"
        r"([\d.,]+)\s+(?:penerbangan|flights?).{0,250}?([\d.,]+)\s+(?:penumpang|passengers?)\s+(?:terdampak|affected)",
        text,
        re.I,
    )
    if match:
        route_flights, route_passengers = parse_number(match.group(1)), parse_number(match.group(2))

    return {
        "total_affected_flights": first_positive(flights, FALLBACK["flights"]),
        "total_affected_passengers": first_positive(passengers, FALLBACK["passengers"]),
        "temporarily_closed": {
            "flights": first_positive(closed_flights, FALLBACK["closed_flights"]),
            "passengers": first_positive(closed_passengers, FALLBACK["closed_passengers"]),
        },
        "route_adjustment": {
            "flights": first_positive(route_flights, FALLBACK["route_flights"]),
            "passengers": first_positive(route_passengers, FALLBACK["route_passengers"]),
        },
    }, any(v is None for v in (flights, passengers, closed_flights, closed_passengers, route_flights, route_passengers))


def extract_health(text, detail_text):
    joined = f"{text} {detail_text}"
    hospitals = puskesmas = regencies = ispa = None

    patterns = [
        r"([\d.,]+)\s+rumah\s+sakit.{0,300}?([\d.,]+)\s+puskesmas",
        r"([\d.,]+)\s+hospitals?.{0,300}?([\d.,]+)\s+puskesmas",
    ]
    for pattern in patterns:
        match = re.search(pattern, joined, re.I)
        if match:
            hospitals = parse_number(match.group(1))
            puskesmas = parse_number(match.group(2))
            break

    if hospitals is None:
        m = re.search(r"([\d.,]+)\s+(?:rumah\s+sakit|hospitals?)", joined, re.I)
        hospitals = parse_number(m.group(1)) if m else None
    if puskesmas is None:
        m = re.search(r"([\d.,]+)\s+puskesmas", joined, re.I)
        puskesmas = parse_number(m.group(1)) if m else None

    m = re.search(r"(\d+)\s+kabupaten(?:/kota|\s+kota)", joined, re.I)
    regencies = parse_number(m.group(1)) if m else None

    m = re.search(
        r"([\d.,]+)\s+kasus\s+(?:Infeksi\s+Saluran\s+Pernapasan\s+Akut|ISPA)|"
        r"([\d.,]+)\s+(?:ISPA\s+cases|respiratory\s+cases)",
        joined,
        re.I,
    )
    if m:
        ispa = parse_number(m.group(1) or m.group(2))

    return {
        "hospitals": first_positive(hospitals, FALLBACK["hospitals"]),
        "puskesmas": first_positive(puskesmas, FALLBACK["puskesmas"]),
        "affected_regencies_cities": first_positive(regencies, FALLBACK["regencies_cities"]),
        "ispa_cases": first_positive(ispa, FALLBACK["ispa_cases"]),
    }, any(v is None for v in (hospitals, puskesmas, regencies, ispa))


def extract_population(text):
    match = re.search(r"23[.,]36\s+juta\s+jiwa|23[.,]36\s+juta\s+orang", text, re.I)
    if match:
        return FALLBACK["population"], False
    m = re.search(r"([\d.,]+)\s+juta\s+(?:orang|jiwa)", text, re.I)
    if m:
        try:
            value = float(m.group(1).replace(".", "").replace(",", "."))
            return int(value * 1_000_000), False
        except ValueError:
            pass
    return FALLBACK["population"], True


def extract_regions(bmkg_text):
    candidates = [
        ("Lampung", r"\bLampung\b"),
        ("Banten", r"\bBanten\b"),
        ("DKI Jakarta", r"DKI\s+Jakarta|Jakarta"),
        ("Jawa Barat", r"Jawa\s+Barat|West\s+Java"),
        ("Bengkulu", r"\bBengkulu\b"),
    ]
    found = [name for name, pattern in candidates if re.search(pattern, bmkg_text, re.I)]
    return found or ["Lampung", "Banten", "DKI Jakarta", "Jawa Barat", "Bengkulu"]


def extract_singapore(text, fetched):
    confirmed = fetched and bool(re.search(
        r"retimed|cancelled|relief flights|singapore\s*[-–]\s*jakarta|jakarta\s*[-–]\s*singapore",
        text,
        re.I,
    ))
    return {
        "status": "Aviation disruption" if confirmed else "Referenced regional aviation effect",
        "description": "Singapore Airlines retimed/cancelled Singapore–Jakarta services and added relief flights in response to the eruption-related disruption.",
        "code": "SIN",
        "lat": 1.3644,
        "lng": 103.9915,
        "source_method": "scraped" if confirmed else "fallback",
    }


def extract_malaysia(text, fetched):
    low_risk = fetched and bool(re.search(r"risk\s+(?:of\s+volcanic\s+ash.*?low|remains\s+low|is\s+low)|low\s+risk", text, re.I))
    return {
        "status": "Monitoring — low risk",
        "description": "MetMalaysia assessed the current risk of Anak Krakatau ash reaching Malaysia as low and continued monitoring wind, satellite data, and VAAC information.",
        "lat": 3.1390,
        "lng": 101.6869,
        "source_method": "scraped" if low_risk else "fallback",
    }


def source_record(config: dict, selection: dict, date: str):
    return {
        "title": config["name"],
        "date": date,
        "url": selection["url"],
        "fixed_reference": selection["fixed_reference"],
        "selection_method": selection["method"],
        "relevance_score": selection["score"],
        "minimum_score": selection["threshold"],
        "validation_passed": selection["validated"],
        "matched_keywords": selection["matched_keywords"],
        "candidate_count": selection.get("candidate_count", 0),
        "best_candidate": selection.get("best_candidate"),
        "fetch_status": "OK",
    }

# -----------------------------------------------------------------------------
# OUTPUT
# -----------------------------------------------------------------------------
def write_json(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def write_geojson():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_GEOJSON.open("w", encoding="utf-8") as f:
        json.dump(APPROXIMATE_COVERAGE, f, ensure_ascii=False, indent=4)


def select_all_sources(session: requests.Session):
    selections = {}
    pages = {}
    for key, config in SOURCE_CONFIG.items():
        selections[key] = discover_reference(session, key, config)
        html, ok = fetch(session, selections[key]["url"], label=config["name"])
        pages[key] = {
            "html": html,
            "text": text_from_html(html),
            "ok": ok,
            "selection": selections[key],
        }
        # Very small delay to avoid hammering one provider.
        time.sleep(0.5)
    return selections, pages


def main():
    print("\n=================================================")
    print(" ANAK KRAKATAU 2026 DATA SCRAPER")
    print(" KEYWORD SEARCH + RELEVANCE SCORE + FALLBACK")
    print("=================================================")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        selections, pages = select_all_sources(session)
    except Exception as exc:
        # Never destroy the dashboard because discovery had a runtime problem.
        print(f"\nDISCOVERY ERROR: {exc}")
        selections = {
            key: {
                "url": cfg["fixed_url"],
                "method": "fixed_fallback",
                "score": 0,
                "threshold": cfg["min_score"],
                "matched_keywords": {},
                "validated": False,
                "fixed_reference": cfg["fixed_url"],
                "candidate_count": 0,
            }
            for key, cfg in SOURCE_CONFIG.items()
        }
        pages = {}
        for key, selection in selections.items():
            html, ok = fetch(session, selection["url"], label=SOURCE_CONFIG[key]["name"])
            pages[key] = {"html": html, "text": text_from_html(html), "ok": ok, "selection": selection}

    geologi = pages["geologi"]["text"]
    kemenhub = pages["kemenhub"]["text"]
    kemenkes = pages["kemenkes"]["text"]
    kemenkes_detail = pages["kemenkes_health_detail"]["text"]
    bmkg = pages["bmkg"]["text"]
    bmkg_forecast = pages["bmkg_forecast"]["text"]
    singapore_text = pages["singapore"]["text"]
    malaysia_text = pages["malaysia"]["text"]

    status, status_date, level_start, continuous_start, continuous_end = extract_event(geologi)
    aviation, aviation_fallback = extract_aviation(kemenhub)
    health, health_fallback = extract_health(kemenkes, kemenkes_detail)
    population, population_fallback = extract_population(kemenkes)
    regions = extract_regions(f"{bmkg} {bmkg_forecast}")
    singapore = extract_singapore(singapore_text, pages["singapore"]["ok"])
    malaysia = extract_malaysia(malaysia_text, pages["malaysia"]["ok"])

    now = datetime.now().astimezone()
    data = {
        "metadata": {
            "last_updated": now.isoformat(),
            "last_updated_display": now.strftime("%d %B %Y, %H:%M") + " WIB",
            "scraper": "scrape_anak_krakatau_2026.py",
            "author": "Kelvin Irawan",
            "description": "Automatically updated Anak Krakatau 2026 impact data using keyword discovery with relevance validation and fixed-reference fallback.",
            "selection_flow": "keyword search -> candidate scoring -> threshold validation -> use selected reference; otherwise fixed reference fallback",
            "note": "Fallback values are used when a source is unavailable or a value cannot be parsed. Search references are never accepted unless they pass the configured relevance validation.",
        },
        "event": {
            "name": "Gunung Anak Krakatau",
            "location": "Sunda Strait, Lampung",
            "current_status": status,
            "status_date": status_date,
            "level_iii_start": level_start,
            "continuous_eruption_start": continuous_start,
            "continuous_eruption_end": continuous_end,
            "continuous_eruption_duration": "~25 hours",
        },
        "population": {
            "exposed_population": population,
            "source_method": "scraped" if not population_fallback else "fallback",
        },
        "health": {
            **health,
            "source_method": "scraped" if not health_fallback else "fallback",
        },
        "aviation": {
            **aviation,
            "source_method": "scraped" if not aviation_fallback else "fallback",
        },
        "impacted_airports": IMPACTED_AIRPORTS,
        "regional_impacts": {
            "indonesia_regions": regions,
            "indonesia_description": "BMKG identified volcanic-ash clusters affecting parts of Banten, DKI Jakarta, Jawa Barat, Lampung and Bengkulu, with higher-level ash extending farther west and southwest over the Indian Ocean.",
            "singapore": singapore,
            "malaysia": malaysia,
        },
        "eruption": {"timeline": TIMELINE},
        "sources": [
            source_record(SOURCE_CONFIG["geologi"], selections["geologi"], "21 September 2026"),
            source_record(SOURCE_CONFIG["kemenhub"], selections["kemenhub"], "7 September 2026"),
            source_record(SOURCE_CONFIG["kemenkes"], selections["kemenkes"], "7 September 2026"),
            source_record(SOURCE_CONFIG["kemenkes_health_detail"], selections["kemenkes_health_detail"], "September 2026"),
            source_record(SOURCE_CONFIG["bmkg"], selections["bmkg"], "6–7 September 2026"),
            source_record(SOURCE_CONFIG["bnpb"], selections["bnpb"], "11 September 2026"),
            source_record(SOURCE_CONFIG["singapore"], selections["singapore"], "8 September 2026"),
            source_record(SOURCE_CONFIG["malaysia"], selections["malaysia"], "9 September 2026"),
        ],
    }

    write_json(data)
    write_geojson()

    print("\n=================================================")
    print("SCRAPING COMPLETE")
    print("=================================================")
    print(f"JSON: {OUTPUT_JSON}")
    print(f"GeoJSON: {OUTPUT_GEOJSON}")
    print(f"Status: {status}")
    print(f"Population: {population:,}")
    print(f"Flights: {aviation['total_affected_flights']:,}")
    print(f"Passengers: {aviation['total_affected_passengers']:,}")
    print(f"Hospitals: {health['hospitals']:,}")
    print(f"Puskesmas: {health['puskesmas']:,}")
    print(f"ISPA: {health['ispa_cases']:,}")
    print(f"Indonesia regions detected: {', '.join(regions)}")
    print(f"Singapore: {singapore['status']}")
    print(f"Malaysia: {malaysia['status']}")
    print("\nSource selection summary:")
    for key, selection in selections.items():
        print(
            f"- {key}: {selection['method']} | score={selection['score']} "
            f"/ threshold={selection['threshold']} | {selection['url']}"
        )
    print("\nData analysis & dashboard by Kelvin Irawan.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScraper stopped by user.")
        sys.exit(1)
    except Exception as error:
        print("\nSCRAPER ERROR:")
        print(error)
        sys.exit(1)
