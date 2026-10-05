"""
============================================================
ANAK KRAKATAU 2026 - FIXED REFERENCE SCRAPER
Data analysis & dashboard by Kelvin Irawan
============================================================

PURPOSE
-------
This production version intentionally uses fixed, trusted reference URLs.
The scraper re-fetches those references on every run, so GitHub Actions can
refresh the data without depending on a search engine or changing site HTML
search results.

As of 05 October 2026, the latest official activity evaluation found in the
trusted reference set is the Badan Geologi / ESDM evaluation effective
21 September 2026 at 18:30 WIB: Level II (Waspada). No later official Anak
Krakatau status evaluation was found in the reference set at the build date.

OUTPUTS
-------
1. data/anak_krakatau_2026.json
2. data/impacted_areas.geojson

DEPENDENCIES
------------
requests
beautifulsoup4
lxml
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, Tuple

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_JSON = DATA_DIR / "anak_krakatau_2026.json"
OUTPUT_GEOJSON = DATA_DIR / "impacted_areas.geojson"

TIMEOUT = 30
AS_OF_DATE = "05 October 2026"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36 AnakKrakatauDashboard/1.0"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}

# ---------------------------------------------------------------------------
# TRUSTED FIXED REFERENCES
# ---------------------------------------------------------------------------
SOURCES = {
    "geologi": {
        "name": "Kementerian ESDM / Badan Geologi — Latest Status",
        "url": "https://www.esdm.go.id/id/media-center/arsip-berita/aktivitas-anak-krakatau-menurun-badan-geologi-turunkan-status-dari-siaga-menjadi-waspada",
        "date": "22 September 2026",
        "description": "Latest official activity evaluation; status was lowered from Level III (Siaga) to Level II (Waspada).",
    },
    "bnpb": {
        "name": "BNPB — Preparedness in Lampung",
        "url": "https://bnpb.go.id/berita/antisipasi-erupsi-gunung-anak-krakatau-bnpb-perkuat-kesiapsiagaan-di-lampung",
        "date": "10 September 2026",
        "description": "BNPB preparedness and local mitigation measures associated with Anak Krakatau activity.",
    },
    "kemenhub": {
        "name": "Kementerian Perhubungan RI — Aviation",
        "url": "https://www.kemenhub.go.id/post/read/sejumlah-bandara-masih-terdampak-abu-vulkanik-gunung-anak-krakatau%2C-kemenhub-siapkan-bandara-alternatif",
        "date": "7 September 2026",
        "description": "Affected flights, passengers, airport closures and route adjustments.",
    },
    "kemenkes": {
        "name": "Kementerian Kesehatan RI — Response",
        "url": "https://www.kemkes.go.id/id/kemenkes-siagakan-413-rumah-sakit-dan-830-puskesmas-hadapi-dampak-erupsi-anak-krakatau",
        "date": "7 September 2026",
        "description": "Population exposure and healthcare preparedness in affected areas.",
    },
    "kemenkes_health": {
        "name": "Kementerian Kesehatan RI — Air Quality",
        "url": "https://kemkes.go.id/eng/kemenkes-perkuat-pemantauan-kualitas-udara-hadapi-dampak-erupsi-anak-krakatau",
        "date": "September 2026",
        "description": "Air-quality and respiratory-health monitoring, including ISPA reporting.",
    },
    "bmkg": {
        "name": "BMKG — Volcanic Ash & Airport Monitoring",
        "url": "https://www.bmkg.go.id/siaran-pers/bmkg-ungkap-abu-vulkanik-negatif-8-bandara-beroperasi-kembali-dan-pemerintah-terus-laksanakan-omc",
        "date": "8 September 2026",
        "description": "Paper-test verification, ash monitoring and airport reopening after the eruption.",
    },
    "singapore": {
        "name": "The Straits Times — Singapore Airlines",
        "url": "https://www.straitstimes.com/singapore/anak-krakatau-eruption-sia-adds-8-relief-flights-between-jakarta-and-singapore",
        "date": "8 September 2026",
        "description": "Singapore Airlines added eight relief flights between Singapore and Jakarta and reported schedule disruptions.",
    },
    "malaysia_airlines": {
        "name": "The Star — Malaysia Airlines",
        "url": "https://www.thestar.com.my/news/nation/2026/09/06/malaysia-airlines-cancels-12-jakarta-flights-after-anak-krakatau-eruption",
        "date": "6 September 2026",
        "description": "Malaysia Airlines cancelled 12 Jakarta flights because of the volcanic activity affecting Soekarno-Hatta operations.",
    },
    "malaysia": {
        "name": "NADMA / MetMalaysia — Malaysia Risk",
        "url": "https://www.nadma.gov.my/bi/media-en/news/7101-metmalaysia-anak-krakatau-ash-could-reach-malaysia-but-risk-remains-low",
        "date": "9 September 2026",
        "description": "Malaysia monitoring and assessment of the potential for Anak Krakatau ash to reach Malaysia.",
    },
}

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

AIRPORTS = [
    {"name":"Soekarno-Hatta International Airport","code":"CGK","province":"Banten","country":"Indonesia","impact":"Temporary closure","lat":-6.1256,"lng":106.6559},
    {"name":"Halim Perdanakusuma Airport","code":"HLP","province":"DKI Jakarta","country":"Indonesia","impact":"Temporary closure","lat":-6.2666,"lng":106.8900},
    {"name":"Radin Inten II Airport","code":"TKG","province":"Lampung","country":"Indonesia","impact":"Temporary closure","lat":-5.2427,"lng":105.1751},
    {"name":"Budiarto Airport","code":"RTO","province":"Banten","country":"Indonesia","impact":"Temporary closure","lat":-6.2930,"lng":106.5690},
    {"name":"Pondok Cabe Airport","code":"PCB","province":"Banten","country":"Indonesia","impact":"Affected","lat":-6.3369,"lng":106.7640},
    {"name":"Husein Sastranegara Airport","code":"BDO","province":"West Java","country":"Indonesia","impact":"Affected","lat":-6.9006,"lng":107.5764},
    {"name":"Muhammad Taufiq Kiemas Airport","code":"TNB","province":"Lampung","country":"Indonesia","impact":"Affected","lat":-5.2110,"lng":105.1630},
    {"name":"Atung Bungsu Airport","code":"PXA","province":"South Sumatra","country":"Indonesia","impact":"Previously affected","lat":-4.0330,"lng":103.3950},
    {"name":"Singapore Changi Airport","code":"SIN","province":"Singapore","country":"Singapore","impact":"International route disruption","lat":1.3644,"lng":103.9915,"regional":True},
    {"name":"Kuala Lumpur International Airport","code":"KUL","province":"Malaysia","country":"Malaysia","impact":"International route disruption","lat":2.7456,"lng":101.7099,"regional":True},
]

# Irregular plume-style analytical coverage. These are intentionally NOT square
# administrative boxes. They represent reported/monitored ash corridors only.
GEOJSON = {
    "type": "FeatureCollection",
    "name": "Anak Krakatau 2026 Approximate Ash Coverage",
    "features": [
        {
            "type":"Feature",
            "properties":{
                "name":"Reported ash-affected corridor — Indonesia",
                "coverage_type":"ash_affected",
                "regions":["Bengkulu","Lampung","Banten","DKI Jakarta","Jawa Barat"],
                "note":"Approximate analytical corridor based on reported volcanic-ash impact. It is not an official administrative or concentration boundary."
            },
            "geometry":{
                "type":"Polygon",
                "coordinates":[[
                    [103.65,-5.02],[104.20,-5.12],[104.65,-5.32],[105.15,-5.22],
                    [105.62,-5.38],[106.02,-5.48],[106.38,-5.60],[106.74,-5.83],
                    [107.02,-6.13],[106.88,-6.42],[106.46,-6.58],[105.92,-6.62],
                    [105.42,-6.52],[104.96,-6.66],[104.54,-6.42],[104.10,-6.18],
                    [103.82,-5.78],[103.65,-5.02]
                ]]
            }
        },
        {
            "type":"Feature",
            "properties":{
                "name":"Higher-level ash monitoring plume — offshore",
                "coverage_type":"higher_level_monitoring",
                "note":"Approximate offshore monitoring corridor consistent with higher-level ash observations reported by BMKG; not an official ash concentration boundary."
            },
            "geometry":{
                "type":"Polygon",
                "coordinates":[[
                    [98.85,-4.22],[99.72,-4.32],[100.58,-4.55],[101.42,-4.68],
                    [102.22,-4.88],[102.98,-5.12],[103.60,-5.42],[103.74,-5.82],
                    [103.38,-6.20],[102.76,-6.53],[101.92,-6.62],[101.06,-6.42],
                    [100.20,-6.12],[99.46,-5.60],[99.02,-4.92],[98.85,-4.22]
                ]]
            }
        }
    ]
}

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or " ").strip()

def fetch(url: str) -> Tuple[str, bool, int]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        print(f"  OK HTTP {r.status_code} -> {r.url}")
        return r.text, True, r.status_code
    except requests.RequestException as exc:
        print(f"  ERROR {exc}")
        return "", False, 0

def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script","style","noscript","svg","nav","footer"]):
        tag.decompose()
    return normalize_space(soup.get_text(" ", strip=True))

def extract_title(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return normalize_space(soup.title.get_text(" ", strip=True)) if soup.title else ""

def parse_number(value: Optional[str]) -> Optional[int]:
    if value is None: return None
    raw = str(value).strip().replace(" ", "").replace(".", "").replace(",", "")
    m = re.search(r"\d+", raw)
    return int(m.group()) if m else None

def find_number(patterns: Sequence[str], text: str) -> Optional[int]:
    for p in patterns:
        m = re.search(p, text or "", re.I)
        if m:
            n = parse_number(m.group(1))
            if n is not None: return n
    return None

def extract_date(text: str) -> Optional[str]:
    months = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
              "januari":1,"februari":2,"maret":3,"mei":5,"juni":6,"juli":7,"agustus":8,"september":9,"oktober":10,"november":11,"desember":12}
    pat = r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\s+(20\d{2})\b"
    vals=[]
    for d,m,y in re.findall(pat,text or "",re.I):
        try: vals.append(datetime(int(y),months[m.lower()],int(d)))
        except Exception: pass
    return max(vals).strftime("%Y-%m-%d") if vals else None

def first(source_key: str) -> dict:
    return SOURCE_CACHE.get(source_key, {})

SOURCE_CACHE = {}
def collect_sources():
    print("\nFetching fixed trusted references")
    for key,cfg in SOURCES.items():
        print(f"\n[{cfg['name']}]\n{cfg['url']}")
        html,ok,status=fetch(cfg['url'])
        SOURCE_CACHE[key]={
            "html":html,"ok":ok,"status":status,
            "text":html_to_text(html),
            "title":extract_title(html) or cfg['name'],
            "date":cfg['date'],
            "url":cfg['url'],
            "description":cfg['description'],
            "reference_type":"fixed_reference",
        }
        time.sleep(0.25)

def extract_aviation(text: str) -> dict:
    total_f=find_number([r"([\d.,]+)\s+(?:affected\s+)?flights",r"([\d.,]+)\s+penerbangan\s+(?:terdampak|affected)",r"approximately\s+([\d.,]+)\s+flights"],text)
    total_p=find_number([r"([\d.,]+)\s+(?:affected\s+)?passengers",r"([\d.,]+)\s+penumpang\s+(?:terdampak|affected)",r"approximately\s+([\d.,]+)\s+passengers"],text)
    closure_f=find_number([r"([\d.,]+)\s+(?:flights|penerbangan).{0,220}?(?:ditutup sementara|temporary closure)",r"(?:ditutup sementara|temporary closure).{0,220}?([\d.,]+)\s+(?:flights|penerbangan)"],text)
    closure_p=find_number([r"(?:ditutup sementara|temporary closure).{0,300}?([\d.,]+)\s+(?:passengers|penumpang)"],text)
    route_f=find_number([r"penyesuaian\s+rute.{0,220}?([\d.,]+)\s+penerbangan",r"([\d.,]+)\s+(?:flights|penerbangan).{0,140}?route adjustment"],text)
    route_p=find_number([r"penyesuaian\s+rute.{0,250}?([\d.,]+)\s+penumpang",r"route adjustment.{0,200}?([\d.,]+)\s+passengers"],text)
    return {"total_affected_flights":total_f or FALLBACK["flights"],"total_affected_passengers":total_p or FALLBACK["passengers"],"temporarily_closed":{"flights":closure_f or FALLBACK["closure_flights"],"passengers":closure_p or FALLBACK["closure_passengers"]},"route_adjustment":{"flights":route_f or FALLBACK["route_flights"],"passengers":route_p or FALLBACK["route_passengers"]}}

def extract_health(text: str, detail: str) -> dict:
    joined=f"{text} {detail}"
    hospitals=find_number([r"([\d.,]+)\s+rumah\s+sakit",r"([\d.,]+)\s+hospitals?"],joined) or FALLBACK["hospitals"]
    pusk=find_number([r"([\d.,]+)\s+puskesmas"],joined) or FALLBACK["puskesmas"]
    reg=find_number([r"([\d.,]+)\s+kabupaten\s*/\s*kota",r"([\d.,]+)\s+kabupaten/kota"],joined) or FALLBACK["affected_regencies_cities"]
    ispa=find_number([r"([\d.,]+)\s+(?:kasus\s+)?ISPA",r"([\d.,]+)\s+respiratory\s+cases"],joined) or FALLBACK["ispa"]
    return {"hospitals":hospitals,"puskesmas":pusk,"affected_regencies_cities":reg,"ispa_cases":ispa}

def extract_population(text: str) -> int:
    m=re.search(r"([\d.,]+)\s*(?:juta|million)\s+(?:orang|people|jiwa|penduduk)",text,re.I)
    if m:
        raw=m.group(1).replace('.','').replace(',','.')
        try:return int(round(float(raw)*1_000_000))
        except ValueError:pass
    return FALLBACK["population"]

def singapore_info(text: str) -> dict:
    relief=None
    m=re.search(r"(?:added|adds)\s+(\d+)\s+relief\s+flights|(?:added|adds)\s+eight\s+relief\s+flights",text,re.I)
    if m: relief=parse_number(m.group(1)) if m.group(1) else 8
    if relief is None and re.search(r"eight\s+relief\s+flights",text,re.I): relief=8
    return {"status":"Aviation disruption","description":f"Singapore Airlines added {relief or 8} relief flights between Singapore and Jakarta, with other services retimed or cancelled in response to the eruption-related disruption.","relief_flights_added":relief or 8,"code":"SIN","lat":1.3644,"lng":103.9915,"source_method":"fixed_reference"}

def malaysia_airlines_info(text: str) -> dict:
    n=None
    m=re.search(r"cancel(?:led|ed)\s+(?:a\s+)?(?:dozen|12)\s+Jakarta flights",text,re.I)
    if m:n=12
    if n is None and re.search(r"cancel(?:led|ed).*?12.*?flights",text,re.I):n=12
    return {"status":"Aviation disruption","description":f"Malaysia Airlines cancelled {n or 12} Jakarta flights following volcanic activity from Anak Krakatau, affecting operations at Soekarno-Hatta International Airport.","cancelled_flights":n or 12,"code":"KUL","lat":2.7456,"lng":101.7099,"source_method":"fixed_reference"}

def malaysia_monitoring(text: str) -> dict:
    low_risk=bool(re.search(r"risk.*?(?:remains|is)\s+low|low\s+risk|risiko\s+rendah",text,re.I))
    return {"status":"Monitoring — low risk" if low_risk else "Monitoring","description":"MetMalaysia continued monitoring the potential for Anak Krakatau volcanic ash to reach Malaysia; the referenced assessment described the current ash-arrival risk as low." if low_risk else "Malaysia continued monitoring the potential regional ash impact from Anak Krakatau.","lat":3.139,"lng":101.6869,"source_method":"fixed_reference"}

def extract_status(text: str) -> str:
    if re.search(r"Level\s*II\s*(?:—|-|–)?\s*Waspada|Level\s*2.*?Waspada",text,re.I):
        return "Level II — Waspada"
    if re.search(r"Level\s*III\s*(?:—|-|–)?\s*Siaga|Level\s*3.*?Siaga",text,re.I):
        return "Level III — Siaga"
    return FALLBACK["status"]

def build_sources():
    out=[]
    for key,cfg in SOURCES.items():
        s=SOURCE_CACHE[key]
        out.append({
            "title":cfg["name"],"description":cfg["description"],"date":cfg["date"],
            "url":cfg["url"],"fetch_status":"OK" if s["ok"] else "UNAVAILABLE",
            "reference_type":"fixed_reference","source_status":"official_reference",
        })
    return out

def build_timeline():
    return [
        {"date":"2 July 2026, 16:30 WIB","title":"Level III — Siaga","description":"Gunung Anak Krakatau was raised to Level III (Siaga) after increased volcanic seismicity and deformation."},
        {"date":"2 July–3 September 2026","title":"224 eruptions recorded","description":"Badan Geologi reported 224 eruptions during the period of elevated activity up to 3 September 2026."},
        {"date":"4 September 2026 — 23:07 WIB","title":"Continuous eruption began","description":"A continuous eruption began and continued for approximately 25 hours."},
        {"date":"6 September 2026 — 00:04 WIB","title":"Continuous eruption ended","description":"The continuous eruption ended after approximately 25 hours, followed by additional Strombolian activity."},
        {"date":"6–8 September 2026","title":"Ash impact & aviation disruption","description":"Volcanic ash affected parts of Indonesia; multiple airports were temporarily closed and regional flights were disrupted."},
        {"date":"21 September 2026 — 18:30 WIB","title":"Status lowered to Level II","description":"Badan Geologi lowered the activity level from Level III (Siaga) to Level II (Waspada). This remained the latest official status evaluation in the trusted reference set as of 5 October 2026."},
    ]

def main():
    print("\n============================================================")
    print(" ANAK KRAKATAU 2026 — FIXED REFERENCE SCRAPER")
    print("============================================================")
    print(f"Data build date: {AS_OF_DATE}")
    print("Reference mode: fixed trusted URLs")

    DATA_DIR.mkdir(parents=True,exist_ok=True)
    collect_sources()

    geologi=first("geologi")["text"]
    kemenhub=first("kemenhub")["text"]
    kemenkes=first("kemenkes")["text"]
    kemenkes_health=first("kemenkes_health")["text"]
    bmkg=first("bmkg")["text"]
    singapore=first("singapore")["text"]
    malaysia_air=first("malaysia_airlines")["text"]
    malaysia=first("malaysia")["text"]

    status=extract_status(geologi)
    aviation=extract_aviation(kemenhub)
    health=extract_health(kemenkes,kemenkes_health)
    population=extract_population(kemenkes)
    si=singapore_info(singapore)
    mai=malaysia_airlines_info(malaysia_air)
    mm=malaysia_monitoring(malaysia)

    # Prefer the current official evaluation date from the trusted ESDM source.
    data={
        "metadata":{
            "last_updated":now_iso(),
            "last_updated_display":AS_OF_DATE + ", refresh run",
            "data_as_of":AS_OF_DATE,
            "latest_official_status_date":"21 September 2026, 18:30 WIB",
            "scraper":"scrape_anak_krakatau_2026.py",
            "author":"Kelvin Irawan",
            "reference_mode":"fixed_trusted_references",
            "description":"Automatically refreshed Anak Krakatau 2026 impact dashboard using a fixed trusted-reference set.",
            "note":"The latest official activity evaluation in the trusted reference set is effective 21 September 2026. A daily refresh updates the fetch timestamp while re-reading the same trusted references.",
        },
        "event":{
            "name":"Gunung Anak Krakatau","location":"Sunda Strait, Lampung","current_status":status,
            "status_date":"21 September 2026, 18:30 WIB",
            "level_iii_start":"2 July 2026, 16:30 WIB",
            "continuous_eruption_start":"4 September 2026, 23:07 WIB",
            "continuous_eruption_end":"6 September 2026, 00:04 WIB",
            "continuous_eruption_duration":"~25 hours",
            "eruptions_until_3_sep":224,
            "strombolian_after_continuous":7,
        },
        "population":{"exposed_population":population,"source_method":"fixed_reference"},
        "health":{**health,"source_method":"fixed_reference"},
        "aviation":{**aviation,"source_method":"fixed_reference"},
        "impacted_airports":AIRPORTS,
        "regional_impacts":{
            "indonesia_regions":["Lampung","Banten","DKI Jakarta","Jawa Barat","Bengkulu"],
            "indonesia_description":"Reported ash effects were documented across parts of Lampung, Banten, DKI Jakarta, Jawa Barat and Bengkulu.",
            "singapore":si,"malaysia_airlines":mai,"malaysia":mm,
        },
        "eruption":{"timeline":build_timeline()},
        "sources":build_sources(),
    }

    OUTPUT_JSON.write_text(json.dumps(data,ensure_ascii=False,indent=4),encoding="utf-8")
    GEOJSON["generated_at"]=now_iso()
    OUTPUT_GEOJSON.write_text(json.dumps(GEOJSON,ensure_ascii=False,indent=2),encoding="utf-8")

    print("\n============================================================")
    print(" SCRAPING COMPLETE")
    print("============================================================")
    print(f"Status: {status}")
    print(f"Population: {population:,}")
    print(f"Flights: {aviation['total_affected_flights']:,}")
    print(f"Passengers: {aviation['total_affected_passengers']:,}")
    print(f"Hospitals: {health['hospitals']:,}")
    print(f"Puskesmas: {health['puskesmas']:,}")
    print(f"ISPA: {health['ispa_cases']:,}")
    print("Regional: Singapore 8 relief flights; Malaysia Airlines 12 Jakarta cancellations; Malaysia monitoring risk low.")
    print(f"JSON: {OUTPUT_JSON}")
    print(f"GeoJSON: {OUTPUT_GEOJSON}")

if __name__=="__main__":
    try: main()
    except KeyboardInterrupt:
        print("\nStopped by user."); sys.exit(1)
    except Exception as exc:
        print("\nSCRAPER ERROR:"); print(exc); sys.exit(1)
