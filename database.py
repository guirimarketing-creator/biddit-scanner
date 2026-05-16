import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config import DB_PATH


@dataclass
class Property:
    biddit_id: str
    url: str
    title: str = ""
    address: str = ""
    city: str = ""
    postal_code: str = ""
    province: str = ""
    property_type: str = ""
    size_m2: Optional[float] = None
    size_estimated: bool = False   # True when size is estimated from bedrooms, not from page
    bedrooms: Optional[int] = None
    epc_score: str = ""
    cadastral_income: Optional[float] = None
    starting_price: Optional[float] = None
    current_bid: Optional[float] = None
    auction_date: str = ""
    image_url: str = ""
    renovation_state: str = ""          # "Goed" / "Op te frissen" / "Te renoveren" / etc.
    renovation_cost_estimate: Optional[float] = None  # € estimate added by analyzer
    estimated_monthly_rent: Optional[float] = None
    gross_yield: Optional[float] = None
    score: float = 0.0
    last_scraped: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    is_active: bool = True


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS properties (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                biddit_id       TEXT UNIQUE NOT NULL,
                url             TEXT,
                title           TEXT,
                address         TEXT,
                city            TEXT,
                postal_code     TEXT,
                province        TEXT,
                property_type   TEXT,
                size_m2         REAL,
                size_estimated  INTEGER DEFAULT 0,
                bedrooms        INTEGER,
                epc_score       TEXT,
                cadastral_income REAL,
                starting_price  REAL,
                current_bid     REAL,
                auction_date    TEXT,
                image_url       TEXT,
                renovation_state TEXT,
                renovation_cost_estimate REAL,
                estimated_monthly_rent REAL,
                gross_yield     REAL,
                score           REAL DEFAULT 0,
                last_scraped    TEXT,
                is_active       INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS scrape_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at      TEXT,
                finished_at     TEXT,
                total_found     INTEGER,
                total_scraped   INTEGER,
                total_in_region INTEGER,
                total_interesting INTEGER
            );
        """)


def upsert_property(prop: Property):
    with get_conn() as conn:
        d = prop.__dict__.copy()
        d["size_estimated"] = int(d.get("size_estimated", False))
        conn.execute("""
            INSERT INTO properties (
                biddit_id, url, title, address, city, postal_code, province,
                property_type, size_m2, size_estimated, bedrooms, epc_score, cadastral_income,
                starting_price, current_bid, auction_date, image_url,
                renovation_state, renovation_cost_estimate,
                estimated_monthly_rent, gross_yield, score, last_scraped, is_active
            ) VALUES (
                :biddit_id, :url, :title, :address, :city, :postal_code, :province,
                :property_type, :size_m2, :size_estimated, :bedrooms, :epc_score, :cadastral_income,
                :starting_price, :current_bid, :auction_date, :image_url,
                :renovation_state, :renovation_cost_estimate,
                :estimated_monthly_rent, :gross_yield, :score, :last_scraped, :is_active
            )
            ON CONFLICT(biddit_id) DO UPDATE SET
                url=excluded.url, title=excluded.title, address=excluded.address,
                city=excluded.city, postal_code=excluded.postal_code, province=excluded.province,
                property_type=excluded.property_type, size_m2=excluded.size_m2,
                size_estimated=excluded.size_estimated, bedrooms=excluded.bedrooms,
                epc_score=excluded.epc_score, cadastral_income=excluded.cadastral_income,
                starting_price=excluded.starting_price, current_bid=excluded.current_bid,
                auction_date=excluded.auction_date, image_url=excluded.image_url,
                renovation_state=excluded.renovation_state,
                renovation_cost_estimate=excluded.renovation_cost_estimate,
                estimated_monthly_rent=excluded.estimated_monthly_rent,
                gross_yield=excluded.gross_yield, score=excluded.score,
                last_scraped=excluded.last_scraped, is_active=excluded.is_active
        """, d)


def update_yields(biddit_id: str, monthly_rent: float, gross_yield: float,
                  score: float, renovation_cost: float | None = None):
    with get_conn() as conn:
        conn.execute("""
            UPDATE properties
            SET estimated_monthly_rent=?, gross_yield=?, score=?, renovation_cost_estimate=?
            WHERE biddit_id=?
        """, (monthly_rent, gross_yield, score, renovation_cost, biddit_id))


def get_all_active(province_filter: set[str] | None = None) -> list[sqlite3.Row]:
    with get_conn() as conn:
        if province_filter:
            placeholders = ",".join("?" * len(province_filter))
            return conn.execute(
                f"SELECT * FROM properties WHERE is_active=1 AND province IN ({placeholders}) ORDER BY gross_yield DESC NULLS LAST",
                list(province_filter),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM properties WHERE is_active=1 ORDER BY gross_yield DESC NULLS LAST"
        ).fetchall()


def get_scraped_ids() -> set[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT biddit_id FROM properties").fetchall()
        return {r["biddit_id"] for r in rows}


def mark_inactive(biddit_ids_to_keep: set[str]):
    with get_conn() as conn:
        conn.execute("UPDATE properties SET is_active=0")
        if biddit_ids_to_keep:
            placeholders = ",".join("?" * len(biddit_ids_to_keep))
            conn.execute(
                f"UPDATE properties SET is_active=1 WHERE biddit_id IN ({placeholders})",
                list(biddit_ids_to_keep),
            )


def log_run(started_at: str, finished_at: str, total_found: int,
            total_scraped: int, total_in_region: int, total_interesting: int):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO scrape_runs (started_at, finished_at, total_found, total_scraped, total_in_region, total_interesting)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (started_at, finished_at, total_found, total_scraped, total_in_region, total_interesting))
