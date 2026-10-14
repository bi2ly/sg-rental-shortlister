"""Turn a listing plus market benchmark into a verdict, following SPEC.md."""

from __future__ import annotations

from .. import config
from ..models import Benchmark, Listing, Verdict
from .matching import match_project
from .sources import BenchmarkSource

BANDS = (
    "well below market",   # under the project's 25th percentile
    "below median",        # 25th percentile .. median
    "above median",        # median .. 75th percentile
    "overpriced",          # over the 75th percentile
    "no data",             # project not covered by the benchmark source
)


def classify(psf: float, b: Benchmark) -> str:
    if psf < b.p25:
        return "well below market"
    if psf <= b.median:
        return "below median"
    if psf <= b.p75:
        return "above median"
    return "overpriced"


def evaluate(listing: Listing, source: BenchmarkSource) -> Verdict:
    benchmarks = source.benchmarks()
    name, score = match_project(listing.project, list(benchmarks))
    bench = benchmarks.get(name) if name else None
    v = Verdict(listing=listing, benchmark=bench, matched_name=name)

    psf = listing.psf
    v.reasons.append(f"S${listing.rent:,.0f} for {listing.sqft:,.0f} sqft = S${psf:.2f} psf")

    # --- market comparison ---------------------------------------------------
    if bench:
        if score < 1.0:
            v.flags.append(f"project name matched approximately to '{name}' ({score:.0%})")
        v.band = classify(psf, bench)
        v.vs_median_pct = round((psf / bench.median - 1) * 100, 1)
        v.good_deal = psf < bench.median
        direction = "below" if v.vs_median_pct < 0 else "above"
        v.reasons.append(
            f"{abs(v.vs_median_pct):.1f}% {direction} project median "
            f"(S${bench.median:.2f} psf; range S${bench.p25:.2f}-{bench.p75:.2f}, "
            f"{bench.contracts} contracts, {'/'.join(bench.quarters)})"
        )
        if psf < bench.p25 * (1 - config.SUSPICIOUS_BELOW_P25):
            v.flags.append("suspiciously cheap vs. market: check it's real and still available")
        if bench.contracts < config.LOW_CONFIDENCE_CONTRACTS:
            v.flags.append(f"benchmark based on only {bench.contracts} contracts")
    else:
        v.flags.append("no market data for this project: review price manually")

    # --- budget & size rules from SPEC ----------------------------------------
    if listing.sqft < config.MIN_SQFT:
        v.reasons.append(f"rejected: under {config.MIN_SQFT} sqft")
    elif listing.rent > config.MAX_RENT:
        v.reasons.append(f"rejected: over S${config.MAX_RENT:,} max budget")
    elif listing.rent <= config.TARGET_RENT:
        v.keep = True
        v.reasons.append(f"within S${config.TARGET_RENT:,} target budget")
        if v.band == "overpriced":
            v.flags.append("in budget but above the project's usual range")
    elif v.good_deal:
        v.keep = True
        v.reasons.append(f"above S${config.TARGET_RENT:,} target but kept: priced below market")
    elif bench:
        v.reasons.append(f"rejected: above S${config.TARGET_RENT:,} target and not below market")
    else:
        v.reasons.append(f"not kept: above S${config.TARGET_RENT:,} target and good deal can't be confirmed")

    if listing.has_study:
        v.reasons.append("has a study (bonus)")
    return v
