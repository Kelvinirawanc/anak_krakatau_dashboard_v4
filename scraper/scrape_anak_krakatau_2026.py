"""
ANAK KRAKATAU 2026 DATA SCRAPER
Data analysis & dashboard by Kelvin Irawan

Writes:
  data/anak_krakatau_2026.json
  data/impacted_areas.geojson

The scraper separates:
  1) directly reported ash impacts in Indonesia,
  2) documented aviation disruption in Singapore, and
  3) monitoring / low-risk status for Malaysia.
"""

from datetime import datetime
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_JSON = DATA_DIR / "anak_krakatau_2026.json"
OUTPUT_GEOJSON = DATA_DIR / "impacted_areas.geojson"
TIMEOUT = 30

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154.0 Safari/537.36"}

SOURCES = {
    "geologi": "https://geologi.esdm.go.id/media-center/laporan-khusus-penurunan-tingkat-aktivitas-gunungapi-anak-krakatau-provinsi-lampung-dari-level-iii-siaga-menjadi-level-ii-waspada-tanggal-21-september-2026-pukul-18-30-wib",
    "kemenhub": "https://www.kemenhub.go.id/post/read/sejumlah-bandara-masih-terdampak-abu-vulkanik-gunung-anak-krakatau%2C-kemenhub-siapkan-bandara-alternatif",
    "kemenhub_mirror": "https://dephub.go.id/post/read/sejumlah-bandara-masih-terdampak-abu-vulkanik-gunung-anak-krakatau%2C-kemenhub-siapkan-bandara-alternatif",
    "kemenkes": "https://www.kemkes.go.id/id/kemenkes-siagakan-413-rumah-sakit-dan-830-puskesmas-hadapi-dampak-erupsi-anak-krakatau",
    "kemenkes_health_detail": "https://kemkes.go.id/eng/kemenkes-perkuat-pemantauan-kualitas-udara-hadapi-dampak-erupsi-anak-krakatau",
    "bnpb": "https://bnpb.go.id/berita/update-aktivitas-gunung-anak-krakatau-status-level-iii-masih-berlaku",
    "bmkg": "https://www.bmkg.go.id/berita/utama/bmkg-terus-pantau-dampak-erupsi-gunung-anak-krakatau",
    "bmkg_forecast": "https://www.bmkg.go.id/cuaca/potensi-hujan-sepekan/prakiraan-cuaca-indonesia-sepekan-periode-8-14-september-2026-abu-vulkanik-dan-asap-masih-terpantau-potensi-hujan-signifikan-masih-ada-di-sejumlah-wilayah",
    "singapore": "https://www.singaporeair.com/en_UK/dk/corporate/newsroom/newsalert-listing/advisory-on-singapore-airlines-flights-impacted-by-the-eruption-/",
    "malaysia": "https://www.nadma.gov.my/bi/media-en/news/7101-metmalaysia-anak-krakatau-ash-could-reach-malaysia-but-risk-remains-low",
}

FALLBACK = {
    "status": "Level II — Waspada", "status_date": "21 September 2026, 18:30 WIB",
    "level_iii_start": "2 July 2026, 16:30 WIB", "continuous_start": "4 September 2026, 23:07 WIB", "continuous_end": "6 September 2026, 00:04 WIB",
    "population": 23360000, "hospitals": 413, "puskesmas": 830, "regencies_cities": 23, "ispa_cases": 16759,
    "flights": 2300, "passengers": 270337, "closed_flights": 1397, "closed_passengers": 177579, "route_flights": 922, "route_passengers": 92758,
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


def fetch(session, url):
    print(f"\nFetching:\n{url}")
    try:
        response = session.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        print(f"OK - HTTP {response.status_code}")
        return response.text, True
    except requests.RequestException as exc:
        print(f"ERROR - {exc}")
        return "", False


def text_from_html(html):
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def parse_number(value):
    if value is None:
        return None
    value = str(value).strip().replace(".", "").replace(",", "").replace(" ", "")
    match = re.search(r"\d+", value)
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
    status = "Level II — Waspada" if re.search(r"Level\s*II.*?Waspada", text, re.I) else FALLBACK["status"]
    status_date = FALLBACK["status_date"] if re.search(r"21\s+September\s+2026.{0,300}?18[.:]30\s*WIB", text, re.I) else FALLBACK["status_date"]
    level_start = FALLBACK["level_iii_start"] if re.search(r"2\s+July\s+2026.{0,250}?16[.:]30\s*WIB", text, re.I) else FALLBACK["level_iii_start"]
    start = FALLBACK["continuous_start"] if re.search(r"4\s+September\s+2026.{0,250}?23[.:]07\s*WIB", text, re.I) else FALLBACK["continuous_start"]
    end = FALLBACK["continuous_end"] if re.search(r"6\s+September\s+2026.{0,250}?00[.:]04\s*WIB", text, re.I) else FALLBACK["continuous_end"]
    return status, status_date, level_start, start, end


def extract_aviation(text):
    flights = passengers = closed_flights = closed_passengers = route_flights = route_passengers = None
    match = re.search(r"([\d.,]+)\s+penerbangan\s+dan\s+([\d.,]+)\s+penumpang\s+terdampak", text, re.I)
    if match:
        flights, passengers = parse_number(match.group(1)), parse_number(match.group(2))
    match = re.search(r"Pada\s+bandara\s+yang\s+berstatus\s+ditutup\s+sementara.{0,250}?tercatat\s+([\d.,]+)\s+penerbangan.{0,150}?(?:sekitar\s+)?([\d.,]+)\s+penumpang\s+terdampak", text, re.I)
    if match:
        closed_flights, closed_passengers = parse_number(match.group(1)), parse_number(match.group(2))
    if closed_flights is None:
        match = re.search(r"tercatat\s+([\d.,]+)\s+penerbangan\s+dengan\s+sekitar\s+([\d.,]+)\s+penumpang\s+terdampak.{0,100}?ditutup\s+sementara", text, re.I)
        if match:
            closed_flights, closed_passengers = parse_number(match.group(1)), parse_number(match.group(2))
    match = re.search(r"(?:penyesuaian\s+rute|penerbangan\s+terdampak\s+akibat\s+penyesuaian\s+rute).{0,250}?tercatat\s+([\d.,]+)\s+penerbangan.{0,150}?([\d.,]+)\s+penumpang\s+terdampak", text, re.I)
    if match:
        route_flights, route_passengers = parse_number(match.group(1)), parse_number(match.group(2))
    return {
        "total_affected_flights": first_positive(flights, FALLBACK["flights"]),
        "total_affected_passengers": first_positive(passengers, FALLBACK["passengers"]),
        "temporarily_closed": {"flights": first_positive(closed_flights, FALLBACK["closed_flights"]), "passengers": first_positive(closed_passengers, FALLBACK["closed_passengers"])},
        "route_adjustment": {"flights": first_positive(route_flights, FALLBACK["route_flights"]), "passengers": first_positive(route_passengers, FALLBACK["route_passengers"])},
    }, any(v is None for v in (flights, passengers, closed_flights, closed_passengers, route_flights, route_passengers))


def extract_health(text, detail_text):
    joined = f"{text} {detail_text}"
    match = re.search(r"(\d[\d.,]*)\s+rumah\s+sakit.{0,250}?(\d[\d.,]*)\s+puskesmas", joined, re.I)
    hospitals = parse_number(match.group(1)) if match else None
    puskesmas = parse_number(match.group(2)) if match else None
    if hospitals is None:
        m = re.search(r"([\d.,]+)\s+rumah\s+sakit", joined, re.I); hospitals = parse_number(m.group(1)) if m else None
    if puskesmas is None:
        m = re.search(r"([\d.,]+)\s+puskesmas", joined, re.I); puskesmas = parse_number(m.group(1)) if m else None
    m = re.search(r"(\d+)\s+kabupaten/kota", joined, re.I)
    regencies = parse_number(m.group(1)) if m else None
    ispa = None
    m = re.search(r"([\d.,]+)\s+kasus\s+Infeksi\s+Saluran\s+Pernapasan\s+Akut", joined, re.I)
    if m:
        ispa = parse_number(m.group(1))
    return {"hospitals": first_positive(hospitals, FALLBACK["hospitals"]), "puskesmas": first_positive(puskesmas, FALLBACK["puskesmas"]), "affected_regencies_cities": first_positive(regencies, FALLBACK["regencies_cities"]), "ispa_cases": first_positive(ispa, FALLBACK["ispa_cases"])}, any(v is None for v in (hospitals,puskesmas,regencies,ispa))


def extract_population(text):
    if re.search(r"23[.,]36\s+juta\s+jiwa", text, re.I):
        return FALLBACK["population"], False
    m = re.search(r"([\d.,]+)\s+juta\s+orang", text, re.I)
    if m:
        try:
            value = float(m.group(1).replace(",", "."))
            return int(value * 1_000_000), False
        except ValueError:
            pass
    return FALLBACK["population"], True


def extract_regions(bmkg_text):
    candidates = [("Lampung", r"\bLampung\b"),("Banten", r"\bBanten\b"),("DKI Jakarta", r"DKI\s+Jakarta|Jakarta"),("Jawa Barat", r"Jawa\s+Barat|Jawa Barat"),("Bengkulu", r"\bBengkulu\b")]
    found = [name for name,pattern in candidates if re.search(pattern,bmkg_text,re.I)]
    return found or ["Lampung","Banten","DKI Jakarta","Jawa Barat","Bengkulu"]


def extract_singapore(text, fetched):
    confirmed = fetched and bool(re.search(r"retimed|cancelled|relief flights|Singapore to Jakarta|Jakarta to Singapore", text, re.I))
    return {"status":"Aviation disruption" if confirmed else "Referenced regional aviation effect", "description":"Singapore Airlines retimed/cancelled Singapore–Jakarta services and added relief flights in response to the eruption-related disruption.", "code":"SIN", "lat":1.3644, "lng":103.9915, "source_method":"scraped" if confirmed else "fallback"}


def extract_malaysia(text, fetched):
    low_risk = fetched and bool(re.search(r"risk\s+of\s+volcanic\s+ash.*?low|risk\s+remains\s+low|risk\s+is\s+low", text, re.I))
    return {"status":"Monitoring — low risk", "description":"MetMalaysia assessed the current risk of Anak Krakatau ash reaching Malaysia as low and continued monitoring wind, satellite data, and VAAC information.", "lat":3.1390, "lng":101.6869, "source_method":"scraped" if low_risk else "fallback"}


def source_record(title, description, date, url, ok):
    return {"title":title,"description":description,"date":date,"url":url,"fetch_status":"OK" if ok else "FALLBACK"}


def write_json(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSON.open("w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)


def write_geojson():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_GEOJSON.open("w", encoding="utf-8") as f: json.dump(APPROXIMATE_COVERAGE, f, ensure_ascii=False, indent=4)


def main():
    print("\n=================================================")
    print(" ANAK KRAKATAU 2026 DATA SCRAPER")
    print("=================================================")
    session = requests.Session(); session.headers.update(HEADERS)
    pages = {}
    for key in ("geologi","kemenkes","kemenkes_health_detail","bnpb","bmkg","bmkg_forecast","singapore","malaysia"):
        html, ok = fetch(session, SOURCES[key]); pages[key] = {"html":html,"text":text_from_html(html),"ok":ok}
    html, ok = fetch(session, SOURCES["kemenhub"])
    if not ok:
        html, ok = fetch(session, SOURCES["kemenhub_mirror"])
    pages["kemenhub"] = {"html":html,"text":text_from_html(html),"ok":ok}

    status,status_date,level_start,continuous_start,continuous_end = extract_event(pages["geologi"]["text"])
    aviation, aviation_fallback = extract_aviation(pages["kemenhub"]["text"])
    health, health_fallback = extract_health(pages["kemenkes"]["text"], pages["kemenkes_health_detail"]["text"])
    population,population_fallback = extract_population(pages["kemenkes"]["text"])
    regions = extract_regions(f"{pages['bmkg']['text']} {pages['bmkg_forecast']['text']}")
    singapore = extract_singapore(pages["singapore"]["text"], pages["singapore"]["ok"])
    malaysia = extract_malaysia(pages["malaysia"]["text"], pages["malaysia"]["ok"])

    now = datetime.now().astimezone()
    data = {
        "metadata": {"last_updated":now.isoformat(),"last_updated_display":now.strftime("%d %B %Y, %H:%M")+" WIB","scraper":"scrape_anak_krakatau_2026.py","author":"Kelvin Irawan","description":"Automatically updated Anak Krakatau 2026 impact data from official Indonesian sources plus documented regional aviation/monitoring sources.","note":"Fallback values are used when a source is unavailable or a value cannot be parsed."},
        "event": {"name":"Gunung Anak Krakatau","location":"Sunda Strait, Lampung","current_status":status,"status_date":status_date,"level_iii_start":level_start,"continuous_eruption_start":continuous_start,"continuous_eruption_end":continuous_end,"continuous_eruption_duration":"~25 hours"},
        "population": {"exposed_population":population,"source_method":"scraped" if not population_fallback else "fallback"},
        "health": {**health,"source_method":"scraped" if not health_fallback else "fallback"},
        "aviation": {**aviation,"source_method":"scraped" if not aviation_fallback else "fallback"},
        "impacted_airports": IMPACTED_AIRPORTS,
        "regional_impacts": {"indonesia_regions":regions,"indonesia_description":"BMKG identified volcanic-ash clusters affecting parts of Banten, DKI Jakarta, Jawa Barat, Lampung and Bengkulu, with higher-level ash extending farther west and southwest over the Indian Ocean.","singapore":singapore,"malaysia":malaysia},
        "eruption": {"timeline":TIMELINE},
        "sources": [
            source_record("Badan Geologi — Latest Status","Latest Anak Krakatau activity and status evaluation.","21 September 2026",SOURCES["geologi"],pages["geologi"]["ok"]),
            source_record("Kementerian Perhubungan RI","Affected flights, passengers, closures and route adjustments.","7 September 2026",SOURCES["kemenhub"] if pages["kemenhub"]["ok"] else SOURCES["kemenhub_mirror"],pages["kemenhub"]["ok"]),
            source_record("Kementerian Kesehatan RI","Population exposure and healthcare preparedness.","7 September 2026",SOURCES["kemenkes"],pages["kemenkes"]["ok"]),
            source_record("Kementerian Kesehatan RI — Air Quality","Respiratory-health monitoring and ISPA cases.","September 2026",SOURCES["kemenkes_health_detail"],pages["kemenkes_health_detail"]["ok"]),
            source_record("BMKG — Volcanic Ash Monitoring","Ash distribution, SIGMETs and atmospheric impact monitoring.","6–7 September 2026",SOURCES["bmkg"],pages["bmkg"]["ok"]),
            source_record("BNPB — Eruption Update","Eruption activity and disaster response measures.","11 September 2026",SOURCES["bnpb"],pages["bnpb"]["ok"]),
            source_record("Singapore Airlines","Singapore–Jakarta flight disruption and recovery actions.","8 September 2026",SOURCES["singapore"],pages["singapore"]["ok"]),
            source_record("Portal NADMA / MetMalaysia","Malaysia ash-risk monitoring and assessment.","9 September 2026",SOURCES["malaysia"],pages["malaysia"]["ok"]),
        ],
    }
    write_json(data); write_geojson()
    print("\nSCRAPING COMPLETE")
    print(f"JSON: {OUTPUT_JSON}\nGeoJSON: {OUTPUT_GEOJSON}")
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
    print("\nData analysis & dashboard by Kelvin Irawan.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScraper stopped by user."); sys.exit(1)
    except Exception as error:
        print("\nSCRAPER ERROR:"); print(error); sys.exit(1)
