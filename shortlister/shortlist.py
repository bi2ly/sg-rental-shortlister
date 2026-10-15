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
    skipped: list[Verdict] = field(default_factory=list)
    duplicates_removed: int = 0


def dedupe(listings: list[Listing]) -> tuple[list[Listing], int]:
    """Same project + same size (±5 sqft) is treated as one unit posted by
    several agents; the cheapest version is kept."""
    best: dict[tuple, Listing] = {}
    for l in listings:
        key = (norm_name(l.project), round(l.sqft / 5))
        if key not in best or l.rent < best[key].rent:
            best[key] = l
    return list(best.values()), len(listings) - len(best)


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
        if l.completed_year and l.completed_year < date.today().year - 25:
            v.flags.append(f"older building (completed {l.completed_year})")
        if v.keep:
            result.kept.append(v)
        elif v.benchmark is None and v.decision.startswith("not kept"):
            result.unverified.append(v)   # can't confirm a good deal, but don't hide it
        else:
            result.skipped.append(v)
    result.kept.sort(key=score, reverse=True)
    result.unverified.sort(key=score, reverse=True)
    return result
