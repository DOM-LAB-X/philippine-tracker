"""
Amadeus flight-search API client.

Amadeus is the primary data supplier for Google Flights, Kayak, and most major
aggregators, so its prices are functionally identical to what you see on Google Flights.

Sign up (free): https://developers.amadeus.com/self-service
 • Test environment  — simulated data, free, no approval
 • Production        — live data, requires a one-click approval request

Set amadeus_client_id / amadeus_client_secret in Settings.
Leave amadeus_environment as "test" until you get production approved.
"""
import logging
import time
from datetime import date, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_TEST_BASE = "https://test.api.amadeus.com"
_PROD_BASE = "https://api.amadeus.com"
_TOKEN_PATH  = "/v1/security/oauth2/token"
_SEARCH_PATH = "/v2/shopping/flight-offers"
_TIMEOUT = 20

# ICAO → IATA code lookup for Philippine airports
ICAO_TO_IATA: dict[str, str] = {
    "RPLL": "MNL",   # Manila
    "RPVM": "CEB",   # Cebu
    "RPMD": "DVO",   # Davao
    "RPLC": "CRK",   # Clark
    "RPVD": "DGT",   # Dumaguete
    "RPUI": "GES",   # General Santos
    "RPVI": "ILO",   # Iloilo
    "RPUB": "BCD",   # Bacolod
    "RPVK": "KLO",   # Kalibo
    "RPSP": "PPS",   # Puerto Princesa
    "RPUZ": "ZAM",   # Zamboanga
    "RPVB": "TAG",   # Bohol-Panglao
}

# IATA 2-letter code → full airline name
AIRLINE_NAMES: dict[str, str] = {
    "PR": "Philippine Airlines",
    "5J": "Cebu Pacific",
    "Z2": "AirAsia Philippines",
    "DG": "PAL Express",
    "JL": "Japan Airlines",
    "NH": "All Nippon Airways (ANA)",
    "KE": "Korean Air",
    "OZ": "Asiana Airlines",
    "SQ": "Singapore Airlines",
    "CX": "Cathay Pacific",
    "EK": "Emirates",
    "QR": "Qatar Airways",
    "EY": "Etihad Airways",
    "TG": "Thai Airways",
    "MH": "Malaysia Airlines",
    "GA": "Garuda Indonesia",
    "CI": "China Airlines",
    "BR": "EVA Air",
    "UA": "United Airlines",
    "AA": "American Airlines",
    "DL": "Delta Air Lines",
    "HA": "Hawaiian Airlines",
}

# Common 2–3 letter aliases → IATA code
_ALIAS_TO_IATA: dict[str, str] = {
    "PAL": "PR",  "PR":  "PR",
    "CEB": "5J",  "5J":  "5J",
    "APA": "Z2",  "Z2":  "Z2",   "AIRASIA": "Z2",
    "JAL": "JL",  "JL":  "JL",
    "ANA": "NH",  "NH":  "NH",
    "KAL": "KE",  "KE":  "KE",
    "AAR": "OZ",  "OZ":  "OZ",
    "SIA": "SQ",  "SQ":  "SQ",
    "CPA": "CX",  "CX":  "CX",
    "UAE": "EK",  "EK":  "EK",
    "QTR": "QR",  "QR":  "QR",
    "ETD": "EY",  "EY":  "EY",
    "THA": "TG",  "TG":  "TG",
    "MAS": "MH",  "MH":  "MH",
    "GIA": "GA",  "GA":  "GA",
    "CAL": "CI",  "CI":  "CI",
    "EVA": "BR",  "BR":  "BR",
    "UAL": "UA",  "UA":  "UA",
    "AAL": "AA",  "AA":  "AA",
    "DAL": "DL",  "DL":  "DL",
    "HAL": "HA",  "HA":  "HA",
}


def resolve_airline_codes(raw: str) -> str:
    """
    Convert user-typed airline names to comma-separated IATA codes.
    Accepts any mix of aliases: 'JAL, ANA, PAL' → 'JL,NH,PR'
    Unknown codes are passed through as-is.
    """
    codes = []
    for token in raw.upper().replace(" ", "").split(","):
        if token:
            codes.append(_ALIAS_TO_IATA.get(token, token))
    return ",".join(dict.fromkeys(codes))  # deduplicate, preserve order


class AmadeusError(Exception):
    pass


class AmadeusAuthError(AmadeusError):
    pass


class AmadeusClient:
    def __init__(self, client_id: str, client_secret: str, production: bool = False) -> None:
        self._id = client_id
        self._secret = client_secret
        self._base = _PROD_BASE if production else _TEST_BASE
        self._token: str = ""
        self._token_exp: float = 0.0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "PhilFlight-Tracker/1.0"

    @property
    def is_configured(self) -> bool:
        return bool(self._id and self._secret)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

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
        Search for flights.  airlines is a comma-separated list of IATA or
        common codes, e.g. 'JAL, ANA, PAL' or 'JL,NH,PR'.
        """
        """
        Search for flights.  origin / destination accept both IATA (MNL) and
        ICAO (RPLL) codes — ICAO is converted automatically.
        departure_date: YYYY-MM-DD
        """
        if not self.is_configured:
            raise AmadeusError("Amadeus API credentials not configured.")

        origin      = ICAO_TO_IATA.get(origin.upper(), origin.upper())
        destination = ICAO_TO_IATA.get(destination.upper(), destination.upper())

        self._ensure_token()
        params = {
            "originLocationCode":      origin,
            "destinationLocationCode": destination,
            "departureDate":           departure_date,
            "adults":                  adults,
            "currencyCode":            currency,
            "max":                     max_results,
            "travelClass":             cabin_class.upper(),
        }
        if return_date:
            params["returnDate"] = return_date
        if airlines:
            iata_codes = resolve_airline_codes(airlines)
            if iata_codes:
                params["includedAirlineCodes"] = iata_codes

        resp = self._get(_SEARCH_PATH, params)
        return self._parse_offers(resp, origin, destination)

    def cheapest_date_range(
        self,
        origin: str,
        destination: str,
        days_ahead: int = 14,
    ) -> list[dict]:
        """
        Search the cheapest price across the next *days_ahead* days.
        Returns a list sorted by price ascending.
        """
        origin      = ICAO_TO_IATA.get(origin.upper(), origin.upper())
        destination = ICAO_TO_IATA.get(destination.upper(), destination.upper())

        results: list[dict] = []
        today = date.today()
        for i in range(days_ahead):
            d = (today + timedelta(days=i + 1)).isoformat()
            try:
                offers = self.search_flights(origin, destination, d, max_results=3)
                results.extend(offers)
            except Exception as exc:
                logger.debug("Amadeus skip %s: %s", d, exc)
        return sorted(results, key=lambda x: x["price_php"])

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _ensure_token(self) -> None:
        if time.time() < self._token_exp - 60:
            return
        resp = requests.post(
            f"{self._base}{_TOKEN_PATH}",
            data={
                "grant_type":    "client_credentials",
                "client_id":     self._id,
                "client_secret": self._secret,
            },
            timeout=10,
        )
        if resp.status_code == 401:
            raise AmadeusAuthError("Invalid Amadeus credentials. Check client_id / client_secret.")
        resp.raise_for_status()
        data = resp.json()
        self._token     = data["access_token"]
        self._token_exp = time.time() + data.get("expires_in", 1799)
        self._session.headers["Authorization"] = f"Bearer {self._token}"

    def _get(self, path: str, params: dict) -> dict:
        resp = self._session.get(f"{self._base}{path}", params=params, timeout=_TIMEOUT)
        if resp.status_code == 401:
            self._token_exp = 0
            self._ensure_token()
            resp = self._session.get(f"{self._base}{path}", params=params, timeout=_TIMEOUT)
        if resp.status_code == 400:
            errors = resp.json().get("errors", [])
            detail = errors[0].get("detail", resp.text) if errors else resp.text
            raise AmadeusError(f"Bad request: {detail}")
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _parse_offers(data: dict, origin: str, destination: str) -> list[dict]:
        results = []
        dictionaries = data.get("dictionaries", {})
        carrier_names = dictionaries.get("carriers", {})

        for offer in data.get("data", []):
            itineraries = offer.get("itineraries", [])
            if not itineraries:
                continue
            segments = itineraries[0].get("segments", [])
            if not segments:
                continue

            first = segments[0]
            last  = segments[-1]
            price = offer.get("price", {})
            code  = first.get("carrierCode", "")

            results.append({
                "airline_code":      code,
                "airline_name":      carrier_names.get(code) or AIRLINE_NAMES.get(code, code),
                "flight_number":     code + first.get("number", ""),
                "departure_airport": first["departure"]["iataCode"],
                "arrival_airport":   last["arrival"]["iataCode"],
                "departure_time":    first["departure"].get("at", ""),
                "arrival_time":      last["arrival"].get("at", ""),
                "stops":             len(segments) - 1,
                "duration":          itineraries[0].get("duration", ""),
                "price_php":         float(price.get("total", 0)),
                "currency":          price.get("currency", "PHP"),
                "seats_left":        offer.get("numberOfBookableSeats"),
                "source":            "Google Flights / Amadeus",
            })
        return sorted(results, key=lambda x: x["price_php"])
