"""
Auto-update checker.

Reads version.json from the configured GitHub repo (raw content) and compares
it against the local version.json.  Runs in a background thread and fires
on_update_available(current, latest, release_url) when a newer version exists.

Checking happens:
  • Immediately on start()
  • Every update_check_interval_hours thereafter
  • On demand via check_now()
"""
import json
import logging
import threading
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests
from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)

LOCAL_VERSION_FILE = Path(__file__).parent.parent / "version.json"
GITHUB_RAW = "https://raw.githubusercontent.com/{owner}/{repo}/main/version.json"
GITHUB_RELEASES = "https://github.com/{owner}/{repo}/releases/latest"
TIMEOUT = 10


class AutoUpdater:
    def __init__(
        self,
        owner: str,
        repo: str,
        check_interval_hours: int = 2,
    ) -> None:
        self._owner = owner
        self._repo = repo
        self._interval = check_interval_hours * 3600
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._current = self._read_local_version()

        self.on_update_available: Optional[Callable[[str, str, str], None]] = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="AutoUpdater"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def check_now(self) -> None:
        """Fire a one-shot check outside of the normal interval."""
        threading.Thread(
            target=self._check, daemon=True, name="UpdateCheckOnce"
        ).start()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        self._check()
        while not self._stop.wait(self._interval):
            self._check()

    def _check(self) -> None:
        try:
            latest, release_url = self._fetch_remote_version()
            if latest and self._is_newer(latest):
                logger.info("Update available: %s → %s", self._current, latest)
                if self.on_update_available:
                    self.on_update_available(self._current, latest, release_url)
        except Exception as exc:
            logger.debug("Update check failed: %s", exc)

    def _fetch_remote_version(self) -> Tuple[str, str]:
        url = GITHUB_RAW.format(owner=self._owner, repo=self._repo)
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        version = data.get("version", "0.0.0")
        release_url = GITHUB_RELEASES.format(owner=self._owner, repo=self._repo)
        return version, release_url

    def _is_newer(self, remote: str) -> bool:
        try:
            return Version(remote) > Version(self._current)
        except InvalidVersion:
            return False

    @staticmethod
    def _read_local_version() -> str:
        try:
            with open(LOCAL_VERSION_FILE, encoding="utf-8") as f:
                return json.load(f).get("version", "0.0.0")
        except Exception:
            return "0.0.0"
