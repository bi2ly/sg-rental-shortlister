import json
import time

from shortlister.cli import _only_unseen
from shortlister.models import Listing
from shortlister.pricing import DataGovSource
from shortlister.shortlist import build
from shortlister.state import SeenStore


def _l(name, rent, lid):
    return Listing(name, rent, 600, bedrooms=1, source="PropertyGuru", listing_id=lid, url=lid,
                   lat=1.3, lng=103.8)


def test_seen_store_flow(tmp_path):
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"fetched_at": time.time(), "records": []}))
    src = DataGovSource(cache_path=cache)
    store = SeenStore(token="", local=tmp_path / "seen.json").load()
    assert store.is_empty

    day1 = [_l("Okio", 2900, "1"), _l("Vetro", 3000, "2")]
    sl = _only_unseen(build(day1, src), store)
    assert {v.listing.project for v in sl.kept} == {"Okio", "Vetro"}   # first run: all
    store.remember(day1)
    store.save()

    store = SeenStore(token="", local=tmp_path / "seen.json").load()   # next run
    day2 = [_l("Okio", 2900, "1"), _l("Vetro", 2800, "2"), _l("New One", 2950, "3")]
    sl = _only_unseen(build(day2, src), store)
    names = {v.listing.project: v for v in sl.kept}
    assert set(names) == {"Vetro", "New One"}                       # Okio already sent
    assert names["Vetro"].flags[0] == "⬇️ price reduced from S$3,000"


def test_not_remembered_if_never_saved(tmp_path):
    """If sending fails the run stops before save(): listings come again next time."""
    store = SeenStore(token="", local=tmp_path / "seen.json").load()
    store.remember([_l("Okio", 2900, "1")])          # no save()
    again = SeenStore(token="", local=tmp_path / "seen.json").load()
    assert again.status(_l("Okio", 2900, "1"))[0] == "new"
