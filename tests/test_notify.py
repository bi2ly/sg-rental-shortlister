import json
import time
from pathlib import Path

from shortlister.collect import load_file, normalise
from shortlister.models import Listing
from shortlister.notify import LIMIT, messages, send
from shortlister.pricing import DataGovSource
from shortlister.shortlist import Shortlist, build

FIX = Path(__file__).parent / "fixtures" / "apify_propertyguru_sample.json"


def _sl(tmp_path, listings):
    cache = tmp_path / "r.json"
    cache.write_text(json.dumps({"fetched_at": time.time(), "records": []}))
    return build(listings, DataGovSource(cache_path=cache))


def test_cards_html_and_links(tmp_path):
    listings, _, _ = normalise(load_file(FIX))
    msgs = messages(_sl(tmp_path, listings), new_only=True)
    text = "\n".join(msgs)
    assert "<b>Condo shortlist</b>" in text and "new since last run" in text
    assert '<a href="https://www.propertyguru.com.sg/listing/' in text
    assert "<script" not in text


def test_escaping_and_split(tmp_path):
    many = [Listing(f"Tower <{i}> & Co", 2900, 600 + i, bedrooms=1, url=f"https://x/{i}",
                    source="PropertyGuru", district=12) for i in range(80)]
    msgs = messages(_sl(tmp_path, many), new_only=False)
    assert len(msgs) > 1 and all(len(m) <= LIMIT for m in msgs)
    assert "Tower &lt;0&gt; &amp; Co" in msgs[0]


def test_nothing_new():
    assert "Nothing new" in messages(Shortlist(), new_only=True)[0]


def test_send_skips_without_config(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert send(["hi"]) == 0


def test_availability_from_full_page(tmp_path):
    """Real full-page rows from 2026-10-15 (Okio 24956896, Florence 25343630)."""
    from shortlister.collect.propertyguru import apply_details, sg_date
    from shortlister.report import available
    assert sg_date("2026-11-04T16:00:00.000Z") == "2026-11-05"   # midnight SGT
    rows = [{"listingId": "24956896", "availableAt": "2026-11-04T16:00:00.000Z",
             "headline": "Central Singapore 2 bedroom for rent"},
            {"listingId": "24591488", "availableAt": "2026-12-04T16:00:00.000Z",
             "headline": "1bedroom with study for rent!"},
            {"listingId": "25343630", "headline": "Beautiful penthouse unit."}]
    base = dict(sqft=600, bedrooms=1, source="PropertyGuru", district=12, url="u")
    ls = [Listing("Okio", 3400, listing_id="24956896", **base),
          Listing("Affinity At Serangoon", 3200, listing_id="24591488", **base),
          Listing("The Florence Residences", 2999, listing_id="25343630", **base),
          Listing("Not Opened", 2900, listing_id="1", **base)]
    okio, aff, flo, other = apply_details(ls, rows)
    assert available(okio) in ("5 Nov", "now") and aff.has_study
    assert available(flo) == "not stated" and available(other) is None
    text = "\n".join(messages(_sl(tmp_path, [okio, aff, flo, other]), new_only=True))
    assert "📅 Available:" in text and text.count("📅") == 3
