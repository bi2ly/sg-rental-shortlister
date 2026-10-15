"""Run listing scrapers on Apify, or load a JSON export of a previous run.

Every live run carries a hard spending cap (config.MAX_COST_USD_PER_RUN).
PropertyGuru is the main source; 99.co is optional and ~10x pricier per listing.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from .. import config


def propertyguru_input(max_items: int = config.MAX_RESULTS_PER_RUN, since: str | None = None) -> dict:
    """One keyword search per area; price filter server-side, the rest in our code."""
    inp = {
        "searchType": "rent",
        "keywords": config.AREA_KEYWORDS,
        "maxPrice": config.MAX_RENT,
        "minBedrooms": 1,
        "scrapeDetails": False,          # card mode: cheap, enough fields
        "maxItems": max_items,
        "maxPages": config.PG_MAX_PAGES_PER_AREA,
    }
    if since:
        inp["since"] = since             # only listings posted after the last run
    return inp


def ninetynine_input(max_results: int = 60) -> dict:
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
        "minFloorArea": min(config.MIN_SQFT, config.MIN_SQFT_WITH_STUDY),
        "maxResults": max_results,
        "enrichListings": False,
    }


# Kept for backwards compatibility with earlier code/tests.
search_input = ninetynine_input


def run_actor(actor: str, actor_input: dict, token: str | None = None,
              max_cost_usd: float = config.MAX_COST_USD_PER_RUN) -> list[dict]:
    token = token or os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN is not set. Put it in the .env file (see .env.example).")
    actor_path = actor.replace("/", "~")
    query = urllib.parse.urlencode({"maxTotalChargeUsd": max_cost_usd, "timeout": 600})
    req = urllib.request.Request(
        f"https://api.apify.com/v2/acts/{actor_path}/run-sync-get-dataset-items?{query}",
        data=json.dumps(actor_input).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=620) as resp:
        return json.load(resp)


def run_live(source: str = "propertyguru", since: str | None = None, **kw) -> list[dict]:
    if source == "propertyguru":
        return run_actor(config.PG_ACTOR, propertyguru_input(since=since), **kw)
    if source == "99co":
        return run_actor(config.NINETYNINE_ACTOR, ninetynine_input(), **kw)
    raise ValueError(f"unknown source {source!r}")


def load_file(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of listings (Apify dataset export).")
    return data
