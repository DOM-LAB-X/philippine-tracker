import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).parent
DEFAULT_CONFIG_PATH = CONFIG_DIR / "default_config.json"
USER_CONFIG_PATH = CONFIG_DIR / "user_config.json"

PHILIPPINE_AIRPORTS: dict[str, str] = {
    "RPLL": "Manila — Ninoy Aquino Intl",
    "RPVM": "Cebu — Mactan Intl",
    "RPMD": "Davao — Francisco Bangoy Intl",
    "RPLC": "Clark International",
    "RPVD": "Dumaguete — Sibulan",
    "RPUI": "General Santos Intl",
    "RPVI": "Iloilo International",
    "RPUB": "Bacolod-Silay",
    "RPVK": "Kalibo International",
    "RPSP": "Puerto Princesa Intl",
    "RPUZ": "Zamboanga International",
    "RPVB": "Bohol–Panglao International",
}

PHILIPPINE_AIRLINES: dict[str, str] = {
    "PAL": "Philippine Airlines",
    "CEB": "Cebu Pacific",
    "APG": "AirAsia Philippines",
    "SEJ": "SkyJet Airlines",
    "MYP": "PAL Express",
}


class Settings:
    def __init__(self) -> None:
        self._defaults: dict = {}
        self._user: dict = {}
        self._load()

    def _load(self) -> None:
        with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
            self._defaults = json.load(f)

        if USER_CONFIG_PATH.exists():
            try:
                with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._user = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._user = {}

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._user:
            return self._user[key]
        return self._defaults.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._user[key] = value

    def save(self) -> None:
        USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._user, f, indent=2)

    @staticmethod
    def validate_icao_airport(code: str) -> bool:
        return bool(code) and len(code) == 4 and code.isalpha() and code.isupper()

    @staticmethod
    def validate_airline_icao(code: str) -> bool:
        return bool(code) and 2 <= len(code) <= 4 and code.isalnum() and code.isupper()
