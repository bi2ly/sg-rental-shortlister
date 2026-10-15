"""Plain data objects shared across the project."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Listing:
    """A rental listing to evaluate. Only project, rent and size are required."""

    project: str
    rent: float                  # S$/month
    sqft: float
    bedrooms: int | None = None  # 0 = studio, None = unknown
    has_study: bool = False
    url: str | None = None
    # Filled in when the listing comes from a portal
    listing_id: str | None = None
    source: str | None = None            # e.g. "99.co"
    title: str | None = None
    highlights: str | None = None
    district: int | None = None
    lat: float | None = None
    lng: float | None = None
    completed_year: int | None = None
    photo_count: int = 0
    posted_at: str | None = None         # ISO-8601 UTC
    available_from: str | None = None    # YYYY-MM-DD (Singapore date), from the full listing page
    details_fetched: bool = False        # full listing page was opened
    area: str | None = None              # e.g. "Balestier / Toa Payoh"
    mrt_name: str | None = None          # e.g. "Boon Keng MRT"
    mrt_walk_min: int | None = None      # estimated walking minutes to mrt_name

    @property
    def psf(self) -> float:
        return self.rent / self.sqft


@dataclass(frozen=True)
class Benchmark:
    """Market rents for one condo project, in S$ per sqft per month."""

    project: str
    district: str
    p25: float
    median: float
    p75: float
    contracts: int
    quarters: tuple[str, ...]    # e.g. ("2026-Q1", "2026-Q2")
    source: str                  # "data.gov.sg" now, "URA" later


@dataclass
class Verdict:
    listing: Listing
    benchmark: Benchmark | None
    matched_name: str | None = None
    band: str = "no data"            # see engine.BANDS
    vs_median_pct: float | None = None   # negative = cheaper than median
    good_deal: bool = False
    keep: bool = False
    decision: str = ""                   # one-line keep/skip reason
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
