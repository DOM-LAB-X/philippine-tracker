"""
Reddit deal monitor.
Uses Reddit's public JSON API — no authentication needed.
Searches r/Philippines and r/PHtravel for airline promo keywords.
"""
import logging
from datetime import datetime, timezone
from typing import List

import requests

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "PhilFlight-Tracker/1.0 (deal monitor; contact via GitHub)"}
TIMEOUT = 15

SUBREDDITS = ["Philippines", "PHtravel", "phinvest"]

KEYWORDS = [
    "promo fare", "seat sale", "piso fare", "promo code",
    "discount code", "cebu pacific promo", "pal promo",
    "airasia promo", "airline sale", "travel deal",
]


def search_deals(hours_back: int = 24) -> List[dict]:
    """
    Return Reddit posts from Philippine subreddits that mention airline deals.
    Posts older than *hours_back* are ignored.
    """
    cutoff = datetime.now(timezone.utc).timestamp() - hours_back * 3600
    found: List[dict] = []

    for sub in SUBREDDITS:
        found.extend(_search_subreddit(sub, cutoff))

    # Deduplicate by URL
    seen: set = set()
    unique = []
    for post in found:
        if post["url"] not in seen:
            seen.add(post["url"])
            unique.append(post)

    return unique


def _search_subreddit(sub: str, cutoff: float) -> List[dict]:
    url = f"https://www.reddit.com/r/{sub}/search.json"
    params = {
        "q": "airline promo fare sale seat discount",
        "sort": "new",
        "restrict_sr": "true",
        "limit": 25,
        "t": "day",
    }
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        posts = resp.json().get("data", {}).get("children", [])
    except Exception as exc:
        logger.warning("Reddit r/%s fetch failed: %s", sub, exc)
        return []

    results = []
    for item in posts:
        data = item.get("data", {})
        created = data.get("created_utc", 0)
        if created < cutoff:
            continue
        text = (data.get("title", "") + " " + data.get("selftext", "")).lower()
        if any(kw in text for kw in KEYWORDS):
            results.append({
                "source": f"r/{sub}",
                "title": data.get("title", "")[:300],
                "url": "https://www.reddit.com" + data.get("permalink", ""),
                "score": data.get("score", 0),
                "created_utc": created,
                "type": "reddit",
            })
    return results
