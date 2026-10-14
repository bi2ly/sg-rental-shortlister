"""Where market rent benchmarks come from.

Today: data.gov.sg "Rentals of Non-Landed Residential Buildings, Quarterly"
(URA statistics, no key needed). Values are S$ per sqft per month, per project,
for major projects with at least 10 contracts in a quarter.

Later: a URA Data Service source (contract-level, needs the access key) can be
added by implementing the same BenchmarkSource interface.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Protocol

from ..config import QUARTERS_TO_USE
from ..models import Benchmark

DATAGOV_DATASET_ID = "d_149ac00a2734bb0a03867bbe2ec0e7b0"
DATAGOV_URL = "https://data.gov.sg/api/action/datastore_search"
DEFAULT_CACHE = Path(__file__).resolve().parents[2] / "data" / "datagov_rentals.json"
CACHE_MAX_AGE_DAYS = 7


class BenchmarkSource(Protocol):
    name: str

    def benchmarks(self) -> dict[str, Benchmark]:
        """Return benchmarks keyed by official (uppercase) project name."""
        ...


class DataGovSource:
    name = "data.gov.sg"

    def __init__(self, cache_path: Path = DEFAULT_CACHE, api_key: str | None = None):
        self.cache_path = Path(cache_path)
        # Optional: a free data.gov.sg key raises rate limits. Not required.
        self.api_key = api_key or os.environ.get("DATAGOV_API_KEY")
        self._benchmarks: dict[str, Benchmark] | None = None

    # ---- public -------------------------------------------------------------

    def refresh(self) -> int:
        """Download the full dataset and cache it. Returns the record count."""
        records = list(self._download())
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"fetched_at": time.time(), "records": records}
        self.cache_path.write_text(json.dumps(payload))
        self._benchmarks = None
        return len(records)

    def benchmarks(self) -> dict[str, Benchmark]:
        if self._benchmarks is None:
            if not self.cache_path.exists() or self._cache_age_days() > CACHE_MAX_AGE_DAYS:
                self.refresh()
            records = json.loads(self.cache_path.read_text())["records"]
            self._benchmarks = build_benchmarks(records, source=self.name)
        return self._benchmarks

    # ---- internals ----------------------------------------------------------

    def _cache_age_days(self) -> float:
        fetched = json.loads(self.cache_path.read_text()).get("fetched_at", 0)
        return (time.time() - fetched) / 86400

    def _download(self, page_size: int = 1000) -> Iterable[dict]:
        offset, total = 0, None
        while total is None or offset < total:
            query = urllib.parse.urlencode(
                {"resource_id": DATAGOV_DATASET_ID, "limit": page_size, "offset": offset}
            )
            req = urllib.request.Request(f"{DATAGOV_URL}?{query}")
            if self.api_key:
                req.add_header("x-api-key", self.api_key)
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.load(resp)["result"]
            total = result["total"]
            batch = result["records"]
            if not batch:
                break
            yield from batch
            offset += len(batch)


def build_benchmarks(records: Iterable[dict], source: str,
                     quarters_to_use: int = QUARTERS_TO_USE) -> dict[str, Benchmark]:
    """Combine raw quarterly rows into one benchmark per project.

    Uses the most recent `quarters_to_use` quarters available for each project,
    weighting each quarter's percentiles by its number of contracts.
    """
    by_project: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        try:
            row = {
                "qtr": r["qtr"],
                "district": str(r.get("postal_district", "")),
                "p25": float(r["25th_percentile"]),
                "median": float(r["median"]),
                "p75": float(r["75th_percentile"]),
                "contracts": int(float(r["rental_contracts"])),
            }
        except (KeyError, TypeError, ValueError):
            continue  # skip malformed rows ("na", blanks)
        if row["contracts"] <= 0:
            continue
        by_project[r["project_name"].strip().upper()].append(row)

    out: dict[str, Benchmark] = {}
    for project, rows in by_project.items():
        rows.sort(key=lambda x: x["qtr"], reverse=True)
        recent = rows[:quarters_to_use]
        n = sum(x["contracts"] for x in recent)

        def wavg(key: str) -> float:
            return round(sum(x[key] * x["contracts"] for x in recent) / n, 2)

        out[project] = Benchmark(
            project=project,
            district=recent[0]["district"],
            p25=wavg("p25"),
            median=wavg("median"),
            p75=wavg("p75"),
            contracts=n,
            quarters=tuple(sorted(x["qtr"] for x in recent)),
            source=source,
        )
    return out
