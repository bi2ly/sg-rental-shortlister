"""Turn raw 99.co scraper rows (sian.agency/99co-property-scraper) into Listings.

Findings from the first real export (2026-10-14), which shape the rules below:
- Room rentals are mixed into "condo" results. Most carry listingType "room",
  but some are posted as normal rentals and only the text gives them away. They show the WHOLE unit's sqft
  with a room price (e.g. S$1,200 for 1,200 sqft), so they must be removed or
  they look like incredible deals.
- `bedrooms` is -1 both for rooms and for some studios.
- There is no full description without paid enrichment, only a short
  `highlights` line, so "study" can only be detected from title/highlights.
- Agent name/phone is included; we never store it.
- The scraper's `url` (99.co/singapore/listings/<id>) returns 404. The short
  link 99.co/property/<id> redirects to the real listing page, so we build that.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..models import Listing

ROOM_WORDS = re.compile(
    r"\b(rooms?|co-?living|co living|roommates?|housemates?|ensuite room|master room|common room)\b",
    re.IGNORECASE,
)
STUDIO_WORDS = re.compile(r"\bstudio\b", re.IGNORECASE)
ONE_BED_WORDS = re.compile(r"\b(1|one)[ -]?(bed|bedder|bedroom|br)\b", re.IGNORECASE)
STUDY_WORDS = re.compile(r"\bstudy\b|\b1\s*\+\s*1\b|\b1\s*\+\s*s\b", re.IGNORECASE)

# No whole condo unit within reach of Tanglin rents for under this per sqft.
ROOM_PSF_CEILING = 2.5


def _text(raw: dict) -> str:
    return " ".join(str(raw.get(k) or "") for k in ("listingTitle", "highlights"))


def room_reason(raw: dict) -> str | None:
    """Return why a row looks like a room rental, or None for a whole unit."""
    text = _text(raw)
    beds = (raw.get("specs") or {}).get("bedrooms")
    price = (raw.get("pricing") or {}).get("price") or 0
    sqft = (raw.get("specs") or {}).get("floorAreaSqft") or 0
    if raw.get("listingType") == "room":
        return "listed as a room on 99.co"
    if ROOM_WORDS.search(text):
        return "listing text mentions a room / co-living"
    if beds == -1 and not STUDIO_WORDS.search(text):
        return "no bedroom count and not a studio (typical of room rentals)"
    if sqft and price / sqft < ROOM_PSF_CEILING:
        return f"S${price / sqft:.2f} psf is far too low for a whole unit"
    return None


def _posted_iso(value) -> str | None:
    """postedAt arrives in microseconds since epoch; handle ms/s too."""
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    seconds = value / 1e6 if value > 1e14 else value / 1e3 if value > 1e11 else value
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat(timespec="seconds")


def listing_url(raw: dict) -> str | None:
    pid = raw.get("propertyId")
    return f"https://www.99.co/property/{pid}" if pid else raw.get("url")


def to_listing(raw: dict) -> Listing | None:
    """Map one raw row to a Listing. Returns None if essential data is missing."""
    pricing, specs = raw.get("pricing") or {}, raw.get("specs") or {}
    rent, sqft = pricing.get("price"), specs.get("floorAreaSqft")
    project = raw.get("projectName") or raw.get("listingTitle")
    if not (project and rent and sqft):
        return None
    beds = specs.get("bedrooms")
    if beds == -1:
        beds = 0 if STUDIO_WORDS.search(_text(raw)) else None
    elif beds == 0 and ONE_BED_WORDS.search(_text(raw)):
        beds = 1   # agents sometimes tag a "1 bedder" as studio
    loc = raw.get("location") or {}
    return Listing(
        project=project,
        rent=float(rent),
        sqft=float(sqft),
        bedrooms=beds,
        has_study=bool(STUDY_WORDS.search(_text(raw))),
        url=listing_url(raw),
        listing_id=raw.get("propertyId"),
        source="99.co",
        title=raw.get("listingTitle"),
        highlights=raw.get("highlights"),
        district=(raw.get("address") or {}).get("district"),
        lat=loc.get("latitude"),
        lng=loc.get("longitude"),
        completed_year=specs.get("completedYear"),
        photo_count=(raw.get("media") or {}).get("photoCount") or 0,
        posted_at=_posted_iso(raw.get("postedAt")),
    )


def normalise(rows: list[dict]) -> tuple[list[Listing], list[tuple[str, str]]]:
    """Return (whole-unit listings, [(project, reason) for rows dropped])."""
    kept, dropped = [], []
    for raw in rows:
        if raw.get("listingType") == "sale" or raw.get("status") not in (None, "active"):
            dropped.append((str(raw.get("projectName")), "not an active rental"))
            continue
        reason = room_reason(raw)
        if reason:
            dropped.append((str(raw.get("projectName")), f"room rental: {reason}"))
            continue
        listing = to_listing(raw)
        if listing is None:
            dropped.append((str(raw.get("projectName")), "missing rent, size or project"))
            continue
        kept.append(listing)
    return kept, dropped
