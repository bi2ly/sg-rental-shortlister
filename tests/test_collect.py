"""Collector tests on real rows from a 2026-10-14 Apify export (agent data removed)."""

import json
import time
from pathlib import Path

import pytest

from shortlister.collect import load_file, normalise, search_input
from shortlister.pricing import DataGovSource
from shortlister.shortlist import build, dedupe

FIXTURE = Path(__file__).parent / "fixtures" / "apify_99co_sample.json"


@pytest.fixture
def rows():
    return load_file(FIXTURE)


@pytest.fixture
def source(tmp_path):
    # Synthetic benchmark for Okio only; other projects have no market data.
    rec = {"qtr": "2026-Q2", "project_name": "OKIO", "postal_district": "12",
           "25th_percentile": "5.3", "median": "5.9", "75th_percentile": "6.4",
           "rental_contracts": "20"}
    cache = tmp_path / "rentals.json"
    cache.write_text(json.dumps({"fetched_at": time.time(), "records": [rec]}))
    return DataGovSource(cache_path=cache)


def test_room_rentals_removed(rows):
    listings, dropped, _ = normalise(rows)
    dropped_names = {name for name, _ in dropped}
    # labelled "room" by 99.co, and Sunglade which is only given away by its text
    assert {"Villa Azura", "Studios @ Marne", "Sunglade", "Pandan Valley"} <= dropped_names
    assert "Okio" in {l.project for l in listings}


def test_fields_mapped(rows):
    listings, _, _ = normalise(rows)
    okio = next(l for l in listings if l.listing_id == "jSBrpCsTCpS5CLVVYQFKUH")
    assert (okio.rent, okio.sqft, okio.bedrooms, okio.completed_year) == (3400, 592, 2, 2015)
    assert okio.district == 12 and okio.lat and okio.lng
    assert okio.url == "https://www.99.co/property/jSBrpCsTCpS5CLVVYQFKUH"
    assert okio.posted_at.startswith("2026-10-14")


def test_study_and_one_bedder_detection(rows):
    listings, _, _ = normalise(rows)
    by = {l.project: l for l in listings}
    assert by["Riviera 38"].has_study
    assert by["Newest"].bedrooms == 1      # tagged 0 but text says "1 bedder"


def test_duplicates_keep_cheapest(rows):
    listings, _, _ = normalise(rows)
    unique, removed = dedupe(listings)
    okio = [l for l in unique if l.project == "Okio"]
    assert removed == 1 and len(okio) == 1 and okio[0].rent == 3300


def test_shortlist_buckets(rows, source):
    listings, _, _ = normalise(rows)
    sl = build(listings, source)
    kept = {v.listing.project for v in sl.kept}
    unverified = {v.listing.project for v in sl.unverified}
    assert "Okio" in kept               # 3300/592 = 5.57 psf < median 5.9
    assert "Suites 28" in kept          # within 3000 target
    assert "Riviera 38" in unverified   # 3200, no market data -> needs price check


def test_search_input_matches_spec():
    inp = search_input()
    assert inp["listingType"] == "rent" and inp["propertyType"] == "condo"
    assert inp["maxPrice"] == 3500 and inp["minFloorArea"] == 500
    assert inp["enrichListings"] is False
