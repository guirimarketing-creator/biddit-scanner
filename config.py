from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "biddit.db"
REPORT_DIR = BASE_DIR / "reports"

MIN_YIELD = 5.0  # Minimum gross rental yield % to flag as interesting

SITEMAP_INDEX = "https://www.biddit.be/stg/eco/sitemap_index.xml"
SITEMAP_BASE = "https://www.biddit.be/stg/eco/"
PROPERTY_URL_TEMPLATE = "https://www.biddit.be/nl/catalog/detail/{id}"

SCRAPER_CONCURRENCY = 4   # Parallel Playwright browser contexts
SCRAPER_DELAY = 1.5        # Seconds between requests per context

# Belgian postal code → province mapping
# Each entry: (start, end_inclusive, province_name)
POSTAL_CODE_RANGES = [
    (1000, 1299, "Brussels"),
    (1300, 1499, "Brabant wallon"),
    (1500, 1999, "Vlaams-Brabant"),
    (2000, 2999, "Antwerpen"),
    (3000, 3499, "Vlaams-Brabant"),
    (3500, 3999, "Limburg"),
    (4000, 4999, "Liège"),
    (5000, 5999, "Namur"),
    (6000, 6599, "Hainaut"),
    (6600, 6999, "Luxembourg"),
    (7000, 7999, "Hainaut"),
    (8000, 8999, "West-Vlaanderen"),
    (9000, 9999, "Oost-Vlaanderen"),
]

# Provinces to INCLUDE (Flanders minus West Flanders)
INCLUDED_PROVINCES = {"Antwerpen", "Oost-Vlaanderen", "Vlaams-Brabant", "Limburg"}
EXCLUDED_PROVINCES = {"West-Vlaanderen"}


def postal_to_province(postal_code: str) -> str | None:
    try:
        code = int(str(postal_code).strip()[:4])
    except (ValueError, TypeError):
        return None
    for start, end, province in POSTAL_CODE_RANGES:
        if start <= code <= end:
            return province
    return None


def is_in_target_region(province: str) -> bool:
    return province in INCLUDED_PROVINCES


# Property types excluded from yield analysis and report
EXCLUDED_PROPERTY_TYPES = {"land", "garage", "commercial"}

# EPC scoring for bonus calculation (A=best, G=worst)
EPC_RANK = {"A+": 0, "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7}

# Major cities that add a location bonus
MAJOR_CITIES = {"antwerpen", "gent", "leuven", "mechelen", "hasselt", "genk", "aalst", "sint-niklaas"}
