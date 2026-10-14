"""Command line entry point.

    python -m shortlister refresh
    python -m shortlister price "Loft @ Nathan" --rent 3200 --sqft 550 --study
    python -m shortlister lookup "nathan"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import config
from .collect import load_file, normalise as normalise_rows, run_live
from .env import load_env
from .models import Listing
from .pricing import DataGovSource, evaluate
from .pricing.matching import normalise
from .shortlist import build, score

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "listings"


def _save_raw(rows: list[dict]) -> None:
    """Keep each live run (without agent personal data) for later comparisons."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    clean = [{k: v for k, v in r.items() if k != "agent"} for r in rows]
    path = RAW_DIR / f"{datetime.now():%Y-%m-%d_%H%M}.json"
    path.write_text(json.dumps(clean, indent=1))


def _print_card(i: int, v) -> None:
    l = v.listing
    layout = "studio" if l.bedrooms == 0 else f"{l.bedrooms}BR" if l.bedrooms else "?BR"
    if l.has_study:
        layout += " + study"
    market = (f"{abs(v.vs_median_pct):.1f}% {'below' if v.vs_median_pct < 0 else 'above'} market"
              if v.vs_median_pct is not None else "no market data")
    print(f"\n{i}. {l.project} (D{l.district}, built {l.completed_year or '?'})  score {score(v)}")
    print(f"   S${l.rent:,.0f} | {l.sqft:,.0f} sqft | S${l.psf:.2f} psf | {layout} | {market}")
    if l.highlights:
        print(f"   \"{l.highlights.strip()[:90]}\"")
    for f in v.flags:
        print(f"   ! {f}")
    print(f"   {l.url}")


def _print_verdict(v) -> None:
    status = "KEEP" if v.keep else "SKIP"
    print(f"\n[{status}] {v.listing.project}  ->  {v.band.upper()}")
    if v.matched_name and v.matched_name != v.listing.project.upper():
        print(f"  matched URA project: {v.matched_name}")
    for r in v.reasons:
        print(f"  - {r}")
    for f in v.flags:
        print(f"  ! {f}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="shortlister", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("refresh", help="download latest market rent data from data.gov.sg")

    pr = sub.add_parser("price", help="check a listing against market rents")
    pr.add_argument("project")
    pr.add_argument("--rent", type=float, required=True, help="monthly rent in S$")
    pr.add_argument("--sqft", type=float, required=True)
    pr.add_argument("--study", action="store_true", help="unit has a study")

    lk = sub.add_parser("lookup", help="search project names in the market data")
    lk.add_argument("text")

    co = sub.add_parser("collect", help="collect 99.co listings and print the ranked shortlist")
    src = co.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="JSON export of an Apify run")
    src.add_argument("--live", action="store_true", help="run the Apify scraper now (costs money)")
    co.add_argument("--max-results", type=int, default=config.MAX_RESULTS_PER_RUN)
    co.add_argument("--show-skipped", action="store_true")

    args = p.parse_args(argv)
    load_env()
    source = DataGovSource()

    if args.cmd == "collect":
        rows = run_live(max_results=args.max_results) if args.live else load_file(args.file)
        if args.live:
            _save_raw(rows)
        listings, dropped = normalise_rows(rows)
        sl = build(listings, source)
        print(f"{len(rows)} listings collected | {len(dropped)} room/invalid removed | "
              f"{sl.duplicates_removed} duplicates removed | "
              f"{len(sl.kept)} shortlisted | {len(sl.unverified)} need a price check | "
              f"{len(sl.skipped)} skipped")
        print("\n=== SHORTLIST (best first) ===")
        for i, v in enumerate(sl.kept, 1):
            _print_card(i, v)
        if sl.unverified:
            print(f"\n=== NEEDS PRICE CHECK (above S${config.TARGET_RENT:,}, no market data) ===")
            for i, v in enumerate(sl.unverified, 1):
                _print_card(i, v)
        if args.show_skipped:
            print("\n=== SKIPPED ===")
            for v in sl.skipped:
                print(f"- {v.listing.project}: S${v.listing.rent:,.0f}, {v.listing.sqft:,.0f} sqft "
                      f"-> {v.decision}")
            for project, reason in dropped:
                print(f"- {project}: {reason}")
        return 0

    if args.cmd == "refresh":
        n = source.refresh()
        print(f"Saved {n} rows ({len(source.benchmarks())} projects) to {source.cache_path}")
        return 0

    if args.cmd == "price":
        listing = Listing(args.project, args.rent, args.sqft, has_study=args.study)
        _print_verdict(evaluate(listing, source))
        return 0

    if args.cmd == "lookup":
        needle = normalise(args.text)
        hits = [b for name, b in sorted(source.benchmarks().items()) if needle in normalise(name)]
        for b in hits[:30]:
            print(f"{b.project:<40} D{b.district:<3} median S${b.median:.2f} psf "
                  f"({b.p25:.2f}-{b.p75:.2f}), {b.contracts} contracts")
        if not hits:
            print("No project found. Smaller condos (<100 units) aren't in this dataset.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
