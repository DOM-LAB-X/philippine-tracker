"""
Travelpayouts flight price API  (free replacement for Amadeus).

Sign up FREE at https://www.travelpayouts.com
Then get your token at https://www.travelpayouts.com/programs/100/tools/api

Primary endpoint: /aviasales/v3/prices_for_dates
  - Searches specific dates (not just a monthly cache)
  - Returns actual available fares for the date you pick
  - Works for all routes including less-popular ones like HNL<->MNL

Fallback endpoint: /v1/prices/cheap
  - Monthly price cache from past searches
  - Only has data for popular/recently-searched routes
"""
import logging
from datetime import date as _date
from typing import Optional

import requests

from api.amadeus import AIRLINE_NAMES, resolve_airline_codes

logger = logging.getLogger(__name__)

_BASE    = "https://api.travelpayouts.com"
_TIMEOUT = 20
_UA      = "PhilFlight-Tracker/1.0"


class TravelpayoutsError(Exception):
    pass


def _filter_by_date(offers: list, target_iso: str, field: str) -> list:
    """Keep only offers whose date field is within ±1 day of target_iso."""
    try:
        target = _date.fromisoformat(target_iso[:10])
    except ValueError:
        return offers   # can't parse, return as-is

    result = []
    for o in offers:
        raw = o.get(field, "")
        if not raw:
            result.append(o)   # no date info, include it
            continue
        try:
            offer_date = _date.fromisoformat(str(raw)[:10])
            if abs((offer_date - target).days) <= 1:
                result.append(o)
        except ValueError:
            result.append(o)   # unparseable, include it

    # If strict filter removed everything, return original so user sees something
    return result if result else offers


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

    # ── Public ────────────────────────────────────────────────────────────────

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str = "",
        adults: int = 1,
        cabin_class: str = "ECONOMY",
        currency: str = "USD",
        max_results: int = 15,
        airlines: str = "",
    ) -> list[dict]:
        """
        Return fares for a specific date, sorted cheapest first.

        Tries the v3 date-specific endpoint first (best for exact dates like
        2026-11-14), then falls back to the v1 monthly cache if empty.
        """
        if not self.is_configured:
            raise TravelpayoutsError("No Travelpayouts token configured.")

        offers = self._v3_prices(origin, destination, departure_date,
                                  return_date, currency, max_results)

        # v3 returned nothing — try the monthly cache as a fallback
        if not offers:
            logger.info("v3 returned 0 results, trying v1 cache for %s->%s",
                        origin, destination)
            offers = self._v1_cheap(origin, destination, departure_date,
                                     return_date, currency)

        # Filter by airline if requested
        if airlines and offers:
            codes = set(resolve_airline_codes(airlines).split(","))
            filtered = [o for o in offers if o.get("airline_code", "") in codes]
            if filtered:   # only apply filter if it doesn't eliminate everything
                offers = filtered

        return offers[:max_results]

    def get_price_calendar(
        self,
        origin: str,
        destination: str,
        month: str,
        currency: str = "USD",
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

    # ── Endpoints ─────────────────────────────────────────────────────────────

    def _v3_prices(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str,
        currency: str,
        limit: int,
    ) -> list[dict]:
        """
        /aviasales/v3/prices_for_dates — searches a specific date range.
        Returns an array of available fares (not a nested monthly cache).
        Best for: specific dates, less-popular routes like HNL<->MNL.
        """
        params: dict = {
            "origin":        origin,
            "destination":   destination,
            "currency":      currency,
            "sorting":       "price",
            "direct":        "false",
            "limit":         limit,
            "token":         self._token,
        }
        if departure_date:
            params["departure_at"] = departure_date[:10]   # YYYY-MM-DD
        if return_date:
            params["return_at"] = return_date[:10]

        try:
            resp = self._session.get(
                f"{_BASE}/aviasales/v3/prices_for_dates",
                params=params, timeout=_TIMEOUT,
            )
            if resp.status_code == 401:
                raise TravelpayoutsError(
                    "Invalid Travelpayouts token — check Settings.")
            if resp.status_code == 404:
                logger.warning("v3 endpoint not found for %s->%s", origin, destination)
                return []
            resp.raise_for_status()
            data = resp.json()
        except TravelpayoutsError:
            raise
        except Exception as exc:
            logger.warning("v3 prices_for_dates failed (%s->%s): %s",
                           origin, destination, exc)
            return []

        if not data.get("success"):
            logger.info("v3 success=false for %s->%s: %s",
                        origin, destination, data.get("error", ""))
            return []

        return self._parse_v3(data.get("data", []), currency)

    def _v1_cheap(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        return_date: str,
        currency: str,
    ) -> list[dict]:
        """
        /v1/prices/cheap — monthly cache of past searches.
        Returns data only if this route was recently searched on Travelpayouts.
        """
        params: dict = {
            "origin":      origin,
            "destination": destination,
            "currency":    currency,
            "token":       self._token,
        }
        if depart_date:
            params["depart_date"] = depart_date[:7]    # YYYY-MM
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
            logger.warning("v1 cheap failed (%s->%s): %s",
                           origin, destination, exc)
            return []

        if not data.get("success"):
            return []

        return self._parse_v1(data.get("data", {}), origin, destination, currency)

    # ── Parsers ───────────────────────────────────────────────────────────────

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _parse_v3(self, items: list, currency: str) -> list[dict]:
        """Parse the v3 array response."""
        results = []
        for item in items:
            code = item.get("airline", "")
            dep  = item.get("departure_at", "")
            ret  = item.get("return_at", "")
            dur  = item.get("duration", 0)
            dur_s = f"{dur // 60}h {dur % 60}m" if dur else ""
            results.append({
                "airline_code":      code,
                "airline_name":      AIRLINE_NAMES.get(code, code),
                "departure_airport": item.get("origin_airport",  item.get("origin", "")),
                "arrival_airport":   item.get("destination_airport", item.get("destination", "")),
                "departure_time":    dep,
                "arrival_time":      ret,
                "price_php":         float(item.get("price", 0)),
                "currency":          currency,
                "stops":             int(item.get("transfers", 0)),
                "duration":          dur_s,
                "seats_left":        item.get("number_of_changes"),
                "link":              item.get("link", ""),
                "source":            "Travelpayouts",
            })
        return sorted(results, key=lambda x: x["price_php"])

    def _parse_v1(
        self,
        data: dict,
        origin: str,
        destination: str,
        currency: str,
    ) -> list[dict]:
        """Parse the v1 nested-dict response."""
        results = []
        for _dest_key, fares in data.items():
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
                    "link":              "",
                    "source":            "Travelpayouts",
                })
        return sorted(results, key=lambda x: x["price_php"])
