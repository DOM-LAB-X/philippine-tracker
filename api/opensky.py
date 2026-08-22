"""
OpenSky Network REST API client.
Docs: https://openskynetwork.github.io/opensky-api/rest.html

Anonymous users: ~400 API credits/day, minimum 10s between state requests.
Registered users: higher limits. Credentials are optional.
We poll every 30 minutes by default, well within any rate limit.
"""
import logging
import time
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

OPENSKY_BASE = "https://opensky-network.org/api"
TIMEOUT = 15
USER_AGENT = "PhilFlight-Tracker/1.0"

# Philippine airspace bounding box
PH_BBOX = {"lamin": 4.5, "lomin": 116.0, "lamax": 21.5, "lomax": 127.0}


class OpenSkyError(Exception):
    pass


class RateLimitError(OpenSkyError):
    pass


class NetworkError(OpenSkyError):
    pass


class OpenSkyClient:
    def __init__(self, username: str = "", password: str = "") -> None:
        self._auth = (username, password) if username else None
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        self._last_req: float = 0.0

    # ------------------------------------------------------------------ #
    # Public methods                                                       #
    # ------------------------------------------------------------------ #

    def get_departures(self, airport: str, hours_back: int = 2) -> list[dict]:
        """Flights that departed from *airport* in the past N hours."""
        now = int(time.time())
        data = self._get(
            "flights/departure",
            {"airport": airport, "begin": now - hours_back * 3600, "end": now},
        )
        return [self._norm_flight(f) for f in (data or [])]

    def get_arrivals(self, airport: str, hours_back: int = 2) -> list[dict]:
        """Flights that arrived at *airport* in the past N hours."""
        now = int(time.time())
        data = self._get(
            "flights/arrival",
            {"airport": airport, "begin": now - hours_back * 3600, "end": now},
        )
        return [self._norm_flight(f) for f in (data or [])]

    def get_live_states(self) -> list[dict]:
        """Live flight states within Philippine airspace."""
        data = self._get("states/all", PH_BBOX)
        if not data or not data.get("states"):
            return []
        return [self._norm_state(s) for s in data["states"]]

    def get_routes_from_to(
        self,
        departure: str,
        arrival: str = "",
        hours_back: int = 2,
        airline_prefix: str = "",
    ) -> list[dict]:
        """
        Departures from *departure*, optionally filtered to flights heading
        to *arrival* and/or belonging to *airline_prefix*.
        """
        flights = self.get_departures(departure, hours_back)
        result = []
        for f in flights:
            if arrival and f.get("arrival_airport") != arrival:
                continue
            callsign = f.get("callsign", "")
            if airline_prefix and not callsign.upper().startswith(airline_prefix.upper()):
                continue
            result.append(f)
        return result

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _get(self, endpoint: str, params: dict) -> Optional[Any]:
        self._throttle()
        url = f"{OPENSKY_BASE}/{endpoint}"
        try:
            resp = self._session.get(url, params=params, auth=self._auth, timeout=TIMEOUT)
            self._last_req = time.time()
            if resp.status_code == 429:
                raise RateLimitError("OpenSky rate limit exceeded.")
            if resp.status_code == 401:
                raise OpenSkyError("Bad OpenSky credentials.")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout:
            raise NetworkError("OpenSky request timed out.")
        except requests.ConnectionError as exc:
            raise NetworkError(f"Cannot reach OpenSky: {exc}") from exc
        except requests.HTTPError as exc:
            raise OpenSkyError(f"HTTP error: {exc}") from exc

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_req
        min_gap = 5.0
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)

    @staticmethod
    def _norm_flight(raw: dict) -> dict:
        return {
            "callsign": (raw.get("callsign") or "").strip(),
            "icao24": raw.get("icao24", ""),
            "departure_airport": raw.get("estDepartureAirport") or "",
            "arrival_airport": raw.get("estArrivalAirport") or "",
            "first_seen": raw.get("firstSeen"),
            "last_seen": raw.get("lastSeen"),
            "on_ground": None,
            "baro_altitude_m": None,
            "velocity_ms": None,
        }

    @staticmethod
    def _norm_state(s: list) -> dict:
        return {
            "callsign": (s[1] or "").strip(),
            "icao24": s[0],
            "departure_airport": "",
            "arrival_airport": "",
            "first_seen": s[3],
            "last_seen": s[4],
            "longitude": s[5],
            "latitude": s[6],
            "baro_altitude_m": s[7],
            "on_ground": s[8],
            "velocity_ms": s[9],
            "true_track": s[10],
            "origin_country": s[2],
        }
