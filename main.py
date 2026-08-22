"""
PhilFlight Tracker — entry point.
"""
import logging
import os
import sys

# Ensure the project root is always on the Python path, regardless of how
# the script is invoked (python main.py, double-click, PyInstaller exe, …).
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

from config.settings import Settings  # noqa: E402
from ui.app import FlightTrackerApp   # noqa: E402


def main() -> None:
    # Generate the icon on first run if it is missing.
    icon_path = os.path.join(ROOT, "assets", "icon.ico")
    if not os.path.exists(icon_path):
        try:
            from assets.create_icon import generate
            from pathlib import Path
            generate(Path(ROOT) / "assets")
        except Exception as exc:
            logging.warning("Could not generate icon: %s", exc)

    settings = Settings()
    app = FlightTrackerApp(settings)
    app.run()


if __name__ == "__main__":
    main()
