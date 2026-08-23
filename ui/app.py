"""
PhilFlight Tracker — redesigned UI
Sidebar navigation · Flight cards · 12-hour time · Airport autocomplete
Discord in-app setup · Round-trip date picker · Auto-update banner
"""
import json
import logging
import threading
import tkinter as tk
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox
from typing import List, Optional

import customtkinter as ctk

from config.settings import Settings
from core.deal_monitor import DealMonitor
from core.price_tracker import PriceTracker
from core.tracker import FlightTracker
from core.updater import AutoUpdater
from ui.widgets import AirportEntry, fmt_datetime, fmt_time, iata_to_icao

logger = logging.getLogger(__name__)

ASSETS       = Path(__file__).parent.parent / "assets"
VERSION_FILE = Path(__file__).parent.parent / "version.json"

# ── Palette ─────────────────────────────────────────────────────────────────
BG        = "#0d1117"
SIDEBAR   = "#161b22"
CARD      = "#21262d"
CARD_ALT  = "#1c2128"
BORDER    = "#30363d"
BLUE      = "#1a6ef5"        # bright accent on dark bg
GOLD      = "#FCD116"
TEXT      = "#e6edf3"
SUBTEXT   = "#8b949e"
GREEN     = "#3fb950"
RED       = "#f85149"
ORANGE    = "#d29922"
PURPLE    = "#bc8cff"

NAV_ITEMS = [
    ("✈",  "flights",  "Flights"),
    ("🎫", "deals",    "Deals & Promos"),
    ("💰", "prices",   "Prices"),
    ("🔔", "discord",  "Discord"),
    ("⚙",  "settings", "Settings"),
]


def _card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=10, **kw)


def _label(parent, text, size=12, weight="normal", color=TEXT, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=size, weight=weight),
        text_color=color, **kw
    )


class FlightTrackerApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tracker:       Optional[FlightTracker]  = None
        self._updater:       Optional[AutoUpdater]     = None
        self._deal_monitor:  Optional[DealMonitor]     = None
        self._price_tracker: Optional[PriceTracker]    = None
        self._root:          Optional[ctk.CTk]         = None
        self._countdown_job: Optional[str]             = None
        self._next_update:   Optional[datetime]        = None
        self._pending_url:   str                       = ""
        self._sections:      dict                      = {}
        self._nav_btns:      dict                      = {}

    # ──────────────────────────────────────────── startup ────────────────────

    def run(self) -> None:
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        self._root = ctk.CTk()
        self._root.title("PhilFlight Tracker")
        self._root.geometry("1280x780")
        self._root.minsize(900, 580)
        self._root.configure(fg_color=BG)

        self._set_icon()
        self._build_ui()
        self._show_section("flights")
        self._start_tracker()
        self._start_updater()
        self._start_deal_monitor()
        self._start_price_tracker()

        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.mainloop()

    def _set_icon(self) -> None:
        for path, fn in [
            (ASSETS / "icon.ico", lambda p: self._root.iconbitmap(str(p))),
            (ASSETS / "icon.png", lambda p: self._root.iconphoto(True, tk.PhotoImage(file=str(p)))),
        ]:
            if path.exists():
                try:
                    fn(path)
                    return
                except Exception:
                    pass

    # ──────────────────────────────────────────── UI build ───────────────────

    def _build_ui(self) -> None:
        self._root.grid_columnconfigure(1, weight=1)
        self._root.grid_rowconfigure(1, weight=1)

        # Update notification banner (row 0, spans both columns)
        self._notif_area = ctk.CTkFrame(self._root, fg_color="transparent", height=0)
        self._notif_area.grid(row=0, column=0, columnspan=2, sticky="ew")

        # Sidebar (row 1, col 0)
        self._build_sidebar()

        # Main area (row 1, col 1)
        main = ctk.CTkFrame(self._root, fg_color=BG, corner_radius=0)
        main.grid(row=1, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # Top bar inside main
        self._build_topbar(main)

        # Content container
        content = ctk.CTkFrame(main, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 16))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        # Build each section (only one visible at a time)
        for key, builder in [
            ("flights",  self._build_flights_section),
            ("deals",    self._build_deals_section),
            ("prices",   self._build_prices_section),
            ("discord",  self._build_discord_section),
            ("settings", self._build_settings_section),
        ]:
            frame = ctk.CTkFrame(content, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_rowconfigure(0, weight=1)
            frame.grid_columnconfigure(0, weight=1)
            builder(frame)
            self._sections[key] = frame

    # ── Sidebar ──────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> None:
        sb = ctk.CTkFrame(self._root, fg_color=SIDEBAR, corner_radius=0, width=72)
        sb.grid(row=1, column=0, sticky="ns")
        sb.grid_propagate(False)

        # App logo / icon at top
        logo_frame = ctk.CTkFrame(sb, fg_color="#0038A8", corner_radius=12, width=44, height=44)
        logo_frame.pack(pady=(20, 24))
        logo_frame.pack_propagate(False)
        ctk.CTkLabel(logo_frame, text="✈", font=ctk.CTkFont(size=22), text_color="white").place(relx=0.5, rely=0.5, anchor="center")

        for icon, key, _tooltip in NAV_ITEMS:
            btn = ctk.CTkButton(
                sb,
                text=icon,
                width=48, height=48,
                corner_radius=10,
                font=ctk.CTkFont(size=20),
                fg_color="transparent",
                hover_color=BORDER,
                text_color=SUBTEXT,
                command=lambda k=key: self._show_section(k),
            )
            btn.pack(pady=4)
            self._nav_btns[key] = btn

        # Version at bottom
        try:
            with open(VERSION_FILE) as f:
                ver = json.load(f).get("version", "?")
        except Exception:
            ver = "?"
        ctk.CTkLabel(sb, text=f"v{ver}", font=ctk.CTkFont(size=10),
                     text_color=BORDER).pack(side="bottom", pady=12)

    def _show_section(self, key: str) -> None:
        for _k, frame in self._sections.items():
            frame.grid_remove()
        self._sections[key].grid()

        for k, btn in self._nav_btns.items():
            btn.configure(
                fg_color=BLUE if k == key else "transparent",
                text_color=TEXT if k == key else SUBTEXT,
            )

    # ── Top bar ──────────────────────────────────────────────────────────────

    def _build_topbar(self, parent) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent", height=52)
        bar.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        bar.grid_propagate(False)

        _label(bar, "PhilFlight Tracker", size=18, weight="bold").pack(side="left")

        # Status pills (right side)
        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right")

        self._pill_api = self._pill(right, "● Connecting", ORANGE)
        self._pill_api.pack(side="right", padx=4)

        self._lbl_next = ctk.CTkLabel(
            right, text="", font=ctk.CTkFont(size=11), text_color=SUBTEXT
        )
        self._lbl_next.pack(side="right", padx=8)

        self._lbl_last = ctk.CTkLabel(
            right, text="", font=ctk.CTkFont(size=11), text_color=SUBTEXT
        )
        self._lbl_last.pack(side="right", padx=4)

    @staticmethod
    def _pill(parent, text: str, color: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=color,
        )

    # ──────────────────────────────────────── FLIGHTS section ────────────────

    def _build_flights_section(self, parent) -> None:
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Search bar
        search = _card(parent)
        search.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._build_flight_search(search)

        # Results area
        results_wrap = ctk.CTkFrame(parent, fg_color="transparent")
        results_wrap.grid(row=1, column=0, sticky="nsew")
        results_wrap.grid_rowconfigure(0, weight=1)
        results_wrap.grid_columnconfigure(0, weight=1)

        self._flights_scroll = ctk.CTkScrollableFrame(results_wrap, fg_color="transparent")
        self._flights_scroll.grid(row=0, column=0, sticky="nsew")
        self._flights_scroll.grid_columnconfigure(0, weight=1)

        self._flights_empty = _label(
            self._flights_scroll,
            "No flights found yet.\nClick Search or wait for automatic refresh.",
            size=13, color=SUBTEXT,
        )
        self._flights_empty.grid(row=0, column=0, pady=60)
        self._flight_count_lbl = _label(self._flights_scroll, "", size=11, color=SUBTEXT)

    def _build_flight_search(self, parent) -> None:
        row1 = ctk.CTkFrame(parent, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(14, 6))

        # From
        _label(row1, "From", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._dep_entry = AirportEntry(row1, placeholder="City or code", width=200)
        self._dep_entry.set(self.settings.get("departure_airport", "MNL"))
        self._dep_entry.pack(side="left", padx=(0, 20))

        # To
        _label(row1, "To", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._arr_entry = AirportEntry(row1, placeholder="City or code (optional)", width=200)
        self._arr_entry.set(self.settings.get("arrival_airport", ""))
        self._arr_entry.pack(side="left", padx=(0, 20))

        # Airline
        _label(row1, "Airline", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._airline_var = tk.StringVar(value=self.settings.get("airline_filter", ""))
        ctk.CTkEntry(row1, textvariable=self._airline_var,
                     placeholder_text="PAL, CEB… (optional)", width=160).pack(side="left", padx=(0, 20))

        # Search button
        ctk.CTkButton(
            row1, text="Search", width=100, height=34,
            fg_color=BLUE, hover_color="#1558c0",
            command=self._manual_refresh,
        ).pack(side="left")

        self._search_count = _label(row1, "", size=11, color=SUBTEXT)
        self._search_count.pack(side="right", padx=8)

        # Row 2: dates
        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(0, 14))

        _label(row2, "Depart", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._depart_var = tk.StringVar(value=self.settings.get("depart_date", ""))
        ctk.CTkEntry(row2, textvariable=self._depart_var,
                     placeholder_text="Aug 22, 2026", width=150).pack(side="left", padx=(0, 20))

        _label(row2, "Return", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._return_var = tk.StringVar(value=self.settings.get("return_date", ""))
        ctk.CTkEntry(row2, textvariable=self._return_var,
                     placeholder_text="Aug 29, 2026 (optional)", width=170).pack(side="left", padx=(0, 20))

        _label(row2, "Trip type:", size=11, color=SUBTEXT).pack(side="left", padx=(0, 6))
        self._trip_type = tk.StringVar(value=self.settings.get("trip_type", "One-way"))
        ctk.CTkSegmentedButton(
            row2, values=["One-way", "Round trip"],
            variable=self._trip_type, width=200, height=28,
        ).pack(side="left")

    # ──────────────────────────────────────── DEALS section ──────────────────

    def _build_deals_section(self, parent) -> None:
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        _label(hdr, "Deals & Promos", size=16, weight="bold").pack(side="left")
        ctk.CTkButton(hdr, text="Scan Now", width=100, height=32,
                      fg_color=BLUE, command=self._manual_deal_check).pack(side="right")
        _label(hdr, "Scans Reddit + airline promo pages every hour", size=11, color=SUBTEXT).pack(side="right", padx=12)

        self._deals_scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self._deals_scroll.grid(row=1, column=0, sticky="nsew")
        self._deals_scroll.grid_columnconfigure(0, weight=1)

        self._deals_empty = _label(
            self._deals_scroll,
            "No deals found yet.\nClick 'Scan Now' or wait for the next automatic scan.",
            size=13, color=SUBTEXT,
        )
        self._deals_empty.grid(row=0, column=0, pady=60)

    # ──────────────────────────────────────── PRICES section ─────────────────

    def _build_prices_section(self, parent) -> None:
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Add-route card
        add_card = _card(parent)
        add_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        hdr = ctk.CTkFrame(add_card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 6))
        _label(hdr, "Track a Price Route", size=14, weight="bold").pack(side="left")
        _label(hdr, "Powered by Google Flights / Amadeus", size=11, color=SUBTEXT).pack(side="right")

        fields = ctk.CTkFrame(add_card, fg_color="transparent")
        fields.pack(fill="x", padx=16, pady=(0, 14))

        _label(fields, "From", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._price_from = AirportEntry(fields, placeholder="MNL", width=160)
        self._price_from.set("MNL")
        self._price_from.pack(side="left", padx=(0, 16))

        _label(fields, "To", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._price_to = AirportEntry(fields, placeholder="CEB", width=160)
        self._price_to.pack(side="left", padx=(0, 16))

        _label(fields, "Depart", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._price_depart_var = tk.StringVar()
        ctk.CTkEntry(fields, textvariable=self._price_depart_var,
                     placeholder_text="YYYY-MM-DD", width=130).pack(side="left", padx=(0, 16))

        _label(fields, "Return", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._price_return_var = tk.StringVar()
        ctk.CTkEntry(fields, textvariable=self._price_return_var,
                     placeholder_text="YYYY-MM-DD (optional)", width=160).pack(side="left", padx=(0, 16))

        ctk.CTkButton(fields, text="Watch Route", width=110, height=32,
                      fg_color=BLUE, command=self._add_watched_route).pack(side="left", padx=(0, 8))
        ctk.CTkButton(fields, text="Check Now", width=100, height=32,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      command=self._manual_price_check).pack(side="left")

        self._prices_scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self._prices_scroll.grid(row=1, column=0, sticky="nsew")
        self._prices_scroll.grid_columnconfigure(0, weight=1)

        self._prices_empty = _label(
            self._prices_scroll,
            "No prices yet.\n\n"
            "1. Add your Amadeus API keys in  ⚙ Settings\n"
            "2. Enter a route above and click 'Watch Route'\n"
            "3. Click 'Check Now' or wait for the next automatic refresh",
            size=13, color=SUBTEXT, justify="center",
        )
        self._prices_empty.grid(row=0, column=0, pady=60)

    # ──────────────────────────────────────── DISCORD section ────────────────

    def _build_discord_section(self, parent) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        center = ctk.CTkFrame(parent, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Discord branding card
        card = _card(center, width=560)
        card.pack(pady=20)
        card.pack_propagate(False)

        # Header
        hdr = ctk.CTkFrame(card, fg_color="#5865F2", corner_radius=0,
                           height=72, width=560)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        _label(hdr, "🔔  Discord Notifications", size=16, weight="bold",
               color="white").place(relx=0.5, rely=0.5, anchor="center")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=24, pady=20)

        _label(body,
               "Get notified in Discord when:\n"
               "  • New flights match your route\n"
               "  • A promo or deal is posted\n"
               "  • A price drops below your threshold",
               size=12, color=TEXT, justify="left").pack(anchor="w", pady=(0, 20))

        # How to get webhook
        steps = ctk.CTkFrame(body, fg_color=CARD_ALT, corner_radius=8)
        steps.pack(fill="x", pady=(0, 16))
        _label(steps, "How to get your webhook URL:", size=12, weight="bold",
               color=SUBTEXT).pack(anchor="w", padx=12, pady=(10, 4))
        for i, step in enumerate([
            "Open Discord → your server → Server Settings",
            "Go to Integrations → Webhooks → New Webhook",
            "Pick a channel, name it, click 'Copy Webhook URL'",
            "Paste it below and click Save",
        ], 1):
            _label(steps, f"  {i}.  {step}", size=11, color=SUBTEXT).pack(anchor="w", padx=12, pady=1)
        ctk.CTkFrame(steps, fg_color="transparent", height=8).pack()

        # Webhook URL input
        _label(body, "Webhook URL", size=12, color=SUBTEXT).pack(anchor="w")
        self._discord_url_var = tk.StringVar(value=self.settings.get("discord_webhook", ""))
        url_row = ctk.CTkFrame(body, fg_color="transparent")
        url_row.pack(fill="x", pady=(4, 12))
        ctk.CTkEntry(url_row, textvariable=self._discord_url_var,
                     placeholder_text="https://discord.com/api/webhooks/…",
                     show="").pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Notification toggles
        tog = ctk.CTkFrame(body, fg_color="transparent")
        tog.pack(fill="x", pady=(0, 16))
        self._tog_flights = tk.BooleanVar(value=self.settings.get("discord_notify_flights", True))
        self._tog_deals   = tk.BooleanVar(value=self.settings.get("discord_notify_deals", True))
        self._tog_prices  = tk.BooleanVar(value=self.settings.get("discord_notify_price_drops", True))
        for var, text in [
            (self._tog_flights, "Flight updates"),
            (self._tog_deals,   "New deals & promos"),
            (self._tog_prices,  "Price drops"),
        ]:
            ctk.CTkCheckBox(tog, text=text, variable=var,
                            font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 20))

        # Buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(btn_row, text="Test Connection", width=140, height=36,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      command=self._test_discord).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Save", width=100, height=36,
                      fg_color=BLUE, command=self._save_discord).pack(side="left")

        self._discord_status = _label(btn_row, "", size=11, color=GREEN)
        self._discord_status.pack(side="left", padx=12)

    # ──────────────────────────────────────── SETTINGS section ───────────────

    def _build_settings_section(self, parent) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        def section(label):
            f = ctk.CTkFrame(scroll, fg_color="transparent")
            f.grid(sticky="ew", pady=(20, 4), columnspan=2, padx=4)
            scroll.grid_columnconfigure(0, weight=1)
            _label(f, label, size=13, weight="bold", color=SUBTEXT).pack(anchor="w")
            sep = ctk.CTkFrame(scroll, fg_color=BORDER, height=1)
            sep.grid(sticky="ew", columnspan=2, padx=4, pady=(0, 8))

        def field(label, key, show="", row=None, col=0):
            wrap = ctk.CTkFrame(scroll, fg_color="transparent")
            wrap.grid(row=row, column=col, sticky="ew", padx=(4 + col*8, 4), pady=3)
            _label(wrap, label, size=11, color=SUBTEXT).pack(anchor="w")
            var = tk.StringVar(value=str(self.settings.get(key, "")))
            ctk.CTkEntry(wrap, textvariable=var, show=show).pack(fill="x")
            self._sfields[key] = var

        self._sfields: dict[str, tk.StringVar] = {}
        r = [0]
        def next_row():
            r[0] += 1
            return r[0]

        section("Polling intervals")
        nr = next_row()
        field("Flight check every (minutes)", "poll_interval_minutes", row=nr, col=0)
        field("Deal scan every (minutes)",    "deal_check_interval_minutes", row=nr, col=1)

        section("Appearance")
        nr = next_row()
        theme_wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        theme_wrap.grid(row=nr, column=0, columnspan=2, sticky="w", padx=4, pady=3)
        _label(theme_wrap, "Theme", size=11, color=SUBTEXT).pack(anchor="w")
        self._theme_var = tk.StringVar(value=self.settings.get("theme", "dark"))
        ctk.CTkSegmentedButton(theme_wrap, values=["dark", "light", "system"],
                               variable=self._theme_var, width=260).pack(anchor="w")

        section("Google Flights / Amadeus (free at developers.amadeus.com)")
        nr = next_row()
        field("Client ID",     "amadeus_client_id",     row=nr, col=0)
        field("Client Secret", "amadeus_client_secret", row=nr, col=1, show="*")
        nr = next_row()
        env_wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        env_wrap.grid(row=nr, column=0, sticky="ew", padx=4, pady=3)
        _label(env_wrap, "Environment", size=11, color=SUBTEXT).pack(anchor="w")
        self._amadeus_env = tk.StringVar(value=self.settings.get("amadeus_environment", "test"))
        ctk.CTkSegmentedButton(env_wrap, values=["test", "production"],
                               variable=self._amadeus_env, width=200).pack(anchor="w")
        drop_wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        drop_wrap.grid(row=nr, column=1, sticky="ew", padx=4, pady=3)
        _label(drop_wrap, "Price drop alert threshold (%)", size=11, color=SUBTEXT).pack(anchor="w")
        self._sfields["price_drop_threshold_pct"] = tk.StringVar(
            value=str(self.settings.get("price_drop_threshold_pct", 10)))
        ctk.CTkEntry(drop_wrap, textvariable=self._sfields["price_drop_threshold_pct"],
                     width=80).pack(anchor="w")

        section("OpenSky credentials (optional — more rate limit headroom)")
        nr = next_row()
        field("Username", "opensky_username", row=nr, col=0)
        field("Password", "opensky_password", row=nr, col=1, show="*")

        section("GitHub auto-update")
        nr = next_row()
        field("Owner",     "github_owner", row=nr, col=0)
        field("Repo name", "github_repo",  row=nr, col=1)

        nr = next_row()
        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.grid(row=nr, column=0, columnspan=2, sticky="w", padx=4, pady=(20, 8))
        ctk.CTkButton(btn_row, text="Save Settings", width=140, height=36,
                      fg_color=BLUE, command=self._save_settings).pack(side="left")
        self._settings_status = _label(btn_row, "", size=11, color=GREEN)
        self._settings_status.pack(side="left", padx=12)

    # ──────────────────────────────────── Background services ─────────────────

    def _start_tracker(self) -> None:
        from api.opensky import OpenSkyClient
        client = OpenSkyClient(
            username=self.settings.get("opensky_username", ""),
            password=self.settings.get("opensky_password", ""),
        )
        self._tracker = FlightTracker(client, self.settings)
        self._tracker.on_update = self._on_flights_updated
        self._tracker.on_error  = self._on_tracker_error
        self._tracker.start()

    def _start_updater(self) -> None:
        owner = self.settings.get("github_owner", "")
        repo  = self.settings.get("github_repo", "")
        if not (owner and repo):
            return
        self._updater = AutoUpdater(
            owner, repo,
            check_interval_hours=int(self.settings.get("update_check_interval_hours", 2)),
        )
        self._updater.on_update_available = self._on_update_available
        self._updater.start()

    def _start_deal_monitor(self) -> None:
        interval = int(self.settings.get("deal_check_interval_minutes", 60))
        self._deal_monitor = DealMonitor(check_interval_minutes=interval)
        self._deal_monitor.on_new_deals = self._on_new_deals
        self._deal_monitor.start()

    def _start_price_tracker(self) -> None:
        from api.amadeus import AmadeusClient
        client = AmadeusClient(
            client_id=self.settings.get("amadeus_client_id", ""),
            client_secret=self.settings.get("amadeus_client_secret", ""),
            production=self.settings.get("amadeus_environment", "test") == "production",
        )
        interval = int(self.settings.get("price_check_interval_minutes", 60))
        self._price_tracker = PriceTracker(client, self.settings, interval)
        self._price_tracker.on_prices_updated = self._on_prices_updated
        self._price_tracker.on_price_drop      = self._on_price_drop
        self._price_tracker.start()

    # ──────────────────────────────────── Callbacks ───────────────────────────

    def _on_flights_updated(self, flights: List[dict], ts: datetime) -> None:
        if self._root:
            self._root.after(0, lambda: self._apply_flights(flights, ts))

    def _on_tracker_error(self, msg: str) -> None:
        if self._root:
            self._root.after(0, lambda: self._show_api_error(msg))

    def _on_new_deals(self, deals: List[dict]) -> None:
        if self._root:
            self._root.after(0, lambda: self._apply_deals(deals))

    def _on_prices_updated(self, offers: List[dict]) -> None:
        if self._root:
            self._root.after(0, lambda: self._apply_prices(offers))

    def _on_price_drop(self, info: dict) -> None:
        if self._root:
            self._root.after(0, lambda: self._handle_price_drop(info))

    def _on_update_available(self, current: str, latest: str) -> None:
        if self._root:
            self._root.after(0, lambda: self._show_update_banner(current, latest))

    # ──────────────────────────────────── UI updates ──────────────────────────

    def _apply_flights(self, flights: List[dict], ts: datetime) -> None:
        # Clear existing cards
        for w in self._flights_scroll.winfo_children():
            if w not in (self._flights_empty, self._flight_count_lbl):
                w.destroy()

        self._pill_api.configure(text="● Live", text_color=GREEN)
        self._lbl_last.configure(text=f"Updated {fmt_time(ts.timestamp())}")

        interval = self.settings.get("poll_interval_minutes", 30) * 60
        self._next_update = ts + timedelta(seconds=interval)
        self._tick_countdown()

        n = len(flights)
        self._search_count.configure(text=f"{n} flight{'s' if n != 1 else ''}")

        if not flights:
            self._flights_empty.grid()
            return
        self._flights_empty.grid_remove()

        for i, f in enumerate(flights):
            self._add_flight_card(self._flights_scroll, f, row=i)

        # Discord
        webhook = self.settings.get("discord_webhook", "")
        if webhook and self.settings.get("discord_notify_flights", True) and flights:
            from notifications.discord import notify_flight_update
            dep = self.settings.get("departure_airport", "")
            arr = self.settings.get("arrival_airport", "")
            threading.Thread(target=notify_flight_update,
                             args=(webhook, flights, dep, arr), daemon=True).start()

    def _add_flight_card(self, parent, f: dict, row: int = 0) -> None:
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=10)
        card.grid(row=row, column=0, sticky="ew", pady=5, padx=2)
        card.grid_columnconfigure(1, weight=1)

        callsign = f.get("callsign") or "—"
        dep_ap   = f.get("departure_airport") or "—"
        arr_ap   = f.get("arrival_airport") or "—"
        dep_t    = fmt_time(f.get("first_seen"))
        arr_t    = fmt_time(f.get("last_seen"))
        on_gnd   = f.get("on_ground")

        if on_gnd is True:
            status, sc = "On Ground", ORANGE
        elif on_gnd is False:
            status, sc = "● Airborne", GREEN
        else:
            status, sc = "—", SUBTEXT

        alt = f.get("baro_altitude_m")
        spd = f.get("velocity_ms")
        alt_s = f"{int(alt * 3.28084):,} ft" if alt else "—"
        spd_s = f"{int(spd * 1.944):,} kts" if spd else "—"

        # Airline colour stripe (left side)
        stripe_color = {"PAL": "#0038A8", "CEB": "#FFCD00", "APG": "#E01A22"}.get(
            callsign[:3], BLUE
        )
        stripe = ctk.CTkFrame(card, fg_color=stripe_color, width=5, corner_radius=0)
        stripe.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 12), pady=0)

        # Top row: callsign + status + time
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(12, 2))
        top.grid_columnconfigure(1, weight=1)
        _label(top, callsign, size=14, weight="bold").grid(row=0, column=0, sticky="w")
        _label(top, status, size=12, color=sc).grid(row=0, column=1, sticky="w", padx=12)
        _label(top, f"{dep_t}  →  {arr_t}", size=12, color=SUBTEXT).grid(row=0, column=2, sticky="e")

        # Bottom row: route + altitude + speed
        bot = ctk.CTkFrame(card, fg_color="transparent")
        bot.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=(0, 12))
        _label(bot, f"{dep_ap}  →  {arr_ap}", size=13, color=TEXT).pack(side="left")
        _label(bot, f"  {alt_s}", size=11, color=SUBTEXT).pack(side="left", padx=12)
        _label(bot, spd_s, size=11, color=SUBTEXT).pack(side="left")

    def _show_api_error(self, msg: str) -> None:
        self._pill_api.configure(text="● Error", text_color=RED)

    def _tick_countdown(self) -> None:
        if self._countdown_job:
            self._root.after_cancel(self._countdown_job)
        if not self._next_update:
            return
        secs = max(0, int((self._next_update - datetime.now()).total_seconds()))
        m, s = divmod(secs, 60)
        self._lbl_next.configure(text=f"Next refresh in {m:02d}:{s:02d}")
        if secs > 0:
            self._countdown_job = self._root.after(1000, self._tick_countdown)

    # ── Deals ────────────────────────────────────────────────────────────────

    def _apply_deals(self, deals: List[dict]) -> None:
        min_score = int(self.settings.get("min_reddit_score", 5))
        new = [d for d in deals
               if d.get("type") != "reddit" or d.get("score", 0) >= min_score]
        if not new:
            return
        self._deals_empty.grid_remove()

        existing = [w for w in self._deals_scroll.winfo_children()
                    if w != self._deals_empty]
        row = len(existing)
        for deal in new:
            self._add_deal_card(deal, row)
            row += 1

        self._show_section("deals")

        webhook = self.settings.get("discord_webhook", "")
        if webhook and self.settings.get("discord_notify_deals", True):
            from notifications.discord import notify_deal
            for d in new:
                threading.Thread(target=notify_deal, args=(webhook, d), daemon=True).start()

    def _add_deal_card(self, deal: dict, row: int) -> None:
        src    = deal.get("source", "")
        title  = deal.get("title", "")[:280]
        url    = deal.get("url", "")
        score  = deal.get("score")

        card = _card(self._deals_scroll)
        card.grid(row=row, column=0, sticky="ew", pady=5, padx=2)
        card.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))

        badge_color = {"Philippine Airlines": "#0038A8", "Cebu Pacific": "#005FAD",
                       "AirAsia PH": "#E01A22"}.get(src, "#4a4e69")
        ctk.CTkLabel(hdr, text=f"  {src}  ",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     fg_color=badge_color, corner_radius=6,
                     text_color="white").pack(side="left")
        if score:
            _label(hdr, f"🔼 {score}", size=11, color=SUBTEXT).pack(side="right")

        _label(card, title, size=12, color=TEXT, wraplength=860, justify="left",
               anchor="w").grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        if url:
            ctk.CTkButton(card, text="Open →", width=80, height=26,
                          fg_color="transparent", border_width=1, border_color=BORDER,
                          command=lambda u=url: webbrowser.open(u)).grid(
                              row=2, column=0, sticky="e", padx=14, pady=(0, 10))

    # ── Prices ───────────────────────────────────────────────────────────────

    def _apply_prices(self, offers: List[dict]) -> None:
        self._prices_empty.grid_remove()
        for w in self._prices_scroll.winfo_children():
            if w != self._prices_empty:
                w.destroy()
        routes: dict = {}
        for o in offers:
            key = f"{o['departure_airport']} → {o['arrival_airport']}  ·  {o.get('departure_time','')[:10]}"
            routes.setdefault(key, []).append(o)
        for i, (label, route_offers) in enumerate(routes.items()):
            self._add_price_section(label, route_offers, i)

    def _add_price_section(self, label: str, offers: list, row: int) -> None:
        card = _card(self._prices_scroll)
        card.grid(row=row, column=0, sticky="ew", pady=6, padx=2)
        card.grid_columnconfigure(0, weight=1)

        _label(card, label, size=13, weight="bold").grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 6))

        for i, o in enumerate(offers[:8]):
            row_f = ctk.CTkFrame(card, fg_color=CARD_ALT if i % 2 else CARD, corner_radius=6)
            row_f.grid(row=i + 1, column=0, sticky="ew", padx=10, pady=2)
            row_f.grid_columnconfigure(1, weight=1)

            airline = o.get("airline_name") or o.get("airline_code", "—")
            stops   = o.get("stops", 0)
            stops_s = "Non-stop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
            dur     = o.get("duration", "").replace("PT","").replace("H","h ").replace("M","m")
            dep_t   = fmt_time(None) # Amadeus returns ISO strings, not unix
            dep_iso = o.get("departure_time","")
            if "T" in dep_iso:
                try:
                    dt = datetime.fromisoformat(dep_iso)
                    h = dt.hour % 12 or 12
                    dep_t = f"{h}:{dt.strftime('%M')} {('AM','PM')[dt.hour >= 12]}"
                except Exception:
                    dep_t = dep_iso[11:16]

            _label(row_f, airline, size=12, weight="bold", anchor="w").grid(
                row=0, column=0, sticky="w", padx=12, pady=8)
            _label(row_f, f"{dep_t}  ·  {stops_s}  ·  {dur}",
                   size=11, color=SUBTEXT).grid(row=0, column=1, sticky="w", padx=4)
            seats = o.get("seats_left")
            if seats:
                _label(row_f, f"{seats} seats", size=11, color=ORANGE).grid(
                    row=0, column=2, sticky="e", padx=12)
            _label(row_f, f"₱{o.get('price_php',0):,.0f}",
                   size=14, weight="bold", color=GREEN).grid(
                       row=0, column=3, sticky="e", padx=16)

        ctk.CTkFrame(card, fg_color="transparent", height=6).grid(
            row=len(offers[:8]) + 1, column=0)

    def _handle_price_drop(self, info: dict) -> None:
        drop_pct = (info["old_price"] - info["new_price"]) / info["old_price"] * 100
        self._show_section("prices")
        messagebox.showinfo("Price Drop!",
                            f"💸 {info['route']}  ({info.get('date','')})\n\n"
                            f"{info.get('airline','')} dropped {drop_pct:.0f}%\n"
                            f"Was ₱{info['old_price']:,.0f}  →  Now ₱{info['new_price']:,.0f}",
                            parent=self._root)
        webhook = self.settings.get("discord_webhook", "")
        if webhook and self.settings.get("discord_notify_price_drops", True):
            from notifications.discord import notify_price_drop
            threading.Thread(
                target=notify_price_drop,
                args=(webhook, info["route"], info["old_price"],
                      info["new_price"], info.get("airline",""), info.get("url","")),
                daemon=True,
            ).start()

    # ── Update banner ─────────────────────────────────────────────────────────

    def _show_update_banner(self, current: str, latest: str) -> None:
        for w in self._notif_area.winfo_children():
            w.destroy()
        banner = ctk.CTkFrame(self._notif_area, fg_color="#1a5c2a", height=36, corner_radius=0)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        _label(banner, f"  Update available: v{current} → v{latest}",
               size=12, color="white").pack(side="left", padx=12, pady=4)
        ctk.CTkButton(banner, text="Update Now", width=100, height=24,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#0d1117",
                      command=lambda: self._confirm_and_update(current, latest)).pack(
                          side="right", padx=8, pady=4)
        ctk.CTkButton(banner, text="✕", width=28, height=24,
                      fg_color="transparent", hover_color="#2a7a3a",
                      command=banner.destroy).pack(side="right", padx=(0, 4), pady=4)

    def _confirm_and_update(self, current: str, latest: str) -> None:
        if not messagebox.askyesno(
            "Install Update",
            f"Update from v{current} to v{latest}?\n\n"
            "The app will download the update and restart automatically.\n"
            "Your settings and data will not be affected.",
            parent=self._root,
        ):
            return
        self._update_progress_dialog(latest)

    def _update_progress_dialog(self, latest: str) -> None:
        dlg = ctk.CTkToplevel(self._root)
        dlg.title("Updating…")
        dlg.geometry("380x150")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)

        _label(dlg, f"Installing v{latest}…", size=14, weight="bold").pack(pady=(22, 8))
        self._upd_lbl = _label(dlg, "Connecting…", size=12, color=SUBTEXT)
        self._upd_lbl.pack()
        bar = ctk.CTkProgressBar(dlg, width=320)
        bar.pack(pady=14)
        bar.configure(mode="indeterminate")
        bar.start()

        def _run():
            try:
                self._updater.download_and_apply(
                    on_progress=lambda m: self._root.after(
                        0, lambda msg=m: self._upd_lbl.configure(text=msg)
                    )
                )
            except Exception as err:
                err_msg = str(err)
                self._root.after(0, lambda m=err_msg: (dlg.destroy(),
                                                        messagebox.showerror("Update failed", m,
                                                                             parent=self._root)))
        threading.Thread(target=_run, daemon=True).start()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _manual_refresh(self) -> None:
        dep     = self._dep_entry.get()
        arr     = self._arr_entry.get()
        airline = self._airline_var.get().strip().upper()

        # Convert IATA → ICAO for OpenSky if needed
        dep_icao = iata_to_icao(dep) if len(dep) == 3 else dep
        arr_icao = iata_to_icao(arr) if len(arr) == 3 else arr

        self.settings.set("departure_airport", dep_icao)
        self.settings.set("arrival_airport",   arr_icao)
        self.settings.set("airline_filter",    airline)
        self.settings.set("depart_date",       self._depart_var.get())
        self.settings.set("return_date",       self._return_var.get())
        self.settings.set("trip_type",         self._trip_type.get())
        if self._tracker:
            self._tracker.trigger_refresh()

    def _add_watched_route(self) -> None:
        frm  = self._price_from.get()
        to   = self._price_to.get()
        dep  = self._price_depart_var.get().strip()
        ret  = self._price_return_var.get().strip()
        if not (frm and to and dep):
            messagebox.showwarning("Missing fields", "Fill in From, To and Depart date.", parent=self._root)
            return
        routes = list(self.settings.get("watched_price_routes", []))
        entry = {"from": frm, "to": to, "date": dep}
        if ret:
            entry["return_date"] = ret
        if entry not in routes:
            routes.append(entry)
            self.settings.set("watched_price_routes", routes)
            self.settings.save()
        if self._price_tracker:
            self._price_tracker.check_now()
        else:
            messagebox.showinfo("Amadeus not configured",
                                "Add your Amadeus API keys in ⚙ Settings.", parent=self._root)

    def _manual_price_check(self) -> None:
        if self._price_tracker:
            self._price_tracker.check_now()
        else:
            messagebox.showinfo("Amadeus not configured",
                                "Add your Amadeus API keys in ⚙ Settings.", parent=self._root)

    def _manual_deal_check(self) -> None:
        if self._deal_monitor:
            self._deal_monitor.check_now()

    def _test_discord(self) -> None:
        url = self._discord_url_var.get().strip()
        if not url:
            self._discord_status.configure(text="Enter a webhook URL first.", text_color=ORANGE)
            return
        from notifications.discord import test_webhook
        ok = test_webhook(url)
        if ok:
            self._discord_status.configure(text="✓ Message sent!", text_color=GREEN)
        else:
            self._discord_status.configure(text="✗ Failed — check the URL.", text_color=RED)

    def _save_discord(self) -> None:
        url = self._discord_url_var.get().strip()
        self.settings.set("discord_webhook",            url)
        self.settings.set("discord_notify_flights",     self._tog_flights.get())
        self.settings.set("discord_notify_deals",       self._tog_deals.get())
        self.settings.set("discord_notify_price_drops", self._tog_prices.get())
        self.settings.save()
        self._discord_status.configure(text="✓ Saved!", text_color=GREEN)

    def _save_settings(self) -> None:
        for key, var in self._sfields.items():
            self.settings.set(key, var.get().strip())
        self.settings.set("theme",            self._theme_var.get())
        self.settings.set("amadeus_environment", self._amadeus_env.get())
        self.settings.save()
        ctk.set_appearance_mode(self._theme_var.get())
        self._settings_status.configure(text="✓ Saved — restart to apply all changes.", text_color=GREEN)

    def _on_close(self) -> None:
        for svc in (self._tracker, self._updater, self._deal_monitor, self._price_tracker):
            if svc:
                svc.stop()
        self._root.destroy()
