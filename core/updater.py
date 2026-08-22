"""
Auto-update system.

Version check flow:
  • On startup — check immediately
  • Every update_check_interval_hours — check in background (app keeps running)
  • On demand — check_now()

When a newer version is found on GitHub, on_update_available fires.
The UI then lets the user confirm, and download_and_apply() does the rest:
  1. Downloads the latest source zip from GitHub
  2. Extracts it and copies new files over the current install
     (user_config.json and data/ are never touched)
  3. Restarts the app automatically
"""
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests
from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)

LOCAL_VERSION_FILE = Path(__file__).parent.parent / "version.json"
GITHUB_RAW      = "https://raw.githubusercontent.com/{owner}/{repo}/main/version.json"
GITHUB_ZIP      = "https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"
GITHUB_RELEASES = "https://github.com/{owner}/{repo}/releases/latest"
CHECK_TIMEOUT   = 10
DOWNLOAD_TIMEOUT = 120

# Files / dirs that must never be overwritten during an update
PROTECTED = {
    "config/user_config.json",
    "data",
    ".git",
}


class AutoUpdater:
    def __init__(
        self,
        owner: str,
        repo: str,
        token: str = "",
        check_interval_hours: int = 2,
    ) -> None:
        self._owner    = owner
        self._repo     = repo
        self._interval = check_interval_hours * 3600
        self._stop     = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._current  = self._read_local_version()
        self._latest: str = ""
        self._headers  = self._build_headers(token)

        # Fired on the calling thread (always dispatched to main via root.after)
        self.on_update_available: Optional[Callable[[str, str], None]] = None

    @staticmethod
    def _build_headers(token: str) -> dict:
        h = {"Accept": "application/vnd.github+json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

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
        threading.Thread(target=self._check, daemon=True, name="UpdateCheckOnce").start()

    # ------------------------------------------------------------------ #
    # Update application                                                   #
    # ------------------------------------------------------------------ #

    def download_and_apply(
        self,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Download the latest source zip from GitHub, replace current files,
        and restart the application.  Call this from a background thread.

        on_progress(message) is called with status strings so the UI can
        show progress. Raises on failure so the UI can catch and display.
        """
        def progress(msg: str) -> None:
            logger.info(msg)
            if on_progress:
                on_progress(msg)

        app_dir = Path(__file__).parent.parent
        zip_url = GITHUB_ZIP.format(owner=self._owner, repo=self._repo)

        progress("Connecting to GitHub…")
        with tempfile.TemporaryDirectory() as tmp:
            # ── Download ────────────────────────────────────────────────
            zip_path = Path(tmp) / "update.zip"
            with requests.get(zip_url, stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=32_768):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded / total * 100)
                            progress(f"Downloading… {pct}%")

            # ── Extract ─────────────────────────────────────────────────
            progress("Extracting…")
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp)

            # GitHub names the extracted folder  "<repo>-main"
            extracted_dirs = [
                Path(tmp) / d for d in os.listdir(tmp)
                if (Path(tmp) / d).is_dir() and d != "__MACOSX"
            ]
            if not extracted_dirs:
                raise RuntimeError("Could not find extracted folder in zip.")
            src_root = extracted_dirs[0]

            # ── Copy files ──────────────────────────────────────────────
            progress("Installing…")
            for src in src_root.rglob("*"):
                if not src.is_file():
                    continue
                rel = src.relative_to(src_root)
                rel_str = rel.as_posix()

                # Never touch protected paths
                if any(rel_str == p or rel_str.startswith(p + "/") for p in PROTECTED):
                    continue

                dst = app_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        # ── Restart ─────────────────────────────────────────────────────
        progress("Restarting…")
        _restart_app()

    @property
    def latest_version(self) -> str:
        return self._latest

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        self._check()
        while not self._stop.wait(self._interval):
            self._check()

    def _check(self) -> None:
        try:
            latest = self._fetch_remote_version()
            if latest and self._is_newer(latest):
                self._latest = latest
                logger.info("Update available: %s → %s", self._current, latest)
                if self.on_update_available:
                    self.on_update_available(self._current, latest)
        except Exception as exc:
            logger.debug("Update check failed: %s", exc)

    def _fetch_remote_version(self) -> str:
        url = GITHUB_RAW.format(owner=self._owner, repo=self._repo)
        resp = requests.get(url, timeout=CHECK_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("version", "0.0.0")

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


# ------------------------------------------------------------------ #
# Restart helper                                                       #
# ------------------------------------------------------------------ #

def _restart_app() -> None:
    """
    Restart the current process.
    Works for both  `python main.py`  and  a PyInstaller .exe.
    """
    exe = sys.executable

    if getattr(sys, "frozen", False):
        # Running as a compiled .exe — launch the exe itself and exit
        os.execv(exe, [exe])
    else:
        # Running as Python source
        os.execv(exe, [exe] + sys.argv)
