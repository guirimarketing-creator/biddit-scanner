"""
Scraper for biddit.be using Playwright (site is JS-rendered).

Flow:
  1. Fetch sitemap XML files to collect all property IDs.
  2. For each new/stale property ID, open the detail page with Playwright
     and extract structured data.
  3. Upsert into SQLite.
"""

import asyncio
import re
import xml.etree.ElementTree as ET

import requests
from playwright.async_api import async_playwright, Page, Browser

from config import (
    SITEMAP_INDEX, PROPERTY_URL_TEMPLATE,
    SCRAPER_CONCURRENCY, SCRAPER_DELAY, postal_to_province,
)
from database import Property, upsert_property, get_scraped_ids, init_db

STALE_AFTER_DAYS = 7


def fetch_all_property_ids() -> set[str]:
    """Download sitemap index → individual sitemaps → collect all NL property IDs."""
    ids: set[str] = set()
    try:
        resp = requests.get(SITEMAP_INDEX, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        sitemap_locs = [el.text for el in root.findall(".//sm:loc", ns) if el.text]
    except Exception as e:
        print(f"[scraper] Failed to fetch sitemap index: {e}")
        return ids

    # Only process Dutch (nl) sitemaps
    nl_sitemaps = [loc for loc in sitemap_locs if "/nl_sitemap" in loc]

    for sitemap_url in nl_sitemaps:
        try:
            resp = requests.get(sitemap_url, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc_el in root.findall(".//sm:loc", ns):
                url = loc_el.text or ""
                m = re.search(r"/catalog/detail/(\d+)", url)
                if m:
                    ids.add(m.group(1))
        except Exception as e:
            print(f"[scraper] Failed to fetch {sitemap_url}: {e}")

    print(f"[scraper] Found {len(ids)} property IDs in sitemaps")
    return ids


def _parse_be_number(text: str) -> float | None:
    """Parse Belgian/Dutch formatted numbers where '.' = thousands sep and ',' = decimal."""
    if not text:
        return None
    text = re.sub(r"[€\s\xa0]", "", text).strip()
    if not text:
        return None
    if "," in text:
        # e.g. "195.000,50" → 195000.50
        integer_part, _, decimal_part = text.rpartition(",")
        integer_part = integer_part.replace(".", "")
        try:
            return float(f"{integer_part}.{decimal_part}")
        except ValueError:
            return None
    else:
        # e.g. "195.000" → 195000  OR  "195" → 195
        no_dots = text.replace(".", "")
        try:
            return float(no_dots)
        except ValueError:
            return None


# Aliases used elsewhere
_parse_price = _parse_be_number
_parse_float = _parse_be_number


def _parse_int(text: str) -> int | None:
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else None


async def scrape_property(page: Page, prop_id: str) -> Property | None:
    url = PROPERTY_URL_TEMPLATE.format(id=prop_id)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_selector("h1", timeout=8000)
        except Exception:
            pass

        data = await page.evaluate("""
        () => {
            const getAttr = (sel, attr) => {
                const el = document.querySelector(sel);
                return el ? (el.getAttribute(attr) || '').trim() : '';
            };
            const title = (document.querySelector('h1') || {}).innerText || '';
            const bodyText = document.body.innerText;
            const img = getAttr('meta[property="og:image"]', 'content')
                     || getAttr('img[src*="/images/"]', 'src')
                     || '';
            return { title, bodyText, img };
        }
        """)

        body = data.get("bodyText", "")
        title = data.get("title", "").strip()
        image_url = data.get("img", "")

        # --- Address ----------------------------------------------------------
        # Biddit format: "{postal} {city}- {street} {number}"
        # Separator is always "- " (dash + space); city names may also contain
        # hyphens (e.g. "Sint-Truiden- Kerklaan 5"), so we split on the LAST
        # occurrence of "- " within the address line.
        # We only look in the first 600 chars to avoid the footer copyright line
        # "©2024 Koninklijke Federatie van het Belgisch Notariaat".
        head = body[:600]
        postal_code, city, street = "", "", ""
        line_match = re.search(r"\b(\d{4})\s+([^\n]+)", head)
        if line_match:
            postal_code = line_match.group(1)
            addr_part = line_match.group(2).strip()
            if "- " in addr_part:
                city_part, street_part = addr_part.rsplit("- ", 1)
                city = city_part.strip().rstrip("-").strip()
                street = street_part.strip().split("\n")[0].strip()
            else:
                city = addr_part.split("\n")[0].strip()
        else:
            pc_match = re.search(r"\b(\d{4})\b", head)
            if pc_match:
                postal_code = pc_match.group(1)

        province = postal_to_province(postal_code) or ""
        address = f"{street}" if street else ""

        # --- Property type from title -----------------------------------------
        # Title examples: "Huis te koop - 3 kamer(s)", "Appartement te koop"
        title_lower = (title + " " + body[:200]).lower()
        property_type = "unknown"
        for ptype, keywords in [
            ("garage", ["garage", "garagebox", "box te koop", "parkeerplaats",
                        "parking te koop", "carport", "staanplaats"]),
            ("land", ["bouwgrond", "perceel", "landbouwgrond", "grond te koop"]),
            ("apartment", ["appartement", "flat", "studio", "duplex", "triplex"]),
            ("house", ["woning", "woonhuis", "villa", "rijwoning", "halfopen",
                       "open bebouwing", "bungalow", "huis te koop"]),
            ("commercial", ["handelspand", "kantoor", "magazijn", "loods"]),
        ]:
            if any(kw in title_lower for kw in keywords):
                property_type = ptype
                break

        # --- Livable surface --------------------------------------------------
        # Prefer the explicit "Bewoonbare oppervlakte" field. Never fall back to
        # "Oppervlakte grond" (land area). If absent, estimate from bedrooms later.
        size_m2 = None
        size_exact = False
        size_match = re.search(
            r"Bewoonbare oppervlakte\s*\n?\s*([\d.,]+)\s*m[²2]", body, re.IGNORECASE
        )
        if size_match:
            size_m2 = _parse_be_number(size_match.group(1))
            size_exact = True

        # --- Bedrooms --------------------------------------------------------
        bed_match = re.search(
            r"Aantal slaapkamers\s*\n?\s*(\d+)", body, re.IGNORECASE
        )
        if not bed_match:
            bed_match = re.search(
                r"(\d+)\s*(?:slaapkamers?|chambres?)", body, re.IGNORECASE
            )
        bedrooms = int(bed_match.group(1)) if bed_match else None

        # --- Size fallback: estimate from bedrooms when not explicitly listed --
        if not size_exact and bedrooms is not None:
            BEDROOM_SIZE = {0: 45, 1: 60, 2: 85, 3: 110, 4: 135, 5: 155}
            size_m2 = BEDROOM_SIZE.get(bedrooms, 155 + (bedrooms - 5) * 15)
            # For apartments cap the estimate conservatively
            if property_type == "apartment":
                size_m2 = min(size_m2, 100)

        # --- Renovation state ------------------------------------------------
        # "Staat van het gebouw\nGoed" / "Te renoveren" / "Op te frissen"
        renov_match = re.search(
            r"Staat van het gebouw\s*\n?\s*([^\n]+)", body, re.IGNORECASE
        )
        renovation_state = renov_match.group(1).strip() if renov_match else ""

        # --- EPC -------------------------------------------------------------
        epc_match = re.search(r"\bEPC[:\s]+([A-G][+]?)\b", body, re.IGNORECASE)
        epc_score = epc_match.group(1).upper() if epc_match else ""

        # --- Cadastral income (KI / kadastraal inkomen) ----------------------
        ki_match = re.search(
            r"(?:Kadastraal inkomen|KI|RC)\s*[:\n]\s*€?\s*([\d.,]+)",
            body, re.IGNORECASE,
        )
        cadastral_income = _parse_be_number(ki_match.group(1)) if ki_match else None

        # --- Starting price --------------------------------------------------
        # Auction:  "Bieden vanaf\n€ 195.000"
        # Private:  "Gewenste prijs\n\n€\xa0187.000"
        price_match = re.search(
            r"(?:Bieden vanaf|Gewenste prijs)\s*\n?\s*€[\s\xa0]*([\d.,]+)",
            body, re.IGNORECASE,
        )
        starting_price = _parse_be_number(price_match.group(1)) if price_match else None

        # --- Current bid -----------------------------------------------------
        bid_match = re.search(
            r"(?:Huidig bod|Offre actuelle)\s*\n?\s*€\s*([\d.,]+)",
            body, re.IGNORECASE,
        )
        current_bid = _parse_be_number(bid_match.group(1)) if bid_match else None

        # --- Auction end date ------------------------------------------------
        # "eindigt op 21/05/2026 om 12:00 uur"
        date_match = re.search(
            r"eindigt op\s+(\d{1,2}/\d{1,2}/\d{4})", body, re.IGNORECASE
        )
        if not date_match:
            date_match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", body)
        auction_date = date_match.group(1) if date_match else ""

        prop = Property(
            biddit_id=prop_id,
            url=url,
            title=title[:300],
            address=address[:200],
            city=city[:100],
            postal_code=postal_code,
            province=province,
            property_type=property_type,
            size_m2=size_m2,
            size_estimated=not size_exact and size_m2 is not None,
            bedrooms=bedrooms,
            epc_score=epc_score,
            cadastral_income=cadastral_income,
            starting_price=starting_price,
            current_bid=current_bid,
            auction_date=auction_date,
            image_url=image_url[:500],
            renovation_state=renovation_state[:100],
        )
        return prop

    except Exception as e:
        print(f"[scraper] Error scraping {url}: {e}")
        return None


async def scrape_worker(
    browser: Browser,
    queue: asyncio.Queue,
    results: list,
    semaphore: asyncio.Semaphore,
):
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    )
    page = await context.new_page()
    try:
        while True:
            try:
                prop_id = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            async with semaphore:
                prop = await scrape_property(page, prop_id)
                if prop:
                    results.append(prop)
                    upsert_property(prop)
                    status = f"province={prop.province}" if prop.province else "no province"
                    print(f"[scraper] {prop_id} → {prop.city or '?'} ({status}) | price={prop.starting_price}")
                await asyncio.sleep(SCRAPER_DELAY)
            queue.task_done()
    finally:
        await page.close()
        await context.close()


async def run_scraper(limit: int | None = None) -> tuple[int, list[Property]]:
    """
    Returns (total_ids_found, scraped_properties_list).
    `limit` caps the number of properties scraped (useful for testing).
    """
    init_db()
    all_ids = fetch_all_property_ids()

    if not all_ids:
        print("[scraper] No property IDs found. Aborting.")
        return 0, []

    # Determine which IDs need (re)scraping
    existing_ids = get_scraped_ids()
    ids_to_scrape = list(all_ids - existing_ids)
    print(f"[scraper] {len(ids_to_scrape)} new IDs to scrape (skipping {len(existing_ids)} already in DB)")

    if limit:
        ids_to_scrape = ids_to_scrape[:limit]
        print(f"[scraper] Limited to {limit} properties")

    if not ids_to_scrape:
        print("[scraper] Nothing new to scrape.")
        return len(all_ids), []

    queue: asyncio.Queue = asyncio.Queue()
    for pid in ids_to_scrape:
        await queue.put(pid)

    results: list[Property] = []
    semaphore = asyncio.Semaphore(1)  # One request at a time per worker

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        workers = [
            scrape_worker(browser, queue, results, semaphore)
            for _ in range(min(SCRAPER_CONCURRENCY, len(ids_to_scrape)))
        ]
        await asyncio.gather(*workers)
        await browser.close()

    print(f"[scraper] Done. Scraped {len(results)} properties.")
    return len(all_ids), results


if __name__ == "__main__":
    total, props = asyncio.run(run_scraper(limit=10))
    print(f"Scraped {len(props)} of {total} total properties (limited run)")
