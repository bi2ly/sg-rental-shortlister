"""Building coordinates via OneMap (Singapore Land Authority, free, no key),
and the search-area check.

Each building is looked up once and cached in data/geocode_cache.json.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from . import config
from .models import Listing
from .pricing.matching import normalise as norm_name

ONEMAP_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
CACHE = Path(__file__).resolve().parents[1] / "data" / "geocode_cache.json"


def in_area(lat: float, lng: float, box: dict = config.AREA_BBOX) -> bool:
    return box["lat_min"] <= lat <= box["lat_max"] and box["lng_min"] <= lng <= box["lng_max"]


def parse_onemap(payload: dict, building: str) -> tuple[float, float] | None:
    """Pick the result whose BUILDING matches; else the first result."""
    results = payload.get("results") or []
    if not results:
        return None
    want = norm_name(building)
    best = next((r for r in results if norm_name(r.get("BUILDING", "")) == want), results[0])
    lng = best.get("LONGITUDE") or best.get("LONGTITUDE")   # older API spelling
    return float(best["LATITUDE"]), float(lng)


class Geocoder:
    def __init__(self, cache_path: Path = CACHE, fetch=None):
        self.cache_path = Path(cache_path)
        self.cache: dict = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        self._fetch = fetch or self._onemap

    @staticmethod
    def _onemap(query: str) -> dict:
        q = urllib.parse.urlencode({"searchVal": query, "returnGeom": "Y",
                                    "getAddrDetails": "Y", "pageNum": 1})
        with urllib.request.urlopen(f"{ONEMAP_URL}?{q}", timeout=20) as resp:
            return json.load(resp)

    def locate(self, building: str, street: str | None = None) -> tuple[float, float] | None:
        key = norm_name(building)
        if key not in self.cache:
            point = None
            for query in filter(None, [building, f"{building} {street}" if street else None, street]):
                try:
                    point = parse_onemap(self._fetch(query), building)
                except OSError:
                    point = None
                if point:
                    break
            self.cache[key] = list(point) if point else None
            self.save()
        hit = self.cache[key]
        return tuple(hit) if hit else None

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=1, sort_keys=True))


def place(listings: list[Listing], geocoder: Geocoder,
          streets: dict[str, str] | None = None) -> tuple[list[Listing], list[tuple[str, str]]]:
    """Fill missing coordinates, then keep listings inside the search area.
    Listings whose building can't be located are kept (flagged later)."""
    from dataclasses import replace
    kept, dropped = [], []
    for l in listings:
        if l.lat is None or l.lng is None:
            point = geocoder.locate(l.project, (streets or {}).get(l.listing_id))
            if point:
                l = replace(l, lat=point[0], lng=point[1])
        if l.district and l.district not in config.AREA_DISTRICTS:
            dropped.append((l.project, f"outside the search area (D{l.district:02d})"))
            continue
        if l.lat is not None and not in_area(l.lat, l.lng):
            dropped.append((l.project, "outside the search area"))
            continue
        kept.append(l)
    return kept, dropped
