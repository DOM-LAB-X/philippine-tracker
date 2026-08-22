"""
DealMonitor — background thread that polls Reddit and airline promo pages.

Keeps a deduplication set so only *new* deals fire the callback.
The seen-URLs set is persisted to data/seen_deals.json across restarts.
"""
import json
import logging
import threading
from pathlib import Path
from typing import Callable, List, Optional, Set

logger = logging.getLogger(__name__)

SEEN_FILE = Path(__file__).parent.parent / "data" / "seen_deals.json"


class DealMonitor:
    def __init__(self, check_interval_minutes: int = 60) -> None:
        self._interval = check_interval_minutes * 60
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seen: Set[str] = self._load_seen()

        self.on_new_deals: Optional[Callable[[List[dict]], None]] = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="DealMonitor"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def check_now(self) -> None:
        threading.Thread(target=self._check, daemon=True, name="DealCheckOnce").start()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        self._check()
        while not self._stop.wait(self._interval):
            self._check()

    def _check(self) -> None:
        all_deals: List[dict] = []

        try:
            from scrapers.reddit import search_deals
            all_deals.extend(search_deals(hours_back=24))
        except Exception as exc:
            logger.warning("Reddit deal check failed: %s", exc)

        try:
            from scrapers.airline_deals import fetch_all_deals
            all_deals.extend(fetch_all_deals())
        except Exception as exc:
            logger.warning("Airline deals check failed: %s", exc)

        new = [d for d in all_deals if d.get("url") and d["url"] not in self._seen]

        for d in new:
            self._seen.add(d["url"])
        self._save_seen()

        if new and self.on_new_deals:
            self.on_new_deals(new)

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def _load_seen(self) -> Set[str]:
        try:
            with open(SEEN_FILE, encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()

    def _save_seen(self) -> None:
        try:
            SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SEEN_FILE, "w", encoding="utf-8") as f:
                # Keep at most the last 2000 URLs to prevent unbounded growth
                urls = list(self._seen)[-2000:]
                json.dump(urls, f)
        except Exception as exc:
            logger.warning("Could not save seen deals: %s", exc)
