"""Listings in, ranked shortlist out: dedupe -> price check -> score."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .models import Listing, Verdict
from .pricing import evaluate
from .pricing.matching import normalise as norm_name
from .pricing.sources import BenchmarkSource


@dataclass
class Shortlist:
    kept: list[Verdict] = field(default_factory=list)        # ranked, best first
    unverified: list[Verdict] = field(default_factory=list)  # in stretch budget, no market data
    negotiable: list[Verdict] = field(default_factory=list)  # over budget, worth negotiating
    skipped: list[Verdict] = field(default_factory=list)
    duplicates_removed: int = 0


def _key(l: Listing) -> tuple:
    return (norm_name(l.project), round(l.sqft / 5))


def dedupe(listings: list[Listing]) -> tuple[list[Listing], int]:
    """Same project + same size (±5 sqft) is treated as one unit posted by
    several agents or on several sites; the cheapest version is kept."""
    best: dict[tuple, Listing] = {}
    for l in listings:
        key = _key(l)
        if key not in best or l.rent < best[key].rent:
            best[key] = l
    return list(best.values()), len(listings) - len(best)


def price_differences(kept: Listing, listings: list[Listing]) -> list[str]:
    """Other postings of the same unit at a different price (same price: silent)."""
    notes = []
    for other in listings:
        if other is kept or _key(other) != _key(kept) or other.rent == kept.rent:
            continue
        notes.append(f"same unit also listed at S${other.rent:,.0f} on {other.source} "
                     f"(S${other.rent - kept.rent:+,.0f}): {other.url}")
    return notes


def score(v: Verdict) -> float:
    """Higher is better. Simple and explainable on purpose."""
    l, s = v.listing, 0.0
    if v.vs_median_pct is not None:
        s += -v.vs_median_pct            # 1 point per % below median
    else:
        s -= 5                           # unknown price: small penalty
    if l.has_study:
        s += 5
    # Build year is not scored (decided 2026-10-15: buildings are generally well
    # maintained, and PropertyGuru card data has no build year).
    if l.photo_count == 0:      # PropertyGuru cards only expose a thumbnail
        s -= 5
    if any("suspiciously cheap" in f for f in v.flags):
        s -= 10
    return round(s, 1)


def build(listings: list[Listing], source: BenchmarkSource) -> Shortlist:
    unique, removed = dedupe(listings)
    result = Shortlist(duplicates_removed=removed)
    for l in unique:
        v = evaluate(l, source)
        if l.photo_count == 0:
            v.flags.append("no photos")
        if l.lat is None:
            v.flags.append("location not found: check the area yourself")
        v.flags.extend(price_differences(l, listings))
        if l.completed_year and l.completed_year < date.today().year - 25:
            v.flags.append(f"older building (completed {l.completed_year})")
        if v.keep:
            result.kept.append(v)
        elif v.negotiable:
            result.negotiable.append(v)
        elif v.benchmark is None and v.decision.startswith("not kept"):
            result.unverified.append(v)   # can't confirm a good deal, but don't hide it
        else:
            result.skipped.append(v)
    result.kept.sort(key=score, reverse=True)
    result.unverified.sort(key=score, reverse=True)
    # smallest discount needed first, then the better deal
    result.negotiable.sort(key=lambda v: (v.listing.rent, v.vs_median_pct))
    return result
