"""Command line entry point.

    python -m shortlister refresh
    python -m shortlister price "Loft @ Nathan" --rent 3200 --sqft 550 --study
    python -m shortlister lookup "nathan"
    python -m shortlister collect --live                      # PropertyGuru (default)
    python -m shortlister collect --live --source all         # + 99.co (pricier)
    python -m shortlister collect --file pg.json 99co.json    # from Apify exports
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .collect import load_file, normalise as normalise_rows, run_live
from .env import load_env
from .geo import Geocoder, place
from .report import markdown
from .models import Listing
from .pricing import DataGovSource, evaluate
from .pricing.matching import normalise
from .shortlist import build, score

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "listings"
def _save_raw(rows: list[dict]) -> None:
    """Keep each live run (without agent personal data) for later comparisons."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    clean = [{k: v for k, v in r.items() if k not in ("agent", "agency")} for r in rows]
    path = RAW_DIR / f"{datetime.now():%Y-%m-%d_%H%M}.json"
    path.write_text(json.dumps(clean, indent=1))


def _only_unseen(sl, seen):
    """Keep only listings never alerted before, or now cheaper than before."""
    from .shortlist import Shortlist

    def fresh(vs):
        out = []
        for v in vs:
            status, prev = seen.status(v.listing)
            if status == "seen":
                continue
            if status == "price_drop":
                v.flags.insert(0, f"⬇️ price reduced from S${prev:,.0f}")
            out.append(v)
        return out
    return Shortlist(kept=fresh(sl.kept), unverified=fresh(sl.unverified),
                     skipped=sl.skipped, duplicates_removed=sl.duplicates_removed)


def _add_details(sl, listings, source):
    """Open the full PropertyGuru page of shortlisted units for the move-in date."""
    from .collect import propertyguru as pg
    from .collect.apify import run_actor
    cands = [v.listing for v in sl.kept + sl.unverified if v.listing.source == "PropertyGuru"]
    urls = [l.url for l in cands if l.url][: config.PG_DETAIL_MAX]
    if not urls:
        return sl, listings
    try:
        rows = run_actor(config.PG_ACTOR, pg.detail_input(urls))
    except Exception as e:      # details are a bonus: never lose the shortlist over them
        print(f"warning: could not fetch listing details ({e})")
        return sl, listings
    listings = pg.apply_details(listings, rows)
    from .geo import Geocoder, add_mrt_walk
    listings = add_mrt_walk(listings, Geocoder())
    by_id = {l.listing_id: l for l in listings}
    from dataclasses import replace
    for v in sl.kept + sl.unverified:      # refresh cards in place, keep the filtering
        if v.listing.listing_id in by_id:
            v.listing = by_id[v.listing.listing_id]
    return sl, listings


def _print_card(i: int, v) -> None:
    l = v.listing
    layout = "studio" if l.bedrooms == 0 else f"{l.bedrooms}BR" if l.bedrooms else "?BR"
    if l.has_study:
        layout += " + study"
    market = (f"{abs(v.vs_median_pct):.1f}% {'below' if v.vs_median_pct < 0 else 'above'} market"
              if v.vs_median_pct is not None else "no market data")
    built = f", built {l.completed_year}" if l.completed_year else ""
    print(f"\n{i}. {l.project} (D{l.district}{built}, {l.source})  score {score(v)}")
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

    co = sub.add_parser("collect", help="collect listings and print the ranked shortlist")
    src = co.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", nargs="+", help="JSON export(s) of Apify runs (any source)")
    src.add_argument("--live", action="store_true", help="run the Apify scrapers now (costs money)")
    co.add_argument("--source", choices=["propertyguru", "99co", "all"], default="propertyguru")
    co.add_argument("--new-only", action="store_true",
                    help="only alert on listings not seen before (or cheaper than before); "
                         "the memory is kept in your Apify account")
    co.add_argument("--no-geo", action="store_true", help="skip OneMap lookups (offline)")
    co.add_argument("--show-skipped", action="store_true")
    co.add_argument("--report", help="also write a Markdown report to this file (appends)")
    co.add_argument("--telegram", action="store_true",
                    help="send the shortlist to Telegram (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")

    args = p.parse_args(argv)
    load_env()
    source = DataGovSource()

    if args.cmd == "collect":
        if args.live:
            rows = []
            sources = ["propertyguru", "99co"] if args.source == "all" else [args.source]
            for s in sources:
                rows += run_live(s)
            _save_raw(rows)
        else:
            rows = [r for f in args.file for r in load_file(f)]
        listings, dropped, streets = normalise_rows(rows)
        if not args.no_geo:
            listings, outside = place(listings, Geocoder(), streets)
            dropped += outside
        sl = build(listings, source)
        seen, first_run = None, False
        if args.new_only:
            from .state import SeenStore
            seen = SeenStore().load()
            first_run = seen.is_empty
            sl = _only_unseen(sl, seen)
        if args.live:
            sl, listings = _add_details(sl, listings, source)
        if args.report:
            with open(args.report, "a") as fh:
                fh.write(markdown(sl, len(rows), len(dropped), bool(args.live and args.new_only)))
        if args.telegram:
            from .notify import messages, send
            n = send(messages(sl, bool(args.new_only), first_run=first_run))
            print(f"Sent {n} Telegram message(s).")
        if seen is not None:
            # only after a successful send: if Telegram fails, the run errors
            # out above and these listings are alerted again next time
            seen.remember(listings)
            seen.save()
        print(f"{len(rows)} listings collected | {len(dropped)} removed (rooms, HDB/walk-ups, outside area) | "
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
