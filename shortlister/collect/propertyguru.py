"""Turn raw PropertyGuru rows (automation-lab/propertyguru-singapore-listings-
agent-leads-scraper, card mode) into Listings.

Findings from the first real run (2026-10-15):
- Card mode returns price, bedrooms, sqft, type code, district and a working
  listing URL, but no coordinates, build year or description. Coordinates are
  looked up from the building name with OneMap (see geo.py).
- Searches are by area keyword and also pull in walk-ups (WALK), tiny units and
  rooms, so filtering here matters.
- A "studio" can be tagged bedrooms=1; the title often gives it away.
"""

from __future__ import annotations

import re

from .. import config
from ..models import Listing
from .ninetynine import ONE_BED_WORDS, ROOM_PSF_CEILING, ROOM_WORDS, STUDIO_WORDS, STUDY_WORDS

# Agent adverts / dorms / short stays, not a specific unit (seen in the first
# full sweep, 2026-10-15).
ADVERT_WORDS = re.compile(
    r"work ?permit|workers|\bpax\b|dorm|short[- ]?term|hotel|accommodation|serviced"
    r"|walk-?up|shophouse|landed|\bany(where)?\b|for expat|monthly rental",
    re.IGNORECASE,
)
MAX_TITLE_LEN = 60    # real project names are short; long titles are adverts

STREET = re.compile(r"^\s*([^,]+)")   # "262 BALESTIER ROAD, Balestier / Toa Payoh"


def is_propertyguru(raw: dict) -> bool:
    return "listingId" in raw or "propertyguru.com" in str(raw.get("url", ""))


def street_of(raw: dict) -> str | None:
    m = STREET.match(raw.get("address") or "")
    return m.group(1).strip() if m else None


def skip_reason(raw: dict) -> str | None:
    title = raw.get("title") or ""
    price, sqft = raw.get("price") or 0, raw.get("floorAreaSqft") or 0
    if str(raw.get("listingType", "")).upper() != "RENT" or raw.get("status") not in (None, "ACT"):
        return "not an active rental"
    ptype = str(raw.get("propertyType", "")).upper()
    if ptype not in config.PG_KEEP_TYPES:
        return f"property type {ptype or 'unknown'} (not a condo/apartment)"
    if ROOM_WORDS.search(title):
        return "room rental: listing title mentions a room"
    if ADVERT_WORDS.search(title) or len(title) > MAX_TITLE_LEN:
        return "agent advert / dorm / short stay, not a specific unit"
    if sqft and price and price / sqft < ROOM_PSF_CEILING:
        return f"room rental: S${price / sqft:.2f} psf is far too low for a whole unit"
    if not (price and sqft):
        return "missing rent or size"
    return None


def to_listing(raw: dict) -> Listing:
    title = raw.get("title") or ""
    beds = raw.get("bedrooms")
    if STUDIO_WORDS.search(title) and not ONE_BED_WORDS.search(title):
        beds = 0
    district = re.sub(r"\D", "", str(raw.get("districtCode") or "")) or None
    return Listing(
        project=title,
        rent=float(raw["price"]),
        sqft=float(raw["floorAreaSqft"]),
        bedrooms=beds,
        has_study=bool(STUDY_WORDS.search(title)),
        url=raw.get("url"),
        listing_id=str(raw.get("listingId")),
        source="PropertyGuru",
        title=title,
        highlights=raw.get("address"),
        district=int(district) if district else None,
        photo_count=len(raw.get("imageUrls") or []),
        area=raw.get("district") or None,
    )


def normalise(rows: list[dict]) -> tuple[list[Listing], list[tuple[str, str]]]:
    kept, dropped = [], []
    for raw in rows:
        reason = skip_reason(raw)
        if reason:
            dropped.append((str(raw.get("title")), reason))
        else:
            kept.append(to_listing(raw))
    return kept, dropped


# --- Full-page details for shortlisted units only ------------------------------

def detail_input(urls: list[str]) -> dict:
    return {"startUrls": [{"url": u} for u in urls], "scrapeDetails": True,
            "maxItems": len(urls)}


def sg_date(iso: str | None) -> str | None:
    """'2026-11-04T16:00:00.000Z' (midnight Singapore time) -> '2026-11-05'."""
    if not iso:
        return None
    from datetime import datetime, timedelta, timezone
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone(timedelta(hours=8))).date().isoformat()


def clean_mrt(name: str | None) -> str | None:
    """'NE9 Boon Keng MRT Station' -> 'Boon Keng MRT'."""
    if not name:
        return None
    name = re.sub(r"^\s*([A-Z]{1,3}\d{1,2}\s*)+", "", name)
    return re.sub(r"\s+Station\s*$", "", name).strip() or None


def apply_details(listings: list[Listing], rows: list[dict]) -> list[Listing]:
    """Add availability date (and study, from the agent's headline/description)."""
    from dataclasses import replace
    by_id = {str(r.get("listingId")): r for r in rows}
    out = []
    for l in listings:
        r = by_id.get(l.listing_id)
        if r:
            text = " ".join(str(r.get(k) or "") for k in ("headline", "description"))
            mrts = [m.get("name") for m in (r.get("mrt") or []) if isinstance(m, dict)]
            l = replace(l, available_from=sg_date(r.get("availableAt")), details_fetched=True,
                        mrt_name=clean_mrt(mrts[0]) if mrts else None,
                        area=r.get("district") or l.area,
                        has_study=l.has_study or bool(STUDY_WORDS.search(text)),
                        highlights=r.get("headline") or l.highlights)
        out.append(l)
    return out
