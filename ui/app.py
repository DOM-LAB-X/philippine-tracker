"""
PhilFlight Tracker — Price & Deal Monitor
Midnight-purple theme · Calendar date picker · Discord notifications
"""
import json
import logging
import threading
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox
from typing import List, Optional

import customtkinter as ctk

from config.settings import Settings
from core.deal_monitor import DealMonitor
from core.price_tracker import PriceTracker
from core.updater import AutoUpdater
from ui.widgets import AirportEntry, DatePicker, fmt_iso_time, iata_to_icao

logger = logging.getLogger(__name__)

ASSETS       = Path(__file__).parent.parent / "assets"
VERSION_FILE = Path(__file__).parent.parent / "version.json"

# ── Palette ──────────────────────────────────────────────────────────────────
BG       = "#080812"
SIDEBAR  = "#0e0c1c"
CARD     = "#141228"
CARD_ALT = "#1a1835"
BORDER   = "#2d2850"
PURPLE   = "#7c3aed"
LAVENDER = "#a78bfa"
VIOLET   = "#6d28d9"
TEXT     = "#ede9fe"
SUBTEXT  = "#8b7ec8"
GREEN    = "#34d399"
RED      = "#f87171"
ORANGE   = "#fb923c"

NAV = [
    ("💰", "prices",   "Price Tracker"),
    ("🎫", "deals",    "Deals & Promos"),
    ("🔔", "discord",  "Discord"),
    ("⚙",  "settings", "Settings"),
]


def _lbl(parent, text, size=12, weight="normal", color=TEXT, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=size, weight=weight),
        text_color=color, **kw,
    )


def _card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12, **kw)


def _sep(parent, row: int, label: str) -> int:
    """Render a labelled section separator; returns next available row."""
    ctk.CTkFrame(parent, fg_color="transparent", height=12).grid(
        row=row, column=0, columnspan=2)
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.grid(row=row + 1, column=0, columnspan=2, sticky="ew", padx=4, pady=(0, 2))
    _lbl(f, label, size=12, weight="bold", color=SUBTEXT).pack(anchor="w")
    ctk.CTkFrame(parent, fg_color=BORDER, height=1).grid(
        row=row + 2, column=0, columnspan=2, sticky="ew", padx=4, pady=(0, 6))
    return row + 3


class FlightTrackerApp:
    def __init__(self, settings: Settings) -> None:
        self.settings        = settings
        self._updater:       Optional[AutoUpdater]  = None
        self._deal_monitor:  Optional[DealMonitor]  = None
        self._price_tracker: Optional[PriceTracker] = None
        self._root:          Optional[ctk.CTk]      = None
        self._sections:      dict                   = {}
        self._nav_btns:      dict                   = {}
        self._countdown_job: Optional[str]          = None
        self._next_update:   Optional[datetime]     = None

    # ───────────────────────────────────── startup ───────────────────────────

    def run(self) -> None:
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        self._root = ctk.CTk()
        self._root.title("PhilFlight Tracker")
        self._root.geometry("1200x760")
        self._root.minsize(860, 540)
        self._root.configure(fg_color=BG)

        self._set_icon()
        self._build_ui()
        self._show_section("prices")
        self._start_services()

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

    # ───────────────────────────────────── layout ────────────────────────────

    def _build_ui(self) -> None:
        self._root.grid_columnconfigure(1, weight=1)
        self._root.grid_rowconfigure(1, weight=1)

        self._notif_area = ctk.CTkFrame(self._root, fg_color="transparent", height=0)
        self._notif_area.grid(row=0, column=0, columnspan=2, sticky="ew")

        self._build_sidebar()

        main = ctk.CTkFrame(self._root, fg_color=BG, corner_radius=0)
        main.grid(row=1, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)
        self._build_topbar(main)

        content = ctk.CTkFrame(main, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 16))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        for key, builder in [
            ("prices",   self._section_prices),
            ("deals",    self._section_deals),
            ("discord",  self._section_discord),
            ("settings", self._section_settings),
        ]:
            f = ctk.CTkFrame(content, fg_color="transparent")
            f.grid(row=0, column=0, sticky="nsew")
            f.grid_rowconfigure(0, weight=1)
            f.grid_columnconfigure(0, weight=1)
            builder(f)
            self._sections[key] = f

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> None:
        sb = ctk.CTkFrame(self._root, fg_color=SIDEBAR, corner_radius=0, width=72)
        sb.grid(row=1, column=0, sticky="ns")
        sb.grid_propagate(False)

        logo = ctk.CTkFrame(sb, fg_color=PURPLE, corner_radius=14, width=46, height=46)
        logo.pack(pady=(20, 24))
        logo.pack_propagate(False)
        _lbl(logo, "✈", size=22, color="white").place(relx=0.5, rely=0.5, anchor="center")

        for icon, key, _tip in NAV:
            btn = ctk.CTkButton(
                sb, text=icon, width=48, height=48, corner_radius=12,
                font=ctk.CTkFont(size=20),
                fg_color="transparent", hover_color=BORDER, text_color=SUBTEXT,
                command=lambda k=key: self._show_section(k),
            )
            btn.pack(pady=4)
            self._nav_btns[key] = btn

        try:
            ver = json.loads(VERSION_FILE.read_text())["version"]
        except Exception:
            ver = "?"
        _lbl(sb, f"v{ver}", size=10, color=BORDER).pack(side="bottom", pady=12)

    def _show_section(self, key: str) -> None:
        for f in self._sections.values():
            f.grid_remove()
        self._sections[key].grid()
        for k, btn in self._nav_btns.items():
            btn.configure(
                fg_color=PURPLE if k == key else "transparent",
                text_color=TEXT  if k == key else SUBTEXT,
            )

    # ── Top bar ───────────────────────────────────────────────────────────────

    def _build_topbar(self, parent) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent", height=52)
        bar.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        bar.grid_propagate(False)
        _lbl(bar, "PhilFlight Tracker", size=18, weight="bold").pack(side="left")

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right")
        self._pill_status = _lbl(right, "● Starting", size=11, color=ORANGE)
        self._pill_status.pack(side="right", padx=4)
        self._lbl_next = _lbl(right, "", size=11, color=SUBTEXT)
        self._lbl_next.pack(side="right", padx=8)

    # ──────────────────────────── PRICES section ─────────────────────────────

    def _section_prices(self, parent) -> None:
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # ── Add route card ────────────────────────────────────────────────────
        add = _card(parent)
        add.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        hdr_row = ctk.CTkFrame(add, fg_color="transparent")
        hdr_row.pack(fill="x", padx=18, pady=(16, 8))
        _lbl(hdr_row, "Track a Flight Price", size=15, weight="bold").pack(side="left")
        _lbl(hdr_row,
             "Powered by Google Flights / Amadeus  ·  Add API keys in  ⚙  Settings",
             size=11, color=SUBTEXT).pack(side="right")

        fields = ctk.CTkFrame(add, fg_color="transparent")
        fields.pack(fill="x", padx=18, pady=(0, 16))

        _lbl(fields, "From", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._price_from = AirportEntry(fields, placeholder="e.g. MNL", width=160)
        self._price_from.pack(side="left", padx=(0, 16))

        _lbl(fields, "To", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._price_to = AirportEntry(fields, placeholder="e.g. HNL", width=160)
        self._price_to.pack(side="left", padx=(0, 16))

        _lbl(fields, "Depart", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._price_dep = DatePicker(fields, placeholder="Pick date", width=148)
        self._price_dep.pack(side="left", padx=(0, 16))

        _lbl(fields, "Return", size=11, color=SUBTEXT).pack(side="left", padx=(0, 4))
        self._price_ret = DatePicker(fields, placeholder="Optional", width=148)
        self._price_ret.pack(side="left", padx=(0, 16))

        ctk.CTkButton(
            fields, text="Watch & Check", width=130, height=36,
            fg_color=PURPLE, hover_color=VIOLET,
            command=self._add_watched_route,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            fields, text="Refresh All", width=100, height=36,
            fg_color="transparent", border_width=1, border_color=BORDER,
            hover_color=CARD_ALT, command=self._manual_price_check,
        ).pack(side="left")

        # ── Results ───────────────────────────────────────────────────────────
        self._prices_scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self._prices_scroll.grid(row=1, column=0, sticky="nsew")
        self._prices_scroll.grid_columnconfigure(0, weight=1)

        self._prices_empty = _lbl(
            self._prices_scroll,
            "No routes tracked yet.\n\n"
            "1.  Go to  ⚙  Settings  and add your free Amadeus API keys\n"
            "    (Sign up at  developers.amadeus.com  — takes 2 minutes)\n\n"
            "2.  Pick a route above and click  Watch & Check",
            size=13, color=SUBTEXT, justify="center",
        )
        self._prices_empty.grid(row=0, column=0, pady=80)

    # ── Price result card ─────────────────────────────────────────────────────

    def _render_price_results(self, offers: List[dict]) -> None:
        self._prices_empty.grid_remove()
        for w in self._prices_scroll.winfo_children():
            if w != self._prices_empty:
                w.destroy()

        if not offers:
            self._prices_empty.grid()
            return

        # Group by route + date
        routes: dict = {}
        for o in offers:
            k = f"{o['departure_airport']}  →  {o['arrival_airport']}  ·  {o.get('departure_time','')[:10]}"
            routes.setdefault(k, []).append(o)

        for i, (label, group) in enumerate(routes.items()):
            self._add_price_card(label, group, i)

    def _add_price_card(self, label: str, offers: list, row: int) -> None:
        card = _card(self._prices_scroll)
        card.grid(row=row, column=0, sticky="ew", pady=6, padx=2)
        card.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(card, fg_color=CARD_ALT, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        _lbl(hdr, label, size=13, weight="bold").pack(side="left", padx=14, pady=10)
        cheapest = min((o.get("price_php", 999999) for o in offers), default=0)
        if cheapest:
            _lbl(hdr, f"From  ₱{cheapest:,.0f}", size=12, color=GREEN,
                 weight="bold").pack(side="right", padx=14)

        # Flight rows — Google-Flights style
        for i, o in enumerate(offers[:8]):
            bg = CARD_ALT if i % 2 == 0 else CARD
            row_f = ctk.CTkFrame(card, fg_color=bg, corner_radius=0)
            row_f.grid(row=i + 1, column=0, sticky="ew", pady=0)
            row_f.grid_columnconfigure(2, weight=1)

            # Airline name
            airline = o.get("airline_name") or o.get("airline_code", "—")
            _lbl(row_f, airline, size=12, weight="bold", anchor="w",
                 width=190).grid(row=0, column=0, padx=14, pady=12, sticky="w")

            # Times
            dep_t = fmt_iso_time(o.get("departure_time", ""))
            arr_t = fmt_iso_time(o.get("arrival_time", ""))
            times_frame = ctk.CTkFrame(row_f, fg_color="transparent")
            times_frame.grid(row=0, column=1, padx=4, sticky="w")
            _lbl(times_frame, dep_t, size=14, weight="bold").pack(side="left")
            _lbl(times_frame, "  ──►  ", size=11, color=BORDER).pack(side="left")
            _lbl(times_frame, arr_t, size=14, weight="bold").pack(side="left")

            # Stops + duration
            stops   = o.get("stops", 0)
            stops_s = "Non-stop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
            dur     = o.get("duration", "").replace("PT", "").replace("H", "h ").replace("M", "m")
            _lbl(row_f, f"{stops_s}  ·  {dur}", size=11,
                 color=SUBTEXT).grid(row=0, column=2, padx=4, sticky="w")

            # Seats
            seats = o.get("seats_left")
            if seats and seats <= 9:
                _lbl(row_f, f"{seats} seats left", size=11,
                     color=ORANGE).grid(row=0, column=3, padx=8, sticky="e")

            # Price
            price = o.get("price_php", 0)
            price_color = GREEN if price == cheapest else TEXT
            _lbl(row_f, f"₱{price:,.0f}", size=15, weight="bold",
                 color=price_color).grid(row=0, column=4, padx=14, sticky="e")

        ctk.CTkFrame(card, fg_color="transparent", height=6).grid(
            row=len(offers[:8]) + 1, column=0)

    # ──────────────────────────── DEALS section ──────────────────────────────

    def _section_deals(self, parent) -> None:
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        _lbl(hdr, "Deals & Promos", size=16, weight="bold").pack(side="left")
        ctk.CTkButton(
            hdr, text="Scan Now", width=100, height=32,
            fg_color=PURPLE, hover_color=VIOLET,
            command=self._manual_deal_check,
        ).pack(side="right")
        _lbl(hdr, "Auto-scans Reddit + airline promo pages every hour",
             size=11, color=SUBTEXT).pack(side="right", padx=12)

        self._deals_scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self._deals_scroll.grid(row=1, column=0, sticky="nsew")
        self._deals_scroll.grid_columnconfigure(0, weight=1)

        self._deals_empty = _lbl(
            self._deals_scroll,
            "No deals found yet.\nClick Scan Now or wait for the next automatic scan (every hour).",
            size=13, color=SUBTEXT, justify="center",
        )
        self._deals_empty.grid(row=0, column=0, pady=80)

    # ──────────────────────────── DISCORD section ────────────────────────────

    def _section_discord(self, parent) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Scrollable so it's always reachable regardless of window height
        outer = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_columnconfigure(0, weight=1)

        # Card — no fixed size, sizes itself from content
        card = ctk.CTkFrame(outer, fg_color=CARD, corner_radius=14)
        card.grid(row=0, column=0, sticky="ew", pady=30, padx=60)
        card.grid_columnconfigure(0, weight=1)

        # Discord-purple header bar
        hdr = ctk.CTkFrame(card, fg_color="#5865F2", corner_radius=0, height=64)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        _lbl(hdr, "🔔  Connect Discord", size=16, weight="bold",
             color="white").place(relx=0.5, rely=0.5, anchor="center")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=28, pady=20)
        body.grid_columnconfigure(0, weight=1)

        # What you get
        _lbl(
            body,
            "Get notified in Discord when:\n"
            "  •  A promo or deal is posted\n"
            "  •  A flight price drops below your threshold",
            size=12, color=TEXT, justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 18))

        # Step-by-step
        steps = ctk.CTkFrame(body, fg_color=CARD_ALT, corner_radius=8)
        steps.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        steps.grid_columnconfigure(0, weight=1)
        _lbl(steps, "How to get your webhook URL",
             size=12, weight="bold", color=SUBTEXT).grid(
                 row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        for i, step in enumerate([
            "Open Discord  →  your server  →  Server Settings",
            "Go to  Integrations  →  Webhooks  →  New Webhook",
            "Choose a channel, give it a name, then copy the URL",
            "Paste it in the field below and click Save",
        ], 1):
            _lbl(steps, f"  {i}.  {step}", size=11, color=SUBTEXT).grid(
                row=i, column=0, sticky="w", padx=14, pady=1)
        ctk.CTkFrame(steps, fg_color="transparent", height=10).grid(
            row=5, column=0)

        # Webhook URL input
        _lbl(body, "Webhook URL", size=12, color=SUBTEXT).grid(
            row=2, column=0, sticky="w", pady=(0, 4))
        self._discord_var = tk.StringVar(value=self.settings.get("discord_webhook", ""))
        ctk.CTkEntry(
            body, textvariable=self._discord_var,
            placeholder_text="https://discord.com/api/webhooks/…",
            height=38,
        ).grid(row=3, column=0, sticky="ew", pady=(0, 16))

        # Notification toggles
        tog = ctk.CTkFrame(body, fg_color="transparent")
        tog.grid(row=4, column=0, sticky="w", pady=(0, 16))
        self._tog_deals  = tk.BooleanVar(value=self.settings.get("discord_notify_deals", True))
        self._tog_prices = tk.BooleanVar(value=self.settings.get("discord_notify_price_drops", True))
        ctk.CTkCheckBox(tog, text="New deals & promos",
                        variable=self._tog_deals,
                        font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 24))
        ctk.CTkCheckBox(tog, text="Price drops",
                        variable=self._tog_prices,
                        font=ctk.CTkFont(size=12)).pack(side="left")

        # Action buttons
        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.grid(row=5, column=0, sticky="w", pady=(0, 8))
        ctk.CTkButton(
            btns, text="Test Connection", width=150, height=38,
            fg_color="transparent", border_width=1, border_color=BORDER,
            hover_color=CARD_ALT, command=self._test_discord,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btns, text="Save", width=100, height=38,
            fg_color=PURPLE, hover_color=VIOLET, command=self._save_discord,
        ).pack(side="left")
        self._discord_status = _lbl(btns, "", size=12, color=GREEN)
        self._discord_status.pack(side="left", padx=14)

    # ──────────────────────────── SETTINGS section ───────────────────────────

    def _section_settings(self, parent) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        self._sf: dict[str, tk.StringVar] = {}

        def field(label: str, key: str, grid_row: int, col: int = 0, show: str = "") -> None:
            wrap = ctk.CTkFrame(scroll, fg_color="transparent")
            wrap.grid(row=grid_row, column=col, sticky="ew", padx=(4 + col * 8, 4), pady=4)
            _lbl(wrap, label, size=11, color=SUBTEXT).pack(anchor="w")
            var = tk.StringVar(value=str(self.settings.get(key, "")))
            ctk.CTkEntry(wrap, textvariable=var, show=show).pack(fill="x")
            self._sf[key] = var

        r = 0

        r = _sep(scroll, r, "Polling intervals")
        field("Flight price check every (minutes)", "price_check_interval_minutes", r, 0)
        field("Deal scan every (minutes)",           "deal_check_interval_minutes",  r, 1)
        r += 1

        r = _sep(scroll, r, "Appearance")
        wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        wrap.grid(row=r, column=0, columnspan=2, sticky="w", padx=4, pady=4)
        _lbl(wrap, "Theme", size=11, color=SUBTEXT).pack(anchor="w")
        self._theme_var = tk.StringVar(value=self.settings.get("theme", "dark"))
        ctk.CTkSegmentedButton(
            wrap, values=["dark", "light", "system"],
            variable=self._theme_var, width=260,
        ).pack(anchor="w")
        r += 1

        r = _sep(scroll, r, "Google Flights prices  (Amadeus API — free at developers.amadeus.com)")
        field("Client ID",     "amadeus_client_id",     r, 0)
        field("Client Secret", "amadeus_client_secret", r, 1, show="*")
        r += 1
        env_wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        env_wrap.grid(row=r, column=0, sticky="ew", padx=4, pady=4)
        _lbl(env_wrap, "Environment", size=11, color=SUBTEXT).pack(anchor="w")
        self._amadeus_env = tk.StringVar(
            value=self.settings.get("amadeus_environment", "test"))
        ctk.CTkSegmentedButton(
            env_wrap, values=["test", "production"],
            variable=self._amadeus_env, width=200,
        ).pack(anchor="w")
        r += 1

        r = _sep(scroll, r, "Auto-update (GitHub)")
        field("Organization / owner", "github_owner", r, 0)
        field("Repository name",      "github_repo",  r, 1)
        r += 1

        # Save button
        ctk.CTkFrame(scroll, fg_color="transparent", height=16).grid(row=r, column=0, columnspan=2)
        r += 1
        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.grid(row=r, column=0, columnspan=2, sticky="w", padx=4)
        ctk.CTkButton(
            btn_row, text="Save Settings", width=140, height=38,
            fg_color=PURPLE, hover_color=VIOLET, command=self._save_settings,
        ).pack(side="left")
        self._settings_status = _lbl(btn_row, "", size=11, color=GREEN)
        self._settings_status.pack(side="left", padx=14)

    # ────────────────────────── Background services ───────────────────────────

    def _start_services(self) -> None:
        # Auto-updater
        owner = self.settings.get("github_owner", "")
        repo  = self.settings.get("github_repo", "")
        if owner and repo:
            self._updater = AutoUpdater(
                owner, repo,
                check_interval_hours=int(
                    self.settings.get("update_check_interval_hours", 2)),
            )
            self._updater.on_update_available = self._on_update_available
            self._updater.start()

        # Deal scanner
        self._deal_monitor = DealMonitor(
            check_interval_minutes=int(
                self.settings.get("deal_check_interval_minutes", 60)),
        )
        self._deal_monitor.on_new_deals = self._on_deals
        self._deal_monitor.start()

        # Price tracker
        from api.amadeus import AmadeusClient
        amadeus = AmadeusClient(
            client_id=self.settings.get("amadeus_client_id", ""),
            client_secret=self.settings.get("amadeus_client_secret", ""),
            production=self.settings.get("amadeus_environment", "test") == "production",
        )
        self._price_tracker = PriceTracker(
            amadeus, self.settings,
            check_interval_minutes=int(
                self.settings.get("price_check_interval_minutes", 60)),
        )
        self._price_tracker.on_prices_updated = self._on_prices
        self._price_tracker.on_price_drop      = self._on_price_drop
        self._price_tracker.start()

        self._pill_status.configure(text="● Ready", text_color=GREEN)

    # ──────────────────────── Callbacks (background → main) ──────────────────

    def _on_deals(self, deals: List[dict]) -> None:
        if self._root:
            self._root.after(0, lambda: self._apply_deals(deals))

    def _on_prices(self, offers: List[dict]) -> None:
        if self._root:
            self._root.after(0, lambda: self._render_price_results(offers))

    def _on_price_drop(self, info: dict) -> None:
        if self._root:
            self._root.after(0, lambda: self._handle_price_drop(info))

    def _on_update_available(self, current: str, latest: str) -> None:
        if self._root:
            self._root.after(0, lambda: self._show_update_banner(current, latest))

    # ──────────────────────── Main-thread UI updates ──────────────────────────

    def _apply_deals(self, deals: List[dict]) -> None:
        min_s = int(self.settings.get("min_reddit_score", 5))
        new   = [d for d in deals
                 if d.get("type") != "reddit" or d.get("score", 0) >= min_s]
        if not new:
            return
        self._deals_empty.grid_remove()
        existing = [w for w in self._deals_scroll.winfo_children()
                    if w != self._deals_empty]
        for i, deal in enumerate(new):
            self._add_deal_card(deal, len(existing) + i)
        self._show_section("deals")

        webhook = self.settings.get("discord_webhook", "")
        if webhook and self.settings.get("discord_notify_deals", True):
            from notifications.discord import notify_deal
            for d in new:
                threading.Thread(
                    target=notify_deal, args=(webhook, d), daemon=True,
                ).start()

    def _add_deal_card(self, deal: dict, row: int) -> None:
        src   = deal.get("source", "")
        title = (deal.get("title") or "")[:300]
        url   = deal.get("url", "")
        score = deal.get("score")

        card = _card(self._deals_scroll)
        card.grid(row=row, column=0, sticky="ew", pady=5, padx=2)
        card.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        badge_c = {"Philippine Airlines": "#0038A8", "Cebu Pacific": "#1e88e5",
                   "AirAsia PH": "#e53935"}.get(src, "#4a4e69")
        ctk.CTkLabel(
            hdr, text=f"  {src}  ",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=badge_c, corner_radius=6, text_color="white",
        ).pack(side="left")
        if score:
            _lbl(hdr, f"🔼 {score}", size=11, color=SUBTEXT).pack(side="right")

        _lbl(card, title, size=12, color=TEXT,
             wraplength=820, justify="left", anchor="w").grid(
                 row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        if url:
            ctk.CTkButton(
                card, text="Open →", width=80, height=26,
                fg_color="transparent", border_width=1, border_color=BORDER,
                command=lambda u=url: webbrowser.open(u),
            ).grid(row=2, column=0, sticky="e", padx=14, pady=(0, 10))

    def _handle_price_drop(self, info: dict) -> None:
        pct = (info["old_price"] - info["new_price"]) / info["old_price"] * 100
        self._show_section("prices")
        messagebox.showinfo(
            "Price Drop!",
            f"💸  {info['route']}  ({info.get('date', '')})\n\n"
            f"{info.get('airline', '')} dropped {pct:.0f}%\n"
            f"Was  ₱{info['old_price']:,.0f}  →  Now  ₱{info['new_price']:,.0f}",
            parent=self._root,
        )
        webhook = self.settings.get("discord_webhook", "")
        if webhook and self.settings.get("discord_notify_price_drops", True):
            from notifications.discord import notify_price_drop
            threading.Thread(
                target=notify_price_drop,
                args=(webhook, info["route"], info["old_price"],
                      info["new_price"], info.get("airline", ""),
                      info.get("url", "")),
                daemon=True,
            ).start()

    # ── Update banner ──────────────────────────────────────────────────────────

    def _show_update_banner(self, current: str, latest: str) -> None:
        for w in self._notif_area.winfo_children():
            w.destroy()
        banner = ctk.CTkFrame(
            self._notif_area, fg_color="#1a2e1a", height=36, corner_radius=0)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        _lbl(banner, f"  Update available:  v{current}  →  v{latest}",
             size=12, color="#86efac").pack(side="left", padx=12, pady=4)
        ctk.CTkButton(
            banner, text="Update Now", width=100, height=24,
            fg_color=GREEN, hover_color="#059669", text_color=BG,
            command=lambda: self._confirm_update(current, latest),
        ).pack(side="right", padx=8, pady=4)
        ctk.CTkButton(
            banner, text="✕", width=28, height=24,
            fg_color="transparent", hover_color="#2a3a2a",
            command=banner.destroy,
        ).pack(side="right", padx=(0, 4), pady=4)

    def _confirm_update(self, current: str, latest: str) -> None:
        if not messagebox.askyesno(
            "Install Update",
            f"Update from v{current} to v{latest}?\n\n"
            "The app will download the update and restart automatically.\n"
            "Your settings and data will not be affected.",
            parent=self._root,
        ):
            return
        dlg = ctk.CTkToplevel(self._root)
        dlg.title("Updating…")
        dlg.geometry("380x150")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)
        _lbl(dlg, f"Installing v{latest}…", size=14, weight="bold").pack(pady=(22, 8))
        self._upd_lbl = _lbl(dlg, "Connecting…", size=12, color=SUBTEXT)
        self._upd_lbl.pack()
        bar = ctk.CTkProgressBar(dlg, width=320)
        bar.pack(pady=14)
        bar.configure(mode="indeterminate")
        bar.start()

        def _run() -> None:
            try:
                self._updater.download_and_apply(
                    on_progress=lambda m: self._root.after(
                        0, lambda msg=m: self._upd_lbl.configure(text=msg),
                    )
                )
            except Exception as err:
                msg = str(err)
                self._root.after(0, lambda m=msg: (
                    dlg.destroy(),
                    messagebox.showerror("Update failed", m, parent=self._root),
                ))

        threading.Thread(target=_run, daemon=True).start()

    # ── User actions ──────────────────────────────────────────────────────────

    def _add_watched_route(self) -> None:
        frm = self._price_from.get()
        to  = self._price_to.get()
        dep = self._price_dep.get()
        ret = self._price_ret.get()

        if not frm or not to:
            messagebox.showwarning(
                "Missing fields", "Please fill in both From and To airports.",
                parent=self._root)
            return
        if not dep:
            messagebox.showwarning(
                "No departure date", "Please pick a departure date using the 📅 button.",
                parent=self._root)
            return

        routes = list(self.settings.get("watched_price_routes", []))
        entry  = {"from": frm, "to": to, "date": dep}
        if ret:
            entry["return_date"] = ret
        if entry not in routes:
            routes.append(entry)
            self.settings.set("watched_price_routes", routes)
            self.settings.save()

        if self._price_tracker and self._price_tracker._client.is_configured:
            self._price_tracker.check_now()
        else:
            messagebox.showinfo(
                "Route saved!",
                "Your route has been saved.\n\n"
                "To see live prices, add your free Amadeus API keys in  ⚙  Settings.",
                parent=self._root,
            )

    def _manual_price_check(self) -> None:
        if self._price_tracker and self._price_tracker._client.is_configured:
            self._price_tracker.check_now()
        else:
            messagebox.showinfo(
                "Amadeus not configured",
                "Add your free Amadeus API keys in  ⚙  Settings\n"
                "(developers.amadeus.com — free sign-up).",
                parent=self._root,
            )

    def _manual_deal_check(self) -> None:
        if self._deal_monitor:
            self._deal_monitor.check_now()

    def _test_discord(self) -> None:
        url = self._discord_var.get().strip()
        if not url:
            self._discord_status.configure(
                text="Paste your webhook URL first.", text_color=ORANGE)
            return
        from notifications.discord import test_webhook
        ok = test_webhook(url)
        self._discord_status.configure(
            text="✓ Test message sent!" if ok else "✗ Failed — check the URL.",
            text_color=GREEN if ok else RED,
        )

    def _save_discord(self) -> None:
        self.settings.set("discord_webhook",            self._discord_var.get().strip())
        self.settings.set("discord_notify_deals",       self._tog_deals.get())
        self.settings.set("discord_notify_price_drops", self._tog_prices.get())
        self.settings.save()
        self._discord_status.configure(text="✓ Saved!", text_color=GREEN)

    def _save_settings(self) -> None:
        for key, var in self._sf.items():
            self.settings.set(key, var.get().strip())
        self.settings.set("theme",               self._theme_var.get())
        self.settings.set("amadeus_environment", self._amadeus_env.get())
        self.settings.save()
        ctk.set_appearance_mode(self._theme_var.get())
        self._settings_status.configure(
            text="✓ Saved — restart to apply all changes.", text_color=GREEN)

    def _on_close(self) -> None:
        for svc in (self._updater, self._deal_monitor, self._price_tracker):
            if svc:
                svc.stop()
        self._root.destroy()
