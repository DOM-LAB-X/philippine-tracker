"""
SerpApi — Google Flights API.
Returns real-time results identical to google.com/flights.

Free tier:  100 searches / month  (no credit card needed)
Paid plans: serpapi.com/pricing

Sign up: https://serpapi.com
Copy your API key from the dashboard and paste it in  ⚙  Settings.

Docs: https://serpapi.com/google-flights-api
"""
import logging
from typing import Optional

import requests

from api.amadeus import AIRLINE_NAMES, resolve_airline_codes

logger = logging.getLogger(__name__)

_BASE    = "https://serpapi.com/search"
_TIMEOUT = 30
_UA      = "PhilFlight-Tracker/1.0"

# cabin_class string → Google Flights travel_class integer
_CABIN = {
    "ECONOMY":         1,
    "PREMIUM_ECONOMY": 2,
    "BUSINESS":        3,
    "FIRST":           4,
}


class SerpApiError(Exception):
    pass


class SerpApiClient:
    """
    Google Flights via SerpApi.  Same interface as TravelpayoutsClient and
    AmadeusClient so the app can swap between them without changes elsewhere.
    """

    def __init__(self, api_key: str) -> None:
        self._key = api_key.strip()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = _UA

    @property
    def is_configured(self) -> bool:
        return bool(self._key)

    # ── Public ────────────────────────────────────────────────────────────────

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str = "",
        adults: int = 1,
        cabin_class: str = "ECONOMY",
        currency: str = "PHP",
        max_results: int = 15,
        airlines: str = "",
    ) -> list[dict]:
        """
        Search Google Flights for the given route and dates.
        Returns a list of offers sorted cheapest first.
        """
        if not self.is_configured:
            raise SerpApiError("No SerpApi key configured.")

        params: dict = {
            "engine":        "google_flights",
            "api_key":       self._key,
            "departure_id":  origin.upper(),
            "arrival_id":    destination.upper(),
            "outbound_date": departure_date[:10],
            "currency":      currency,
            "hl":            "en",
            "gl":            "ph",
            "adults":        adults,
            "travel_class":  _CABIN.get(cabin_class.upper(), 1),
            "type":          1 if return_date else 2,   # 1=round trip, 2=one way
            "sort_by":       1,                          # 1=top departing
        }

        if return_date:
            params["return_date"] = return_date[:10]

        # Airline filter — SerpApi uses IATA codes
        if airlines:
            iata = resolve_airline_codes(airlines)
            if iata:
                params["include_airlines"] = iata

        try:
            resp = self._session.get(_BASE, params=params, timeout=_TIMEOUT)
            if resp.status_code == 401:
                raise SerpApiError(
                    "Invalid SerpApi key — check Settings.")
            if resp.status_code == 429:
                raise SerpApiError(
                    "SerpApi monthly limit reached (100 free searches/month). "
                    "See serpapi.com/pricing to upgrade.")
            resp.raise_for_status()
            data = resp.json()
        except SerpApiError:
            raise
        except Exception as exc:
            logger.warning("SerpApi request failed: %s", exc)
            raise SerpApiError(f"Network error: {exc}") from exc

        if "error" in data:
            raise SerpApiError(f"SerpApi error: {data['error']}")

        offers = []
        for group in ("best_flights", "other_flights"):
            for item in data.get(group, []):
                parsed = self._parse_itinerary(item, currency)
                if parsed:
                    offers.append(parsed)

        offers.sort(key=lambda x: x["price_php"])
        return offers[:max_results]

    # ── Parser ────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_itinerary(item: dict, currency: str) -> Optional[dict]:
        segments = item.get("flights", [])
        if not segments:
            return None

        first   = segments[0]
        last    = segments[-1]
        price   = item.get("price", 0)
        dur_min = item.get("total_duration", 0)
        stops   = len(segments) - 1

        dep_airport  = first.get("departure_airport", {})
        arr_airport  = last.get("arrival_airport", {})
        dep_time_raw = dep_airport.get("time", "")   # "2026-11-14 10:00"
        arr_time_raw = arr_airport.get("time", "")

        # Convert "YYYY-MM-DD HH:MM" → ISO format for fmt_iso_time
        def _to_iso(raw: str) -> str:
            return raw.replace(" ", "T") if raw else ""

        airline_name = first.get("airline", "")
        airline_code = first.get("airline_logo", "").split("/")[-1].replace(".png", "") \
            if first.get("airline_logo") else ""

        # duration: X h Y m
        dur_s = ""
        if dur_min:
            h, m = divmod(int(dur_min), 60)
            dur_s = f"{h}h {m}m" if m else f"{h}h"

        return {
            "airline_code":      airline_code,
            "airline_name":      airline_name or AIRLINE_NAMES.get(airline_code, airline_code),
            "flight_number":     first.get("flight_number", ""),
            "departure_airport": dep_airport.get("id", ""),
            "arrival_airport":   arr_airport.get("id", ""),
            "departure_time":    _to_iso(dep_time_raw),
            "arrival_time":      _to_iso(arr_time_raw),
            "price_php":         float(price),
            "currency":          currency,
            "stops":             stops,
            "duration":          dur_s,
            "airplane":          first.get("airplane", ""),
            "seats_left":        None,
            "carbon_kg":         item.get("carbon_emissions", {}).get(
                                     "this_flight", 0) // 1000 or None,
            "source":            "Google Flights (SerpApi)",
        }
