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


def test_mrt_walk_size_and_card(tmp_path):
    """Real OneMap coordinates: Okio and Boon Keng MRT (checked 2026-10-15)."""
    from shortlister.collect.propertyguru import clean_mrt
    from shortlister.geo import Geocoder, add_mrt_walk
    assert clean_mrt("NE9 Boon Keng MRT Station") == "Boon Keng MRT"
    assert clean_mrt("CR9 Serangoon North MRT Station") == "Serangoon North MRT"
    station = {"results": [{"SEARCHVAL": "BOON KENG MRT STATION",
                            "LATITUDE": "1.319939576532913", "LONGITUDE": "103.8620526984453"}]}
    geo = Geocoder(cache_path=tmp_path / "g.json", fetch=lambda q: station)
    okio = Listing("Okio", 3400, 592, bedrooms=2, source="PropertyGuru", url="u", listing_id="1",
                   lat=1.322133428227486, lng=103.8531996618712, mrt_name="Boon Keng MRT",
                   area="Balestier / Toa Payoh")
    okio, = add_mrt_walk([okio], geo)
    assert 12 <= okio.mrt_walk_min <= 18           # ~1 km away
    noMrt = Listing("Vista Residences", 3450, 635, bedrooms=1, source="PropertyGuru", url="v",
                    listing_id="2", area="Balestier / Toa Payoh")
    text = "\n".join(messages(_sl(tmp_path, [okio, noMrt]), new_only=True))
    assert "🚇 Boon Keng MRT · ~" in text and "592 sqft (55 sqm)" in text
    assert text.count("📍 Balestier / Toa Payoh") == 2      # shown with and without MRT
    assert "📍 Balestier / Toa Payoh" in text and "(D12)" not in text


def test_card_layout_v2(tmp_path):
    from shortlister.notify import UNVERIFIED_MAX
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"fetched_at": time.time(), "records": [
        {"qtr": "2026-Q2", "project_name": "OKIO", "postal_district": "12", "25th_percentile": "5.9",
         "median": "6.61", "75th_percentile": "7.0", "rental_contracts": "13"}]}))
    okio = Listing("Okio", 3400, 592, bedrooms=2, district=12, source="PropertyGuru", listing_id="1",
                   url="https://pg/okio", lat=1.32, lng=103.85, details_fetched=True,
                   highlights="Central Singapore 2 bedroom for rent", area="Balestier / Toa Payoh")
    many = [Listing(f"Boutique {i}", 3200, 600, bedrooms=1, source="PropertyGuru", url=f"u{i}",
                    listing_id=str(100 + i), lat=1.3, lng=103.8) for i in range(15)]
    sl = build([okio] + many, DataGovSource(cache_path=cache))
    text = "\n".join(messages(sl, new_only=True))
    assert '<a href="https://pg/okio"><b>1. Okio</b></a>' in text
    assert "💰 S$3,400/mo · 2BR" in text and "📐 592 sqft (55 sqm) · S$5.74 psf" in text
    assert "🟢 13% below market (small sample)" in text
    assert "<i>\"Central Singapore 2 bedroom for rent\"</i>" in text
    assert "benchmark based on" not in text and "Open on" not in text
    assert f"…and {15 - UNVERIFIED_MAX} more" in text
    assert text.count("⚪ no market data") == UNVERIFIED_MAX
