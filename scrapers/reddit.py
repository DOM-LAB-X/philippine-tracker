"""
Reddit deal monitor using RSS feeds.
Reddit's JSON API now requires OAuth, but RSS feeds are still publicly accessible.
"""
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List

import defusedxml.ElementTree as ET  # noqa: N817 — ET is the universal stdlib alias
import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "PhilFlight-Tracker/1.0 (deal monitor)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}
TIMEOUT = 15

SUBREDDITS = ["Philippines", "PHtravel", "phinvest"]

KEYWORDS = [
    "promo fare", "seat sale", "piso fare", "promo code",
    "discount code", "cebu pacific promo", "pal promo",
    "airasia promo", "airline sale", "travel deal", "piso",
]

# Atom namespace used by Reddit RSS
ATOM = "{http://www.w3.org/2005/Atom}"


def search_deals(hours_back: int = 24) -> List[dict]:
    """Return posts from Philippine subreddits that mention airline deals."""
    cutoff = datetime.now(timezone.utc).timestamp() - hours_back * 3600
    found: List[dict] = []
    seen: set = set()

    for sub in SUBREDDITS:
        for post in _fetch_subreddit_rss(sub, cutoff):
            if post["url"] not in seen:
                seen.add(post["url"])
                found.append(post)
        import time
        time.sleep(2)  # be polite between subreddit requests

    return found


def _fetch_subreddit_rss(sub: str, cutoff: float) -> List[dict]:
    """Fetch the subreddit's search RSS and filter by keyword + age."""
    url = f"https://www.reddit.com/r/{sub}/search.rss"
    params = {
        "q": "airline promo fare sale seat discount piso",
        "sort": "new",
        "restrict_sr": "1",
        "t": "week",
    }
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return _parse_atom(resp.text, sub, cutoff)
    except Exception as exc:
        logger.warning("Reddit r/%s RSS failed: %s", sub, exc)
        return []


def _parse_atom(xml_text: str, sub: str, cutoff: float) -> List[dict]:
    results = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Reddit RSS parse error: %s", exc)
        return []

    for entry in root.findall(f"{ATOM}entry"):
        # Title
        title_el = entry.find(f"{ATOM}title")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        # URL
        link_el = entry.find(f"{ATOM}link")
        url = link_el.get("href", "") if link_el is not None else ""

        # Published / updated timestamp
        updated_el = entry.find(f"{ATOM}updated") or entry.find(f"{ATOM}published")
        created = 0.0
        if updated_el is not None and updated_el.text:
            try:
                created = datetime.fromisoformat(
                    updated_el.text.replace("Z", "+00:00")
                ).timestamp()
            except ValueError:
                pass

        if created < cutoff:
            continue

        # Content (self-text preview)
        content_el = entry.find(f"{ATOM}content")
        content = content_el.text or "" if content_el is not None else ""

        combined = (title + " " + content).lower()
        if any(kw in combined for kw in KEYWORDS):
            results.append({
                "source": f"r/{sub}",
                "title": title[:300],
                "url": url,
                "score": 0,
                "created_utc": created,
                "type": "reddit",
            })

    return results
