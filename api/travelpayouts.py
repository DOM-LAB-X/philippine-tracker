"""
Travelpayouts flight price API  (free replacement for Amadeus).

Sign up FREE at https://www.travelpayouts.com/developers/api
Copy your API token (32-char hex) and paste it in Settings.

What it covers:
  • Cheapest fares for any route (e.g. MNL → HNL)
  • Prices per day of a month (price calendar)
  • Philippine peso currency support
  • All major airlines serving Philippine routes

Rate limits: generous free tier — no hard cap for the endpoints we use.
"""
import logging
from typing import Optional

import requests

from api.amadeus import AIRLINE_NAMES, resolve_airline_codes

logger = logging.getLogger(__name__)

_BASE    = "https://api.travelpayouts.com"
_TIMEOUT = 15
_UA      = "PhilFlight-Tracker/1.0"


class TravelpayoutsError(Exception):
    pass


class TravelpayoutsClient:
    def __init__(self, token: str) -> None:
        self._token = token.strip()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent":     _UA,
            "X-Access-Token": self._token,
        })

    @property
    def is_configured(self) -> bool:
        return bool(self._token)

    # ── Public — same signature as AmadeusClient so they're interchangeable ──

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str = "",
        adults: int = 1,
        cabin_class: str = "ECONOMY",
        currency: str = "PHP",
        max_results: int = 10,
        airlines: str = "",
    ) -> list[dict]:
        """
        Return cheapest fares for a route, sorted by price.
        departure_date: YYYY-MM-DD or YYYY-MM
        airlines: comma-separated codes e.g. 'PAL, JAL, ANA'
        """
        offers = self._cheap_fares(origin, destination, departure_date,
                                   return_date, currency)
        if airlines:
            codes = set(resolve_airline_codes(airlines).split(","))
            offers = [o for o in offers if o.get("airline_code", "") in codes]

        return offers[:max_results]

    def get_price_calendar(
        self,
        origin: str,
        destination: str,
        month: str,
        currency: str = "PHP",
    ) -> list[dict]:
        """Cheapest price for each day in a given month (YYYY-MM)."""
        params = {
            "origin":          origin,
            "destination":     destination,
            "calendar_type":   "departure_date",
            "depart_date":     month[:7],
            "currency":        currency,
            "token":           self._token,
        }
        try:
            resp = self._session.get(
                f"{_BASE}/v1/prices/calendar", params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Travelpayouts calendar failed: %s", exc)
            return []

        if not data.get("success"):
            return []

        results = []
        for item in data.get("data", {}).values():
            code = item.get("airline", "")
            results.append({
                "airline_code":      code,
                "airline_name":      AIRLINE_NAMES.get(code, code),
                "departure_airport": origin,
                "arrival_airport":   destination,
                "departure_time":    item.get("depart_date", ""),
                "arrival_time":      "",
                "price_php":         float(item.get("value", 0)),
                "currency":          currency,
                "stops":             int(item.get("transfers", 0)),
                "duration":          "",
                "seats_left":        None,
                "source":            "Travelpayouts",
            })
        return sorted(results, key=lambda x: x["price_php"])

    # ── Internal ──────────────────────────────────────────────────────────────

    def _cheap_fares(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        return_date: str,
        currency: str,
    ) -> list[dict]:
        params: dict = {
            "origin":      origin,
            "destination": destination,
            "currency":    currency,
            "token":       self._token,
        }
        if depart_date:
            params["depart_date"] = depart_date[:7]   # YYYY-MM
        if return_date:
            params["return_date"] = return_date[:7]

        try:
            resp = self._session.get(
                f"{_BASE}/v1/prices/cheap", params=params, timeout=_TIMEOUT)
            if resp.status_code == 401:
                raise TravelpayoutsError(
                    "Invalid Travelpayouts token — check Settings.")
            resp.raise_for_status()
            data = resp.json()
        except TravelpayoutsError:
            raise
        except Exception as exc:
            logger.warning("Travelpayouts cheap fares failed: %s", exc)
            return []

        if not data.get("success"):
            logger.warning("Travelpayouts returned success=false for %s->%s",
                           origin, destination)
            return []

        results: list[dict] = []
        for _dest_key, fares in data.get("data", {}).items():
            for _date_key, fare in fares.items():
                code = fare.get("airline", "")
                results.append({
                    "airline_code":      code,
                    "airline_name":      AIRLINE_NAMES.get(code, code),
                    "departure_airport": origin,
                    "arrival_airport":   destination,
                    "departure_time":    fare.get("departure_at", ""),
                    "arrival_time":      fare.get("return_at", ""),
                    "price_php":         float(fare.get("price", 0)),
                    "currency":          currency,
                    "stops":             int(fare.get("transfers", 0)),
                    "duration":          "",
                    "seats_left":        fare.get("number_of_changes"),
                    "source":            "Travelpayouts",
                })

        return sorted(results, key=lambda x: x["price_php"])
