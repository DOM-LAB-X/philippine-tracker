"""
Scraper for Philippine airline deals/promo pages.

Notes on Facebook:
  Facebook's website is fully JavaScript-rendered and protected by bot detection.
  The official Graph API requires app review and is no longer freely accessible.
  We therefore monitor the airlines' *own* promo pages directly — which are
  faster to load, more reliable, and contain the same information.

If you later want true Facebook monitoring, install playwright:
    pip install playwright && playwright install chromium
  and replace the requests-based fetchers below with a headless browser session.
"""
import logging
from typing import List

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TIMEOUT = 20
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_all_deals() -> List[dict]:
    """Aggregate deals from all monitored airline promo pages."""
    deals: List[dict] = []
    for fetcher in (_pal_deals, _ceb_deals, _airasia_deals):
        try:
            deals.extend(fetcher())
        except Exception as exc:
            logger.warning("%s failed: %s", fetcher.__name__, exc)
    return deals


# ------------------------------------------------------------------ #
# Individual airline scrapers                                          #
# ------------------------------------------------------------------ #

def _pal_deals() -> List[dict]:
    url = "https://www.philippineairlines.com/en/ph/home/promos"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    deals = []
    # PAL uses article or div cards on their promos page
    selectors = [
        "article", ".promo-card", ".promo-item",
        "[class*='promo']", "[class*='promotion']", "[class*='deal']",
    ]
    seen: set = set()
    for sel in selectors:
        for card in soup.select(sel):
            heading = card.find(["h2", "h3", "h4", "strong"])
            title = (heading.get_text(strip=True) if heading else card.get_text(strip=True))[:200]
            if not title or title in seen:
                continue
            link = card.find("a", href=True)
            href = link["href"] if link else url
            if href and not href.startswith("http"):
                href = "https://www.philippineairlines.com" + href
            seen.add(title)
            deals.append({"source": "Philippine Airlines", "title": title, "url": href or url, "type": "airline"})
        if deals:
            break  # found something with this selector, skip the rest

    if not deals:
        logger.debug("PAL deals page returned no cards (site structure may have changed).")
    return deals


def _ceb_deals() -> List[dict]:
    url = "https://www.cebupacificair.com/pages/promos"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    deals = []
    seen: set = set()
    selectors = [
        ".promo", ".promo-card", "article",
        "[class*='promo']", "[class*='offer']", "[class*='sale']",
    ]
    for sel in selectors:
        for card in soup.select(sel):
            heading = card.find(["h2", "h3", "h4"])
            title = (heading.get_text(strip=True) if heading else card.get_text(strip=True))[:200]
            if not title or title in seen:
                continue
            link = card.find("a", href=True)
            href = link["href"] if link else url
            if href and not href.startswith("http"):
                href = "https://www.cebupacificair.com" + href
            seen.add(title)
            deals.append({"source": "Cebu Pacific", "title": title, "url": href or url, "type": "airline"})
        if deals:
            break

    if not deals:
        logger.debug("CEB deals page returned no cards.")
    return deals


def _airasia_deals() -> List[dict]:
    # AirAsia's sale page (PH)
    url = "https://www.airasia.com/en/ph/flights/deals"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception:
        # AirAsia often requires JS; return empty rather than crash
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    deals = []
    seen: set = set()
    for card in soup.select("[class*='deal'], [class*='offer'], article"):
        heading = card.find(["h2", "h3", "h4"])
        title = (heading.get_text(strip=True) if heading else card.get_text(strip=True))[:200]
        if not title or title in seen:
            continue
        link = card.find("a", href=True)
        href = link["href"] if link else url
        if href and not href.startswith("http"):
            href = "https://www.airasia.com" + href
        seen.add(title)
        deals.append({"source": "AirAsia PH", "title": title, "url": href or url, "type": "airline"})

    return deals
