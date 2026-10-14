"""Run the 99.co scraper on Apify, or load a JSON export of a previous run.

The scraper charges per listing returned, so every live run carries a hard
spending cap (config.MAX_COST_USD_PER_RUN) passed to Apify.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from .. import config

ACTOR_ID = "sian.agency~99co-property-scraper"
RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"


def search_input(max_results: int = config.MAX_RESULTS_PER_RUN) -> dict:
    """Actor input matching SPEC.md: condo rentals near Tanglin within budget."""
    lat, lng = config.ANCHOR_LATLNG
    return {
        "searchMode": "coordinates",
        "listingType": "rent",
        "latitude": str(lat),
        "longitude": str(lng),
        "radius": config.SEARCH_RADIUS_M,
        "propertyType": "condo",
        "propertySegment": "residential",
        "maxPrice": config.MAX_RENT,
        "minFloorArea": config.MIN_SQFT,
        "maxResults": max_results,
        "enrichListings": False,
    }


def run_live(token: str | None = None, max_results: int = config.MAX_RESULTS_PER_RUN,
             max_cost_usd: float = config.MAX_COST_USD_PER_RUN) -> list[dict]:
    token = token or os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN is not set. Put it in the .env file (see .env.example).")
    query = urllib.parse.urlencode({"maxTotalChargeUsd": max_cost_usd, "timeout": 280})
    req = urllib.request.Request(
        f"{RUN_SYNC_URL}?{query}",
        data=json.dumps(search_input(max_results)).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)


def load_file(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of listings (Apify dataset export).")
    return data
