"""
PriceTracker — polls Amadeus for configured routes and fires alerts on price drops.
Price history is stored in data/price_history.json.
"""
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from api.amadeus import AmadeusClient, AmadeusError

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent.parent / "data" / "price_history.json"


class PriceTracker:
    def __init__(
        self,
        client: AmadeusClient,
        settings,
        check_interval_minutes: int = 60,
    ) -> None:
        self._client   = client
        self._settings = settings
        self._interval = check_interval_minutes * 60
        self._stop     = threading.Event()
        self._wake     = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._history: dict = _load_json(HISTORY_FILE)

        self.on_price_drop:      Optional[Callable[[dict], None]]       = None
        self.on_prices_updated:  Optional[Callable[[List[dict]], None]] = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if not self._client.is_configured:
            logger.info("Amadeus not configured — price tracker inactive.")
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="PriceTracker"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def check_now(self) -> None:
        threading.Thread(target=self._check, daemon=True, name="PriceCheckOnce").start()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        self._check()
        while not self._stop.is_set():
            self._wake.wait(timeout=self._interval)
            self._wake.clear()
            if not self._stop.is_set():
                self._check()

    def _check(self) -> None:
        routes: list = self._settings.get("watched_price_routes", [])
        if not routes:
            return

        all_offers: List[dict] = []
        threshold: float = float(self._settings.get("price_drop_threshold_pct", 10))

        for route in routes:
            origin = route.get("from", "")
            dest   = route.get("to",   "")
            dep_date = route.get("date", "")
            if not (origin and dest and dep_date):
                continue
            try:
                offers = self._client.search_flights(origin, dest, dep_date)
                if offers:
                    all_offers.extend(offers)
                    self._process_price(origin, dest, dep_date, offers[0], threshold)
            except AmadeusError as exc:
                logger.warning("Price check %s→%s: %s", origin, dest, exc)
            except Exception:
                logger.exception("Unexpected error in price check %s→%s", origin, dest)

        if all_offers and self.on_prices_updated:
            self.on_prices_updated(all_offers)

    def _process_price(
        self,
        origin: str,
        dest: str,
        dep_date: str,
        cheapest: dict,
        threshold_pct: float,
    ) -> None:
        key = f"{origin}-{dest}-{dep_date}"
        now_price = cheapest["price_php"]
        history: list = self._history.setdefault(key, [])

        prev_prices = [h["price"] for h in history]
        history.append({
            "timestamp": datetime.now().isoformat(),
            "price":     now_price,
            "airline":   cheapest.get("airline_name", ""),
        })
        self._history[key] = history[-200:]  # cap to 200 data points per route
        _save_json(HISTORY_FILE, self._history)

        if not prev_prices:
            return
        prev_min = min(prev_prices)
        if prev_min > 0:
            drop_pct = (prev_min - now_price) / prev_min * 100
            if drop_pct >= threshold_pct:
                if self.on_price_drop:
                    self.on_price_drop({
                        "route":     f"{origin} → {dest}",
                        "old_price": prev_min,
                        "new_price": now_price,
                        "airline":   cheapest.get("airline_name", ""),
                        "date":      dep_date,
                        "url":       "",
                    })

    def get_history(self, origin: str, dest: str, dep_date: str) -> list:
        key = f"{origin}-{dest}-{dep_date}"
        return self._history.get(key, [])


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as exc:
        logger.warning("Could not save %s: %s", path.name, exc)
