"""Run listing scrapers on Apify, or load a JSON export of a previous run.

Every live run carries a hard spending cap (config.MAX_COST_USD_PER_RUN).
PropertyGuru is the main source; 99.co is optional and ~10x pricier per listing.
"""

from __future__ import annotations

import json
import os
import time
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


API = "https://api.apify.com/v2"


def _call(method: str, url: str, token: str, body: dict | None = None, timeout: int = 90):
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def run_actor(actor: str, actor_input: dict, token: str | None = None,
              max_cost_usd: float = config.MAX_COST_USD_PER_RUN,
              max_minutes: int = 20) -> list[dict]:
    """Start the actor, wait for it, return its dataset items.

    Uses an asynchronous run (the synchronous endpoint gives up after 5 minutes,
    and a full sweep of all areas can take longer).
    """
    token = token or os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN is not set. Put it in the .env file (see .env.example).")
    q = urllib.parse.urlencode({"maxTotalChargeUsd": max_cost_usd, "timeout": max_minutes * 60})
    run = _call("POST", f"{API}/acts/{actor.replace('/', '~')}/runs?{q}", token, actor_input)["data"]
    deadline = time.time() + max_minutes * 60 + 120
    while run["status"] in ("READY", "RUNNING") and time.time() < deadline:
        run = _call("GET", f"{API}/actor-runs/{run['id']}?waitForFinish=60", token)["data"]
    if run["status"] not in ("SUCCEEDED", "TIMED-OUT", "ABORTED"):
        raise RuntimeError(f"Apify run {run['id']} ended with status {run['status']}")
    items, offset = [], 0
    while True:   # page through the dataset; partial results are still useful
        page = _call("GET", f"{API}/datasets/{run['defaultDatasetId']}/items"
                            f"?clean=true&format=json&limit=1000&offset={offset}", token)
        items += page
        if len(page) < 1000:
            return items
        offset += 1000


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
