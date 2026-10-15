"""Send the shortlist to Telegram.

Only needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (no server: sending a
message is a single HTTPS call, so it works from GitHub Actions).
Messages are compact cards (Telegram renders tables badly) and are split to
stay under Telegram's 4,096-character limit.
"""

from __future__ import annotations

import html
import json
import os
import urllib.request

from . import config
from .report import SGT, _layout, _market
from .shortlist import Shortlist

LIMIT = 3800   # Telegram max is 4096; keep a margin


def _card(i: int, v) -> str:
    l = v.listing
    e = html.escape
    lines = [
        f"<b>{i}. {e(l.project)}</b> (D{l.district})",
        f"S${l.rent:,.0f} · {l.sqft:,.0f} sqft · S${l.psf:.2f} psf · {_layout(l)}",
        f"{_market(v)}",
    ]
    for f in v.flags:
        if f.startswith("no market data"):
            continue   # already said on the line above
        if "same unit also listed" in f:
            text, _, url = f.rpartition(": ")
            lines.append(f"⚠️ {e(text)}: <a href=\"{e(url)}\">other listing</a>")
        else:
            lines.append(f"⚠️ {e(f)}")
    lines.append(f"<a href=\"{e(l.url)}\">Open on {e(l.source)}</a>")
    return "\n".join(lines)


def messages(sl: Shortlist, new_only: bool) -> list[str]:
    from datetime import datetime
    when = datetime.now(SGT).strftime("%a %d %b, %H:%M")
    scope = "new since last run" if new_only else "all current listings"
    head = (f"🏠 <b>Condo shortlist</b> · {when}\n"
            f"{len(sl.kept)} shortlisted · {len(sl.unverified)} need a price check ({scope})")
    if not sl.kept and not sl.unverified:
        return [head + "\n\nNothing new matches today."]
    blocks = []
    if sl.kept:
        blocks.append("<b>✅ Shortlist</b>")
        blocks += [_card(i, v) for i, v in enumerate(sl.kept, 1)]
    if sl.unverified:
        blocks.append(f"<b>🔎 Needs a price check</b> (S${config.TARGET_RENT:,}-{config.MAX_RENT:,}, "
                      "no market data yet)")
        blocks += [_card(i, v) for i, v in enumerate(sl.unverified, 1)]
    out, cur = [], head
    for b in blocks:
        if len(cur) + len(b) + 2 > LIMIT:
            out.append(cur)
            cur = b
        else:
            cur += "\n\n" + b
    out.append(cur)
    return out


def send(texts: list[str], token: str | None = None, chat_id: str | None = None) -> int:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        print("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID); skipping.")
        return 0
    for t in texts:
        body = json.dumps({"chat_id": chat_id, "text": t, "parse_mode": "HTML",
                           "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            if not json.load(resp).get("ok"):
                raise RuntimeError("Telegram refused the message")
    return len(texts)
