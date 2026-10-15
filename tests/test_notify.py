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
