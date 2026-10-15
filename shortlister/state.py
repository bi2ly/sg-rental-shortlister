"""Memory of listings already sent, so each run alerts only on what's new.

Stored durably in an Apify key-value store (same APIFY_TOKEN), because GitHub's
cache can be evicted. Falls back to a local file when there's no token.

Format: {listing_key: {"rent": 3400, "first_seen": "2026-10-15"}}
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Listing

STORE_NAME = "sg-rental-shortlister"
RECORD = "seen-listings"
LOCAL = Path(__file__).resolve().parents[1] / "data" / "seen.json"
API = "https://api.apify.com/v2"
FORGET_AFTER_DAYS = 60   # a unit relisted after 2 months counts as new again


def key(l: Listing) -> str:
    return f"{l.source}:{l.listing_id or l.url}"


class SeenStore:
    def __init__(self, token: str | None = None, local: Path = LOCAL):
        self.token = token if token is not None else os.environ.get("APIFY_TOKEN")
        self.local = Path(local)
        self._store_id: str | None = None
        self.data: dict = {}

    # --- backends -------------------------------------------------------------
    def _req(self, method: str, url: str, body: bytes | None = None, ctype="application/json"):
        req = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": ctype})
        return urllib.request.urlopen(req, timeout=60)

    def _store(self) -> str:
        if not self._store_id:
            with self._req("POST", f"{API}/key-value-stores?name={STORE_NAME}") as r:
                self._store_id = json.load(r)["data"]["id"]   # returns existing store if any
        return self._store_id

    def load(self) -> "SeenStore":
        if self.token:
            try:
                with self._req("GET", f"{API}/key-value-stores/{self._store()}/records/{RECORD}") as r:
                    self.data = json.load(r)
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                self.data = {}            # first run
        elif self.local.exists():
            self.data = json.loads(self.local.read_text())
        return self

    def save(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=FORGET_AFTER_DAYS)).date().isoformat()
        self.data = {k: v for k, v in self.data.items() if v.get("last_seen", "9") >= cutoff}
        body = json.dumps(self.data).encode()
        if self.token:
            with self._req("PUT", f"{API}/key-value-stores/{self._store()}/records/{RECORD}", body):
                pass
        else:
            self.local.parent.mkdir(parents=True, exist_ok=True)
            self.local.write_bytes(body)

    # --- logic ------------------------------------------------------------------
    @property
    def is_empty(self) -> bool:
        return not self.data

    def status(self, l: Listing) -> tuple[str, float | None]:
        """('new'|'price_drop'|'seen', previous rent)."""
        prev = self.data.get(key(l))
        if prev is None:
            return "new", None
        if l.rent < prev["rent"]:
            return "price_drop", prev["rent"]
        return "seen", prev["rent"]

    def remember(self, listings: list[Listing]) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        for l in listings:
            k = key(l)
            entry = self.data.get(k, {"first_seen": today})
            entry.update(rent=l.rent, last_seen=today)
            self.data[k] = entry
