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
from core.tracker import FlightTracker
from core.updater import AutoUpdater
from core.deal_monitor import DealMonitor
from core.price_tracker import PriceTracker
from ui.flight_table import FlightTable

logger = logging.getLogger(__name__)

ASSETS = Path(__file__).parent.parent / "assets"
VERSION_FILE = Path(__file__).parent.parent / "version.json"


class FlightTrackerApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tracker: Optional[FlightTracker] = None
        self._updater: Optional[AutoUpdater] = None
        self._deal_monitor: Optional[DealMonitor] = None
        self._price_tracker: Optional[PriceTracker] = None
        self._root: Optional[ctk.CTk] = None
        self._countdown_job: Optional[str] = None
        self._next_update_time: Optional[datetime] = None
        self._pending_update_url: str = ""

    # ------------------------------------------------------------------ #
    # Startup                                                              #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        self._root = ctk.CTk()
        self._root.title("PhilFlight Tracker")
        self._root.geometry("1200x750")
        self._root.minsize(860, 540)

        self._set_icon()
        self._build_ui()
        self._start_tracker()
        self._start_updater()
        self._start_deal_monitor()
        self._start_price_tracker()

        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.mainloop()

    def _set_icon(self) -> None:
        for path, method in [
            (ASSETS / "icon.ico", lambda p: self._root.iconbitmap(str(p))),
            (ASSETS / "icon.png", lambda p: self._root.iconphoto(True, tk.PhotoImage(file=str(p)))),
        ]:
            if path.exists():
                try:
                    method(path)
                    return
                except Exception:
                    pass

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        self._build_menubar()

        # Notification area — empty until needed
        self._notif_area = ctk.CTkFrame(self._root, fg_color="transparent")
        self._notif_area.pack(fill="x")

        # Header
        header = ctk.CTkFrame(self._root, height=58, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="✈  PhilFlight Tracker",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=16, pady=8)
        self._header_status = ctk.CTkLabel(
            header, text="Starting…",
            font=ctk.CTkFont(size=12), text_color=("gray50", "gray65"),
        )
        self._header_status.pack(side="right", padx=16)

        # Filter bar
        filter_bar = ctk.CTkFrame(self._root, height=64, corner_radius=0)
        filter_bar.pack(fill="x", pady=(2, 0))
        filter_bar.pack_propagate(False)
        self._build_filters(filter_bar)

        # Status bar (must be packed BEFORE the tab view so it stays at the bottom)
        status_bar = ctk.CTkFrame(self._root, height=26, corner_radius=0)
        status_bar.pack(side="bottom", fill="x")
        status_bar.pack_propagate(False)
        self._lbl_last  = ctk.CTkLabel(status_bar, text="Last update: —",
                                        font=ctk.CTkFont(size=11), text_color=("gray50","gray60"))
        self._lbl_last.pack(side="left", padx=10)
        self._lbl_next  = ctk.CTkLabel(status_bar, text="Next update: —",
                                        font=ctk.CTkFont(size=11), text_color=("gray50","gray60"))
        self._lbl_next.pack(side="left", padx=6)
        self._lbl_api   = ctk.CTkLabel(status_bar, text="● Connecting",
                                        font=ctk.CTkFont(size=11), text_color=("gray50","gray60"))
        self._lbl_api.pack(side="right", padx=10)

        # Tab view — Flights | Deals
        self._tabs = ctk.CTkTabview(self._root)
        self._tabs.pack(fill="both", expand=True, padx=8, pady=8)

        self._tabs.add("✈ Flights")
        self._tabs.add("🎫 Deals & Promos")
        self._tabs.add("💰 Prices")

        self._table = FlightTable(self._tabs.tab("✈ Flights"))
        self._table.pack(fill="both", expand=True)

        self._build_deals_panel(self._tabs.tab("🎫 Deals & Promos"))
        self._build_prices_panel(self._tabs.tab("💰 Prices"))

    def _build_filters(self, parent: ctk.CTkFrame) -> None:
        p = {"padx": (0, 10), "pady": 10}

        ctk.CTkLabel(parent, text="From:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(14, 4), pady=10)
        self._dep_var = tk.StringVar(value=self.settings.get("departure_airport", "RPLL"))
        ctk.CTkEntry(parent, textvariable=self._dep_var, width=80,
                     placeholder_text="RPLL").pack(side="left", **p)

        ctk.CTkLabel(parent, text="To:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 4), pady=10)
        self._arr_var = tk.StringVar(value=self.settings.get("arrival_airport", ""))
        ctk.CTkEntry(parent, textvariable=self._arr_var, width=80,
                     placeholder_text="Any").pack(side="left", **p)

        ctk.CTkLabel(parent, text="Airline:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 4), pady=10)
        self._airline_var = tk.StringVar(value=self.settings.get("airline_filter", ""))
        ctk.CTkEntry(parent, textvariable=self._airline_var, width=90,
                     placeholder_text="PAL / CEB").pack(side="left", **p)

        ctk.CTkButton(parent, text="Refresh Now", width=110,
                      command=self._manual_refresh).pack(side="left", **p)

        self._lbl_count = ctk.CTkLabel(parent, text="",
                                        font=ctk.CTkFont(size=12), text_color=("gray50","gray65"))
        self._lbl_count.pack(side="right", padx=16)

    def _build_prices_panel(self, parent: ctk.CTkFrame) -> None:
        # ── Add-route bar ──────────────────────────────────────────────
        add_bar = ctk.CTkFrame(parent, fg_color="transparent", height=54)
        add_bar.pack(fill="x", padx=8, pady=(8, 0))
        add_bar.pack_propagate(False)

        ctk.CTkLabel(add_bar, text="From:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 4))
        self._price_from_var = tk.StringVar(value="MNL")
        ctk.CTkEntry(add_bar, textvariable=self._price_from_var, width=68,
                     placeholder_text="MNL").pack(side="left", padx=(0, 10))

        ctk.CTkLabel(add_bar, text="To:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 4))
        self._price_to_var = tk.StringVar(value="CEB")
        ctk.CTkEntry(add_bar, textvariable=self._price_to_var, width=68,
                     placeholder_text="CEB").pack(side="left", padx=(0, 10))

        ctk.CTkLabel(add_bar, text="Date (YYYY-MM-DD):",
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self._price_date_var = tk.StringVar()
        ctk.CTkEntry(add_bar, textvariable=self._price_date_var, width=120,
                     placeholder_text="2026-09-15").pack(side="left", padx=(0, 10))

        ctk.CTkButton(add_bar, text="Watch Route", width=110,
                      command=self._add_watched_route).pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_bar, text="Check Now", width=100,
                      command=self._manual_price_check).pack(side="left")

        hint = ("Uses Google Flights / Amadeus data  •  "
                "Add Amadeus API keys in Settings to enable")
        ctk.CTkLabel(add_bar, text=hint, font=ctk.CTkFont(size=11),
                     text_color=("gray50", "gray60")).pack(side="right", padx=8)

        # ── Scrollable price cards area ─────────────────────────────────
        self._prices_scroll = ctk.CTkScrollableFrame(parent)
        self._prices_scroll.pack(fill="both", expand=True, padx=8, pady=8)

        self._prices_empty = ctk.CTkLabel(
            self._prices_scroll,
            text=(
                "No prices yet.\n\n"
                "1. Add your Amadeus API keys in File → Settings\n"
                "2. Enter a route above and click 'Watch Route'\n"
                "3. Click 'Check Now' or wait for automatic refresh"
            ),
            font=ctk.CTkFont(size=13),
            text_color=("gray50", "gray60"),
            justify="center",
        )
        self._prices_empty.pack(pady=60)

    def _build_deals_panel(self, parent: ctk.CTkFrame) -> None:
        toolbar = ctk.CTkFrame(parent, fg_color="transparent", height=40)
        toolbar.pack(fill="x", pady=(4, 0))
        toolbar.pack_propagate(False)
        ctk.CTkLabel(toolbar, text="Deals from Reddit & airline promo pages",
                     font=ctk.CTkFont(size=12), text_color=("gray50","gray65")).pack(
                         side="left", padx=12)
        ctk.CTkButton(toolbar, text="Check Now", width=100,
                      command=self._manual_deal_check).pack(side="right", padx=12)

        self._deals_scroll = ctk.CTkScrollableFrame(parent)
        self._deals_scroll.pack(fill="both", expand=True, padx=4, pady=4)

        self._deals_empty = ctk.CTkLabel(
            self._deals_scroll,
            text="No deals found yet. Click 'Check Now' or wait for the next automatic scan.",
            font=ctk.CTkFont(size=13), text_color=("gray50","gray60"),
        )
        self._deals_empty.pack(pady=40)

    def _build_menubar(self) -> None:
        menubar = tk.Menu(self._root)
        self._root.configure(menu=menubar)

        file_m = tk.Menu(menubar, tearoff=0)
        file_m.add_command(label="Settings…", command=self._open_settings)
        file_m.add_separator()
        file_m.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_m)

        help_m = tk.Menu(menubar, tearoff=0)
        help_m.add_command(label="Check for App Updates", command=self._manual_update_check)
        help_m.add_separator()
        help_m.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_m)

    # ------------------------------------------------------------------ #
    # Background services                                                  #
    # ------------------------------------------------------------------ #

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
        interval = int(self.settings.get("update_check_interval_hours", 2))
        self._updater = AutoUpdater(owner, repo, check_interval_hours=interval)
        self._updater.on_update_available = self._on_update_available  # (current, latest)
        self._updater.start()

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

    def _start_deal_monitor(self) -> None:
        interval = int(self.settings.get("deal_check_interval_minutes", 60))
        self._deal_monitor = DealMonitor(check_interval_minutes=interval)
        self._deal_monitor.on_new_deals = self._on_new_deals
        self._deal_monitor.start()

    # ------------------------------------------------------------------ #
    # Tracker callbacks                                                    #
    # ------------------------------------------------------------------ #

    def _on_flights_updated(self, flights: List[dict], ts: datetime) -> None:
        if self._root:
            self._root.after(0, lambda: self._apply_flight_update(flights, ts))

    def _on_tracker_error(self, msg: str) -> None:
        if self._root:
            self._root.after(0, lambda: self._show_api_error(msg))

    def _on_prices_updated(self, offers: List[dict]) -> None:
        if self._root:
            self._root.after(0, lambda: self._apply_price_update(offers))

    def _on_price_drop(self, info: dict) -> None:
        if self._root:
            self._root.after(0, lambda: self._handle_price_drop(info))

    def _on_new_deals(self, deals: List[dict]) -> None:
        if self._root:
            self._root.after(0, lambda: self._apply_new_deals(deals))

    def _on_update_available(self, current: str, latest: str) -> None:
        if self._root:
            self._root.after(0, lambda: self._show_update_banner(current, latest))

    # ------------------------------------------------------------------ #
    # Main-thread UI updates                                               #
    # ------------------------------------------------------------------ #

    def _apply_flight_update(self, flights: List[dict], ts: datetime) -> None:
        self._table.update_flights(flights)
        n = len(flights)
        self._lbl_count.configure(text=f"{n} flight{'s' if n != 1 else ''} found")
        self._lbl_last.configure(text=f"Last update: {ts.strftime('%H:%M:%S')}")
        self._lbl_api.configure(text="● Connected", text_color="#2ecc71")
        self._header_status.configure(text="Connected")

        interval_secs = self.settings.get("poll_interval_minutes", 30) * 60
        self._next_update_time = ts + timedelta(seconds=interval_secs)
        self._tick_countdown()

        # Discord flight notification
        webhook = self.settings.get("discord_webhook", "")
        if webhook and self.settings.get("discord_notify_flights", True) and flights:
            from notifications.discord import notify_flight_update
            import threading
            threading.Thread(
                target=notify_flight_update,
                args=(webhook, flights,
                      self.settings.get("departure_airport", ""),
                      self.settings.get("arrival_airport", "")),
                daemon=True,
            ).start()

    def _show_api_error(self, msg: str) -> None:
        self._lbl_api.configure(text="● Error", text_color="#e74c3c")
        self._header_status.configure(text=f"Error: {msg}")

    def _tick_countdown(self) -> None:
        if self._countdown_job:
            self._root.after_cancel(self._countdown_job)
        if not self._next_update_time:
            return
        remaining = max(0, int((self._next_update_time - datetime.now()).total_seconds()))
        m, s = divmod(remaining, 60)
        self._lbl_next.configure(text=f"Next update: {m:02d}:{s:02d}")
        if remaining > 0:
            self._countdown_job = self._root.after(1000, self._tick_countdown)

    def _apply_price_update(self, offers: List[dict]) -> None:
        self._prices_empty.pack_forget()
        for w in self._prices_scroll.winfo_children():
            if w != self._prices_empty:
                w.destroy()

        # Group by route
        routes: dict[str, list] = {}
        for o in offers:
            key = f"{o['departure_airport']} → {o['arrival_airport']}  ({o.get('departure_time','')[:10]})"
            routes.setdefault(key, []).append(o)

        for route_label, route_offers in routes.items():
            self._add_price_section(route_label, route_offers)

    def _add_price_section(self, label: str, offers: list) -> None:
        section = ctk.CTkFrame(self._prices_scroll, corner_radius=8)
        section.pack(fill="x", padx=4, pady=6)

        ctk.CTkLabel(section, text=label,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
                         anchor="w", padx=12, pady=(10, 4))

        for offer in offers[:8]:
            row = ctk.CTkFrame(section, fg_color=("gray90", "gray20"), corner_radius=6)
            row.pack(fill="x", padx=10, pady=2)

            airline = offer.get("airline_name") or offer.get("airline_code", "—")
            stops   = offer.get("stops", 0)
            stops_s = "Non-stop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
            dur     = offer.get("duration", "").replace("PT", "").replace("H", "h ").replace("M", "m")
            seats   = offer.get("seats_left")
            price   = offer.get("price_php", 0)
            dep_t   = offer.get("departure_time", "")[-8:] if len(offer.get("departure_time","")) > 10 else offer.get("departure_time","")
            arr_t   = offer.get("arrival_time",   "")[-8:] if len(offer.get("arrival_time",  "")) > 10 else offer.get("arrival_time","")

            ctk.CTkLabel(row, text=f"  {airline}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         width=200, anchor="w").pack(side="left", padx=(6, 0), pady=6)
            ctk.CTkLabel(row, text=f"{dep_t} → {arr_t}",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=10)
            ctk.CTkLabel(row, text=f"{stops_s}  {dur}",
                         font=ctk.CTkFont(size=11),
                         text_color=("gray40", "gray65")).pack(side="left", padx=10)
            if seats is not None:
                ctk.CTkLabel(row, text=f"{seats} seats left",
                             font=ctk.CTkFont(size=11),
                             text_color="#e67e22").pack(side="left", padx=10)
            ctk.CTkLabel(row, text=f"₱{price:,.0f}",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="#2ecc71").pack(side="right", padx=16)

    def _handle_price_drop(self, info: dict) -> None:
        drop_pct = (info["old_price"] - info["new_price"]) / info["old_price"] * 100
        # Flash Prices tab
        self._tabs.set("💰 Prices")
        messagebox.showinfo(
            "Price Drop!",
            f"💸 {info['route']}  ({info.get('date','')})\n\n"
            f"{info.get('airline','')} dropped {drop_pct:.0f}%\n"
            f"Was ₱{info['old_price']:,.0f}  →  Now ₱{info['new_price']:,.0f}",
            parent=self._root,
        )
        webhook = self.settings.get("discord_webhook", "")
        if webhook and self.settings.get("discord_notify_price_drops", True):
            from notifications.discord import notify_price_drop
            import threading
            threading.Thread(
                target=notify_price_drop,
                args=(webhook, info["route"], info["old_price"],
                      info["new_price"], info.get("airline",""), info.get("url","")),
                daemon=True,
            ).start()

    def _apply_new_deals(self, deals: List[dict]) -> None:
        min_score = int(self.settings.get("min_reddit_score", 5))
        filtered = [
            d for d in deals
            if d.get("type") != "reddit" or d.get("score", 0) >= min_score
        ]
        if not filtered:
            return

        # Remove the "no deals" placeholder
        self._deals_empty.pack_forget()

        for deal in filtered:
            self._add_deal_card(deal)

        # Discord deal notifications
        webhook = self.settings.get("discord_webhook", "")
        if webhook and self.settings.get("discord_notify_deals", True):
            from notifications.discord import notify_deal
            import threading
            for deal in filtered:
                threading.Thread(
                    target=notify_deal, args=(webhook, deal), daemon=True
                ).start()

        # Flash the tab title so user notices
        self._tabs.set("🎫 Deals & Promos")

    def _add_deal_card(self, deal: dict) -> None:
        card = ctk.CTkFrame(self._deals_scroll, corner_radius=8)
        card.pack(fill="x", padx=6, pady=4)

        source = deal.get("source", "Unknown")
        score  = deal.get("score")
        url    = deal.get("url", "")
        title  = deal.get("title", "")

        header_row = ctk.CTkFrame(card, fg_color="transparent")
        header_row.pack(fill="x", padx=10, pady=(8, 2))

        src_color = {"Philippine Airlines": "#0038A8", "Cebu Pacific": "#FFCD00",
                     "AirAsia PH": "#E01A22"}.get(source, "#555577")
        ctk.CTkLabel(
            header_row, text=f"  {source}  ",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=src_color, corner_radius=4, text_color="white",
        ).pack(side="left")

        if score is not None:
            ctk.CTkLabel(
                header_row, text=f"🔼 {score}",
                font=ctk.CTkFont(size=11), text_color=("gray50","gray65"),
            ).pack(side="right")

        ctk.CTkLabel(
            card, text=title, font=ctk.CTkFont(size=12),
            wraplength=900, justify="left", anchor="w",
        ).pack(fill="x", padx=10, pady=(2, 6))

        if url:
            ctk.CTkButton(
                card, text="Open →", width=80, height=24,
                command=lambda u=url: webbrowser.open(u),
            ).pack(anchor="e", padx=10, pady=(0, 8))

    # ------------------------------------------------------------------ #
    # Update banner                                                        #
    # ------------------------------------------------------------------ #

    def _show_update_banner(self, current: str, latest: str) -> None:
        for w in self._notif_area.winfo_children():
            w.destroy()
        banner = ctk.CTkFrame(self._notif_area, fg_color="#1a5c2a", height=36)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        ctk.CTkLabel(
            banner, text=f"  Update available: v{current} → v{latest}",
            text_color="white", font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=12, pady=4)
        ctk.CTkButton(
            banner, text="Update Now", width=100, height=24,
            command=lambda: self._confirm_and_update(current, latest),
        ).pack(side="right", padx=8, pady=4)
        ctk.CTkButton(
            banner, text="✕", width=28, height=24,
            fg_color="transparent", hover_color="#2a7a3a",
            command=banner.destroy,
        ).pack(side="right", padx=(0, 4), pady=4)

    def _confirm_and_update(self, current: str, latest: str) -> None:
        confirmed = messagebox.askyesno(
            "Update PhilFlight Tracker",
            f"Update from v{current} to v{latest}?\n\n"
            "The app will download the update and restart automatically.\n"
            "Your settings and price history will not be affected.",
            parent=self._root,
        )
        if not confirmed:
            return

        # Show progress dialog
        self._update_progress_dialog(latest)

    def _update_progress_dialog(self, latest: str) -> None:
        dlg = ctk.CTkToplevel(self._root)
        dlg.title("Updating…")
        dlg.geometry("360x140")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)  # block close during update

        ctk.CTkLabel(
            dlg, text=f"Installing v{latest}…",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(20, 8))

        self._update_status_lbl = ctk.CTkLabel(
            dlg, text="Connecting to GitHub…",
            font=ctk.CTkFont(size=12), text_color=("gray50", "gray65"),
        )
        self._update_status_lbl.pack()

        self._update_bar = ctk.CTkProgressBar(dlg, width=300)
        self._update_bar.pack(pady=12)
        self._update_bar.set(0)
        self._update_bar.configure(mode="indeterminate")
        self._update_bar.start()

        def _on_progress(msg: str) -> None:
            if self._root:
                self._root.after(0, lambda m=msg: self._update_status_lbl.configure(text=m))

        def _run_update() -> None:
            try:
                self._updater.download_and_apply(on_progress=_on_progress)
            except Exception as exc:
                logger.error("Update failed: %s", exc)
                if self._root:
                    self._root.after(0, lambda: self._update_failed(dlg, str(exc)))

        threading.Thread(target=_run_update, daemon=True, name="ApplyUpdate").start()

    def _update_failed(self, dlg, error: str) -> None:
        dlg.destroy()
        messagebox.showerror(
            "Update failed",
            f"Could not install the update:\n\n{error}\n\n"
            "Check your internet connection and try again via Help → Check for Updates.",
            parent=self._root,
        )

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _manual_refresh(self) -> None:
        dep     = self._dep_var.get().strip().upper()
        arr     = self._arr_var.get().strip().upper()
        airline = self._airline_var.get().strip().upper()

        if dep and not self.settings.validate_icao_airport(dep):
            messagebox.showerror("Invalid input",
                                 f"'{dep}' is not a valid ICAO airport code.")
            return
        if arr and not self.settings.validate_icao_airport(arr):
            messagebox.showerror("Invalid input",
                                 f"'{arr}' is not a valid ICAO airport code.")
            return

        self.settings.set("departure_airport", dep)
        self.settings.set("arrival_airport",   arr)
        self.settings.set("airline_filter",    airline)
        self._header_status.configure(text="Refreshing…")
        if self._tracker:
            self._tracker.trigger_refresh()

    def _add_watched_route(self) -> None:
        from_code = self._price_from_var.get().strip().upper()
        to_code   = self._price_to_var.get().strip().upper()
        dep_date  = self._price_date_var.get().strip()

        if not (from_code and to_code and dep_date):
            messagebox.showwarning("Missing fields",
                                   "Fill in From, To, and Date.", parent=self._root)
            return

        import re
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", dep_date):
            messagebox.showerror("Invalid date",
                                 "Date must be in YYYY-MM-DD format.", parent=self._root)
            return

        routes: list = list(self.settings.get("watched_price_routes", []))
        new_route = {"from": from_code, "to": to_code, "date": dep_date}
        if new_route not in routes:
            routes.append(new_route)
            self.settings.set("watched_price_routes", routes)
            self.settings.save()

        if self._price_tracker:
            self._price_tracker.check_now()
        else:
            messagebox.showinfo(
                "Amadeus not configured",
                "Add your Amadeus API keys in File → Settings to start tracking prices.",
                parent=self._root,
            )

    def _manual_price_check(self) -> None:
        if self._price_tracker:
            self._price_tracker.check_now()
        else:
            messagebox.showinfo(
                "Amadeus not configured",
                "Add your Amadeus API keys in File → Settings.",
                parent=self._root,
            )

    def _manual_deal_check(self) -> None:
        self._header_status.configure(text="Scanning for deals…")
        if self._deal_monitor:
            self._deal_monitor.check_now()

    def _open_settings(self) -> None:
        from ui.dialogs import SettingsDialog
        dlg = SettingsDialog(self._root, self.settings)
        self._root.wait_window(dlg)
        if self._tracker:
            self._tracker.restart()
        # Re-start deal monitor with potentially new interval
        if self._deal_monitor:
            self._deal_monitor.stop()
        self._start_deal_monitor()
        self._start_updater()

    def _manual_update_check(self) -> None:
        if self._updater:
            self._updater.check_now()
        else:
            messagebox.showinfo(
                "No GitHub repo configured",
                "Open File → Settings and enter your GitHub username and repo name.",
                parent=self._root,
            )

    def _show_about(self) -> None:
        try:
            with open(VERSION_FILE, encoding="utf-8") as f:
                version = json.load(f).get("version", "?")
        except Exception:
            version = "?"
        messagebox.showinfo(
            "About PhilFlight Tracker",
            f"PhilFlight Tracker  v{version}\n\n"
            "Real-time Philippine flight monitoring\n"
            "Deal alerts from Reddit & airline promo pages\n"
            "Discord notifications via webhook\n"
            "Powered by OpenSky Network.\n\n"
            "© 2026",
            parent=self._root,
        )

    def _on_close(self) -> None:
        if self._tracker:
            self._tracker.stop()
        if self._updater:
            self._updater.stop()
        if self._deal_monitor:
            self._deal_monitor.stop()
        if self._price_tracker:
            self._price_tracker.stop()
        self._root.destroy()
