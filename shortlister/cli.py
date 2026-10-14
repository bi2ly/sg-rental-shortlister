"""Command line entry point.

    python -m shortlister refresh
    python -m shortlister price "Loft @ Nathan" --rent 3200 --sqft 550 --study
    python -m shortlister lookup "nathan"
"""

from __future__ import annotations

import argparse
import sys

from .models import Listing
from .pricing import DataGovSource, evaluate
from .pricing.matching import normalise


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

    args = p.parse_args(argv)
    source = DataGovSource()

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
