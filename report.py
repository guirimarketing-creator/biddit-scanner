"""
Generate an HTML report from the current DB state.
"""

import subprocess
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config import BASE_DIR, REPORT_DIR, INCLUDED_PROVINCES, MIN_YIELD
from database import get_all_active


def generate_report(stats: dict, auto_open: bool = True) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    rows = get_all_active(province_filter=INCLUDED_PROVINCES)

    # Convert sqlite3.Row objects to dicts for Jinja2
    all_properties = [dict(r) for r in rows]
    top_picks = [p for p in all_properties if (p.get("gross_yield") or 0) >= MIN_YIELD]
    top_picks.sort(key=lambda p: p.get("gross_yield") or 0, reverse=True)

    env = Environment(loader=FileSystemLoader(str(BASE_DIR / "templates")))
    template = env.get_template("report.html")

    run_date = datetime.now().strftime("%d/%m/%Y %H:%M")
    html = template.render(
        run_date=run_date,
        min_yield=MIN_YIELD,
        stats={
            "total_found": stats.get("total_found", len(all_properties)),
            "total_in_region": len(all_properties),
            "total_with_yield": stats.get("total_with_yield", 0),
            "total_interesting": len(top_picks),
        },
        top_picks=top_picks,
        all_properties=all_properties,
    )

    report_path = REPORT_DIR / f"biddit_report_{datetime.now().strftime('%Y-%m-%d')}.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"[report] Report written to {report_path}")

    if auto_open:
        subprocess.run(["open", str(report_path)], check=False)

    return report_path


if __name__ == "__main__":
    from database import init_db
    init_db()
    generate_report(stats={}, auto_open=True)
