import tkinter as tk
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from config.settings import Settings


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, settings: Settings) -> None:
        super().__init__(parent)
        self.settings = settings
        self.title("Settings — PhilFlight Tracker")
        self.geometry("540x680")
        self.resizable(False, False)
        self.grab_set()
        self._fields: dict[str, tk.StringVar] = {}
        self._build()

    # ------------------------------------------------------------------ #

    def _build(self) -> None:
        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)
        self._scroll = scroll
        p = {"padx": 18, "pady": 4}

        ctk.CTkLabel(scroll, text="Settings", font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w", **p, pady=(16, 4)
        )

        # --- Tracking ---
        self._section(scroll, "Tracking", p)
        self._field(scroll, "departure_airport", "Default Departure Airport (ICAO, e.g. RPLL)", p)
        self._field(scroll, "arrival_airport",   "Default Arrival Airport  (blank = any)", p)
        self._field(scroll, "airline_filter",    "Airline ICAO prefix  (e.g. PAL, CEB — blank = all)", p)

        # --- Polling ---
        self._section(scroll, "Polling", p, top=14)
        ctk.CTkLabel(scroll, text="Flight check interval (minutes, 5–1440)",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", **p)
        self._poll_var = tk.StringVar(value=str(self.settings.get("poll_interval_minutes", 30)))
        ctk.CTkEntry(scroll, textvariable=self._poll_var, width=80).pack(anchor="w", **p)

        ctk.CTkLabel(scroll, text="Deal check interval (minutes, 30–1440)",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", **p)
        self._deal_poll_var = tk.StringVar(value=str(self.settings.get("deal_check_interval_minutes", 60)))
        ctk.CTkEntry(scroll, textvariable=self._deal_poll_var, width=80).pack(anchor="w", **p)

        ctk.CTkLabel(scroll, text="Minimum Reddit score to show a deal (0 = show all)",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", **p)
        self._min_score_var = tk.StringVar(value=str(self.settings.get("min_reddit_score", 5)))
        ctk.CTkEntry(scroll, textvariable=self._min_score_var, width=80).pack(anchor="w", **p)

        # --- Discord ---
        self._section(scroll, "Discord Notifications", p, top=14)
        self._field(scroll, "discord_webhook", "Webhook URL", p)

        notify_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        notify_frame.pack(anchor="w", **p)
        self._notify_flights_var = tk.BooleanVar(
            value=self.settings.get("discord_notify_flights", True)
        )
        self._notify_deals_var = tk.BooleanVar(
            value=self.settings.get("discord_notify_deals", True)
        )
        ctk.CTkCheckBox(notify_frame, text="Notify on flight updates",
                        variable=self._notify_flights_var).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(notify_frame, text="Notify on new deals",
                        variable=self._notify_deals_var).pack(side="left")

        ctk.CTkButton(scroll, text="Send test notification", width=180,
                      command=self._test_discord).pack(anchor="w", **p, pady=(6, 0))

        # --- Google Flights / Amadeus ---
        self._section(scroll, "Google Flights prices  (Amadeus API — free tier)", p, top=14)
        ctk.CTkLabel(
            scroll,
            text="Sign up free at: https://developers.amadeus.com/self-service",
            font=ctk.CTkFont(size=11), text_color=("gray40", "gray60"),
        ).pack(anchor="w", padx=p["padx"], pady=(0, 4))
        self._field(scroll, "amadeus_client_id",     "Client ID",     p)
        self._field(scroll, "amadeus_client_secret", "Client Secret", p, show="*")

        ctk.CTkLabel(scroll, text="Environment", font=ctk.CTkFont(size=12)).pack(anchor="w", **p)
        self._amadeus_env_var = tk.StringVar(value=self.settings.get("amadeus_environment", "test"))
        ctk.CTkSegmentedButton(
            scroll, values=["test", "production"], variable=self._amadeus_env_var, width=200
        ).pack(anchor="w", **p)

        ctk.CTkLabel(scroll, text="Price drop alert threshold (%)",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", **p)
        self._price_drop_var = tk.StringVar(
            value=str(self.settings.get("price_drop_threshold_pct", 10))
        )
        ctk.CTkEntry(scroll, textvariable=self._price_drop_var, width=80).pack(anchor="w", **p)

        ctk.CTkCheckBox(
            scroll, text="Notify Discord on price drops",
            variable=tk.BooleanVar(value=self.settings.get("discord_notify_price_drops", True)),
        ).pack(anchor="w", **p)
        # Store reference so _save can read it
        self._notify_price_var = tk.BooleanVar(
            value=self.settings.get("discord_notify_price_drops", True)
        )
        # Re-create the checkbox linked to the right var
        scroll.winfo_children()[-1].destroy()
        ctk.CTkCheckBox(
            scroll, text="Notify Discord on price drops",
            variable=self._notify_price_var,
        ).pack(anchor="w", **p)

        # --- Appearance ---
        self._section(scroll, "Appearance", p, top=14)
        self._theme_var = tk.StringVar(value=self.settings.get("theme", "dark"))
        ctk.CTkSegmentedButton(
            scroll, values=["dark", "light", "system"], variable=self._theme_var, width=260
        ).pack(anchor="w", **p)

        # --- GitHub ---
        self._section(scroll, "GitHub (required for auto-updates)", p, top=14)
        self._field(scroll, "github_owner", "GitHub username or organisation", p)
        self._field(scroll, "github_repo",  "Repository name", p)

        # --- OpenSky auth ---
        self._section(scroll, "OpenSky credentials  (optional — higher rate limits)", p, top=14)
        self._field(scroll, "opensky_username", "Username", p)
        self._field(scroll, "opensky_password", "Password", p, show="*")

        # Buttons
        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(fill="x", **p, pady=(20, 20))
        ctk.CTkButton(btn_row, text="Cancel", fg_color="gray40",
                      command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="Save", command=self._save).pack(side="right")

    # ------------------------------------------------------------------ #

    def _section(self, parent, label: str, p: dict, top: int = 4) -> None:
        ctk.CTkLabel(
            parent, text=label,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray40", "gray65"),
        ).pack(anchor="w", padx=p["padx"], pady=(top, 2))

    def _field(self, parent, key: str, label: str, p: dict, show: str = "") -> None:
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=12)).pack(anchor="w", **p)
        var = tk.StringVar(value=self.settings.get(key, ""))
        ctk.CTkEntry(parent, textvariable=var, show=show).pack(fill="x", **p)
        self._fields[key] = var

    # ------------------------------------------------------------------ #

    def _test_discord(self) -> None:
        url = self._fields.get("discord_webhook")
        if not url:
            messagebox.showwarning("No webhook", "Enter a Discord webhook URL first.", parent=self)
            return
        webhook = url.get().strip()
        if not webhook:
            messagebox.showwarning("No webhook", "Webhook URL is empty.", parent=self)
            return
        from notifications.discord import test_webhook
        ok = test_webhook(webhook)
        if ok:
            messagebox.showinfo("Success", "Test message sent to Discord!", parent=self)
        else:
            messagebox.showerror("Failed", "Could not reach Discord. Check the webhook URL.", parent=self)

    def _save(self) -> None:
        for key in ("departure_airport", "arrival_airport"):
            val = self._fields[key].get().strip().upper()
            if val and not self.settings.validate_icao_airport(val):
                messagebox.showerror(
                    "Invalid input",
                    f"'{val}' is not a valid 4-letter ICAO airport code (e.g. RPLL).",
                    parent=self,
                )
                return

        for name, var, lo, hi in [
            ("Flight poll interval", self._poll_var, 5, 1440),
            ("Deal poll interval",   self._deal_poll_var, 30, 1440),
            ("Min Reddit score",     self._min_score_var, 0, 10000),
        ]:
            try:
                val = int(var.get())
                if not lo <= val <= hi:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Invalid input", f"{name} must be between {lo} and {hi}.", parent=self
                )
                return

        for key, var in self._fields.items():
            val = var.get().strip()
            if key in ("departure_airport", "arrival_airport", "airline_filter"):
                val = val.upper()
            self.settings.set(key, val)

        try:
            drop_pct = int(self._price_drop_var.get())
            if not 1 <= drop_pct <= 100:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid input",
                                 "Price drop threshold must be 1–100.", parent=self)
            return

        self.settings.set("poll_interval_minutes",      int(self._poll_var.get()))
        self.settings.set("deal_check_interval_minutes", int(self._deal_poll_var.get()))
        self.settings.set("min_reddit_score",           int(self._min_score_var.get()))
        self.settings.set("price_drop_threshold_pct",   drop_pct)
        self.settings.set("amadeus_environment",        self._amadeus_env_var.get())
        self.settings.set("discord_notify_flights",     self._notify_flights_var.get())
        self.settings.set("discord_notify_deals",       self._notify_deals_var.get())
        self.settings.set("discord_notify_price_drops", self._notify_price_var.get())
        self.settings.set("theme",                      self._theme_var.get())
        self.settings.save()
        ctk.set_appearance_mode(self._theme_var.get())
        self.destroy()
