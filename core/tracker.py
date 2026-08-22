import logging
import threading
from datetime import datetime
from typing import Callable, List, Optional

from api.opensky import OpenSkyClient, NetworkError, OpenSkyError, RateLimitError
from config.settings import Settings

logger = logging.getLogger(__name__)


class FlightTracker:
    """
    Polls OpenSky on a configurable interval in a background thread.
    Calls on_update(flights, timestamp) when new data arrives.
    Calls on_error(message) on recoverable failures.
    """

    def __init__(self, client: OpenSkyClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._stop = threading.Event()
        self._wake = threading.Event()  # set to force an early refresh
        self._thread: Optional[threading.Thread] = None

        self.on_update: Optional[Callable[[List[dict], datetime], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="FlightTracker"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def restart(self) -> None:
        self.stop()
        if self._thread:
            self._thread.join(timeout=5)
        self.start()

    def trigger_refresh(self) -> None:
        """Wake the polling loop immediately without waiting for the interval."""
        self._wake.set()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        while not self._stop.is_set():
            self._fetch_and_notify()
            interval = self._settings.get("poll_interval_minutes", 30) * 60
            # Block until the interval elapses or a manual refresh is requested.
            self._wake.wait(timeout=interval)
            self._wake.clear()

    def _fetch_and_notify(self) -> None:
        dep = self._settings.get("departure_airport", "RPLL")
        arr = self._settings.get("arrival_airport", "")
        airline = self._settings.get("airline_filter", "")

        try:
            if dep:
                flights = self._client.get_routes_from_to(
                    dep, arr, hours_back=2, airline_prefix=airline
                )
            else:
                # No departure filter: show all live Philippine airspace traffic.
                states = self._client.get_live_states()
                flights = [
                    s for s in states
                    if not airline
                    or s.get("callsign", "").upper().startswith(airline.upper())
                ]

            if self.on_update:
                self.on_update(flights, datetime.now())

        except RateLimitError:
            logger.warning("OpenSky rate limit hit")
            if self.on_error:
                self.on_error("Rate limit exceeded — will retry next interval.")
        except NetworkError as exc:
            logger.warning("Network error: %s", exc)
            if self.on_error:
                self.on_error(f"Network error: {exc}")
        except OpenSkyError as exc:
            logger.error("OpenSky error: %s", exc)
            if self.on_error:
                self.on_error(str(exc))
        except Exception:
            logger.exception("Unexpected tracker error")
            if self.on_error:
                self.on_error("Unexpected error. Check the log.")
