"""PropertyGuru + area-filter tests.

Fixture rows come from a real run on 2026-10-15 (agent data removed), except the
last "Common room" row, which is synthetic, built on a real room listing URL.
The OneMap response format is the real one (checked live for OKIO).
"""

import json
import time
from pathlib import Path

import pytest

from shortlister.collect import load_file, normalise, propertyguru_input
from shortlister.geo import Geocoder, in_area, parse_onemap, place
from shortlister.pricing import DataGovSource
from shortlister.shortlist import build

HERE = Path(__file__).parent / "fixtures"
ONEMAP_OKIO = {"found": 1, "results": [{"SEARCHVAL": "OKIO", "BUILDING": "OKIO",
               "LATITUDE": "1.322133428227486", "LONGITUDE": "103.8531996618712"}]}


@pytest.fixture
def pg_rows():
    return load_file(HERE / "apify_propertyguru_sample.json")


def test_pg_filters_walkups_rooms_and_bad_rows(pg_rows):
    listings, dropped, _ = normalise(pg_rows)
    reasons = dict(dropped)
    assert "WALK" in reasons["541A Balestier Road"]
    assert "missing" in reasons["Ritz Mansions"]
    assert "room" in reasons["Common room available for rent in Toa Payoh area"]
    assert {l.project for l in listings} >= {"Okio", "Vista Residences", "City Suites"}


def test_pg_fields_and_studio_title(pg_rows):
    listings, _, streets = normalise(pg_rows)
    okio = next(l for l in listings if l.listing_id == "24956896")
    assert (okio.rent, okio.sqft, okio.bedrooms, okio.district) == (3400, 592, 2, 12)
    assert okio.url == "https://www.propertyguru.com.sg/listing/for-rent-okio-24956896"
    assert okio.source == "PropertyGuru"
    assert streets["24956896"] == "262 BALESTIER ROAD"
    studio = next(l for l in listings if "Studio" in l.project)
    assert studio.bedrooms == 0


def test_cross_site_duplicate_merged(pg_rows):
    """The same Okio unit (592 sqft) is on 99.co and PropertyGuru."""
    nn_rows = load_file(HERE / "apify_99co_sample.json")
    listings, _, _ = normalise(pg_rows + nn_rows)
    cache = Path(__file__).parent / "_tmp_rentals.json"
    cache.write_text(json.dumps({"fetched_at": time.time(), "records": []}))
    try:
        sl = build(listings, DataGovSource(cache_path=cache))
    finally:
        cache.unlink()
    all_v = sl.kept + sl.unverified + sl.skipped
    okio_592 = [v for v in all_v if v.listing.project == "Okio" and round(v.listing.sqft) == 592]
    assert len(okio_592) == 1


def test_onemap_parsing_and_area():
    lat, lng = parse_onemap(ONEMAP_OKIO, "Okio")
    assert in_area(lat, lng)
    assert not in_area(1.4400, 103.7860)    # Woodlands: outside the map
    assert not in_area(1.3500, 103.9500)    # Tampines: outside the map
    assert parse_onemap({"results": []}, "x") is None


def test_place_geocodes_and_caches(pg_rows, tmp_path):
    calls = []

    def fake_fetch(query):
        calls.append(query)
        return ONEMAP_OKIO if "OKIO" in query.upper() else {"results": []}

    listings, _, streets = normalise(pg_rows)
    geo = Geocoder(cache_path=tmp_path / "geo.json", fetch=fake_fetch)
    kept, dropped = place(listings, geo, streets)
    okio = [l for l in kept if l.project == "Okio"]
    assert okio and all(l.lat for l in okio)
    assert sum(q.upper() == "OKIO" for q in calls) == 1     # two Okio listings, one lookup
    unknown = next(l for l in kept if l.project == "Vista Residences")
    assert unknown.lat is None                               # kept, not silently dropped


def test_pg_input():
    inp = propertyguru_input(since="2026-10-15T00:00:00Z")
    assert inp["searchType"] == "rent" and inp["maxPrice"] == 3500
    assert "Tanglin" in inp["keywords"] and "Katong" in inp["keywords"]
    assert inp["scrapeDetails"] is False and inp["since"].startswith("2026-10-15")


def test_price_difference_noted_only_when_prices_differ():
    from shortlister.models import Listing
    from shortlister.shortlist import price_differences
    pg = Listing("Okio", 3400, 592, source="PropertyGuru", url="pg")
    nn_same = Listing("Okio", 3400, 592, source="99.co", url="nn")
    nn_dear = Listing("Okio", 3600, 590, source="99.co", url="nn2")
    assert price_differences(pg, [pg, nn_same]) == []
    notes = price_differences(pg, [pg, nn_same, nn_dear])
    assert len(notes) == 1 and "S$3,600 on 99.co (S$+200)" in notes[0] and "nn2" in notes[0]
