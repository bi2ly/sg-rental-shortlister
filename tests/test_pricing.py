"""Tests use rows in the exact format data.gov.sg returns (strings for numbers)."""

import json

import pytest

from shortlister.models import Listing
from shortlister.pricing import DataGovSource, evaluate
from shortlister.pricing.matching import match_project, normalise
from shortlister.pricing.sources import build_benchmarks

ROWS = [
    # Real 2026-Q2 rows from data.gov.sg
    {"qtr": "2026-Q2", "project_name": "18 WOODSVILLE", "postal_district": "13",
     "25th_percentile": "4.9", "median": "5.63", "75th_percentile": "6.31", "rental_contracts": "10"},
    {"qtr": "2026-Q2", "project_name": "26 NEWTON", "postal_district": "11",
     "25th_percentile": "6.16", "median": "6.52", "75th_percentile": "6.92", "rental_contracts": "13"},
    # Synthetic project with two quarters, to test combining
    {"qtr": "2026-Q1", "project_name": "LOFT @ NATHAN", "postal_district": "10",
     "25th_percentile": "5.5", "median": "6.0", "75th_percentile": "6.5", "rental_contracts": "10"},
    {"qtr": "2026-Q2", "project_name": "LOFT @ NATHAN", "postal_district": "10",
     "25th_percentile": "5.8", "median": "6.3", "75th_percentile": "6.8", "rental_contracts": "30"},
    # Malformed row must be ignored
    {"qtr": "2026-Q2", "project_name": "BROKEN", "postal_district": "1",
     "25th_percentile": "na", "median": "-", "75th_percentile": "", "rental_contracts": "12"},
]


@pytest.fixture
def source(tmp_path):
    cache = tmp_path / "rentals.json"
    import time
    cache.write_text(json.dumps({"fetched_at": time.time(), "records": ROWS}))
    return DataGovSource(cache_path=cache)


def test_build_benchmarks_weights_quarters_and_skips_bad_rows():
    b = build_benchmarks(ROWS, source="test")
    assert "BROKEN" not in b
    loft = b["LOFT @ NATHAN"]
    assert loft.contracts == 40
    assert loft.median == pytest.approx((6.0 * 10 + 6.3 * 30) / 40, abs=0.01)
    assert loft.quarters == ("2026-Q1", "2026-Q2")


@pytest.mark.parametrize("raw", ["Loft@Nathan", "loft at nathan", "The Loft @ Nathan", "LOFT @ NATHAN"])
def test_name_matching_variants(raw):
    name, score = match_project(raw, ["LOFT @ NATHAN", "26 NEWTON"])
    assert name == "LOFT @ NATHAN" and score == 1.0


def test_unknown_project_does_not_match():
    assert match_project("Completely Different Place", ["26 NEWTON"]) == (None, 0.0)


def test_normalise():
    assert normalise("The Tembusu") == "TEMBUSU"


def test_under_target_is_kept(source):
    # 2900 / 550 = 5.27 psf: between 18 Woodsville's p25 (4.90) and median (5.63)
    v = evaluate(Listing("18 Woodsville", 2900, 550), source)
    assert v.keep and v.band == "below median" and v.good_deal


def test_stretch_budget_kept_only_if_below_market(source):
    # 26 Newton median 6.52 psf. 3400/550 = 6.18 -> below median -> keep
    good = evaluate(Listing("26 Newton", 3400, 550), source)
    assert good.keep and good.good_deal
    # 3400/510 = 6.67 -> above median -> skip
    bad = evaluate(Listing("26 Newton", 3400, 510), source)
    assert not bad.keep and bad.band == "above median"


def test_hard_limits(source):
    assert not evaluate(Listing("26 Newton", 3600, 800), source).keep   # over max
    assert not evaluate(Listing("26 Newton", 2500, 450), source).keep   # too small


def test_suspiciously_cheap_flag(source):
    v = evaluate(Listing("26 Newton", 2000, 550), source)  # 3.64 psf vs p25 6.16
    assert any("suspiciously cheap" in f for f in v.flags)


def test_no_data_project(source):
    v = evaluate(Listing("Tiny Boutique Condo", 3200, 600), source)
    assert v.band == "no data" and not v.keep
    assert any("no market data" in f for f in v.flags)


def test_low_contract_count_flag(source):
    v = evaluate(Listing("18 Woodsville", 2900, 550), source)
    assert any("only 10 contracts" in f for f in v.flags)


def test_studio_rejected(source):
    v = evaluate(Listing("26 Newton", 2900, 600, bedrooms=0), source)
    assert not v.keep and "studio" in v.decision


def test_small_one_bedroom_flagged(source):
    # Lumiere case: 506 sqft studio listed as 1BR
    v = evaluate(Listing("26 Newton", 2900, 506, bedrooms=1), source)
    assert any("may be a studio" in f for f in v.flags)
    roomy = evaluate(Listing("26 Newton", 2900, 600, bedrooms=1), source)
    assert not any("may be a studio" in f for f in roomy.flags)
