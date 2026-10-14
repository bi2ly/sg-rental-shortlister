"""Match a listing's project name to the official URA project name.

Listing portals write names loosely ("The Tembusu", "Loft@Nathan", "loft at nathan"),
while URA uses its own uppercase spelling. We normalise both, try an exact match,
then fall back to a strict fuzzy match.
"""

from __future__ import annotations

import difflib
import re

FUZZY_CUTOFF = 0.88


def normalise(name: str) -> str:
    s = name.upper()
    s = s.replace("@", " AT ").replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s.startswith("THE "):
        s = s[4:]
    return s


def match_project(name: str, official_names: list[str],
                  cutoff: float = FUZZY_CUTOFF) -> tuple[str | None, float]:
    """Return (official name, score). Score 1.0 means an exact normalised match."""
    target = normalise(name)
    index = {normalise(n): n for n in official_names}
    if target in index:
        return index[target], 1.0
    best = difflib.get_close_matches(target, list(index), n=1, cutoff=cutoff)
    if not best:
        return None, 0.0
    score = difflib.SequenceMatcher(None, target, best[0]).ratio()
    return index[best[0]], round(score, 2)
