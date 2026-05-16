"""
Orchestrator: scrape → analyze → report.
Run this directly or let launchd call it weekly.
"""

import asyncio
from datetime import datetime, timezone

from database import init_db, log_run
from scraper import run_scraper
from analyzer import run_analyzer
from report import generate_report


async def main(limit: int | None = None, skip_scrape: bool = False, no_open: bool = False):
    started_at = datetime.now(timezone.utc).isoformat()
    print(f"\n{'='*60}")
    print(f"Biddit Scanner — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    init_db()

    total_found = 0
    scraped_props = []

    if not skip_scrape:
        print("Step 1/3: Scraping biddit.be...")
        total_found, scraped_props = await run_scraper(limit=limit)
    else:
        print("Step 1/3: Skipping scrape (--no-scrape flag set)")

    print("\nStep 2/3: Analyzing rental yields...")
    stats = run_analyzer()
    stats["total_found"] = total_found

    print("\nStep 3/3: Generating HTML report...")
    report_path = generate_report(stats, auto_open=not no_open)

    finished_at = datetime.now(timezone.utc).isoformat()
    log_run(
        started_at=started_at,
        finished_at=finished_at,
        total_found=total_found,
        total_scraped=len(scraped_props),
        total_in_region=stats.get("total_in_region", 0),
        total_interesting=stats.get("total_interesting", 0),
    )

    print(f"\n{'='*60}")
    print(f"Done! Report: {report_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Biddit weekly real estate scanner")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of properties to scrape (for testing)")
    parser.add_argument("--no-scrape", action="store_true",
                        help="Skip scraping, only re-analyze and regenerate report from existing DB")
    parser.add_argument("--no-open", action="store_true",
                        help="Don't auto-open the HTML report in browser")
    args = parser.parse_args()

    asyncio.run(main(limit=args.limit, skip_scrape=args.no_scrape, no_open=args.no_open))
