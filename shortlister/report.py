"""Markdown report of a shortlist (GitHub job summary now, Telegram later)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config
from .shortlist import Shortlist, score

SGT = timezone(timedelta(hours=8))


def _layout(l) -> str:
    s = "studio" if l.bedrooms == 0 else f"{l.bedrooms}BR" if l.bedrooms else "?BR"
    return s + (" + study" if l.has_study else "")


def _market(v) -> str:
    if v.vs_median_pct is None:
        return "no market data"
    return f"{abs(v.vs_median_pct):.1f}% {'below' if v.vs_median_pct < 0 else 'above'} market"


def _rows(verdicts) -> list[str]:
    out = ["| # | Project | Rent | Size | S$ psf | Layout | vs market | Notes | Link |",
           "|---|---|---|---|---|---|---|---|---|"]
    for i, v in enumerate(verdicts, 1):
        l = v.listing
        notes = "<br>".join(f.replace("|", "/") for f in v.flags) or ""
        out.append(f"| {i} | **{l.project}** (D{l.district}) | S${l.rent:,.0f} | {l.sqft:,.0f} sqft "
                   f"| {l.psf:.2f} | {_layout(l)} | {_market(v)} | {notes} "
                   f"| [{l.source}]({l.url}) |")
    return out


def markdown(sl: Shortlist, collected: int, removed: int, new_only: bool) -> str:
    now = datetime.now(SGT).strftime("%a %d %b %Y, %H:%M SGT")
    scope = "new listings since the last run" if new_only else "all current listings"
    lines = [
        f"# Condo shortlist: {now}",
        "",
        f"Scope: {scope}. {collected} collected, {removed} removed (rooms, HDB/walk-ups, "
        f"outside area), {sl.duplicates_removed} duplicates merged.",
        "",
        f"## Shortlist ({len(sl.kept)})",
        "",
    ]
    lines += _rows(sl.kept) if sl.kept else ["Nothing new matches today."]
    if sl.unverified:
        lines += ["", f"## Needs a price check ({len(sl.unverified)})", "",
                  f"S${config.TARGET_RENT:,}-{config.MAX_RENT:,} but no market data for "
                  "the project yet, so a good deal can't be confirmed.", ""]
        lines += _rows(sl.unverified)
    return "\n".join(lines) + "\n"
