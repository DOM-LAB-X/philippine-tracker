"""
Shared UI widgets: AirportEntry autocomplete, DatePicker calendar, time helpers.
"""
import calendar
import json
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from typing import Callable, List, Optional

import customtkinter as ctk

# ── Palette (imported here so widgets match the app theme) ──────────────────
PURPLE   = "#7c3aed"
LAVENDER = "#a78bfa"
CARD     = "#141228"
BORDER   = "#2d2850"
TEXT     = "#ede9fe"
SUBTEXT  = "#8b7ec8"
BG       = "#080812"

# ── Airport database ─────────────────────────────────────────────────────────
_AIRPORTS: list = []


def _load_airports() -> list:
    global _AIRPORTS
    if _AIRPORTS:
        return _AIRPORTS
    path = Path(__file__).parent.parent / "data" / "airports.json"
    try:
        with open(path, encoding="utf-8") as f:
            _AIRPORTS = json.load(f)
    except Exception:
        _AIRPORTS = []
    return _AIRPORTS


def search_airports(query: str, max_results: int = 8) -> List[dict]:
    if not query:
        return []
    q = query.upper().strip()
    airports = _load_airports()
    results = []
    for a in airports:
        if (
            a["iata"].startswith(q)
            or a.get("icao", "").startswith(q)
            or q in a["name"].upper()
            or q in a["city"].upper()
            or q in a["country"].upper()
        ):
            results.append(a)
        if len(results) >= max_results:
            break
    return results


def airport_label(a: dict) -> str:
    return f"{a['iata']}  —  {a['city']}, {a['country']}  ({a['name']})"


def iata_to_icao(iata: str) -> str:
    for a in _load_airports():
        if a["iata"].upper() == iata.upper():
            return a.get("icao", iata)
    return iata


# ── Time helpers ──────────────────────────────────────────────────────────────

def fmt_time(unix_ts) -> str:
    """Unix timestamp → '2:34 PM'"""
    if unix_ts is None:
        return "—"
    try:
        t = datetime.fromtimestamp(int(unix_ts))
        h = t.hour % 12 or 12
        return f"{h}:{t.strftime('%M')} {('AM', 'PM')[t.hour >= 12]}"
    except Exception:
        return "—"


def fmt_datetime(unix_ts) -> str:
    """Unix timestamp → 'Aug 22, 2:34 PM'"""
    if unix_ts is None:
        return "—"
    try:
        t = datetime.fromtimestamp(int(unix_ts))
        h = t.hour % 12 or 12
        ampm = ("AM", "PM")[t.hour >= 12]
        day = t.day
        return t.strftime(f"%b {day},  {h}:%M {ampm}")
    except Exception:
        return "—"


def fmt_iso_time(iso_str: str) -> str:
    """ISO 8601 datetime string → '2:34 PM'"""
    if not iso_str or "T" not in iso_str:
        return iso_str or "—"
    try:
        t = datetime.fromisoformat(iso_str)
        h = t.hour % 12 or 12
        return f"{h}:{t.strftime('%M')} {('AM', 'PM')[t.hour >= 12]}"
    except Exception:
        return iso_str[11:16] if len(iso_str) > 15 else "—"


# ── AirportEntry ──────────────────────────────────────────────────────────────

class AirportEntry(ctk.CTkFrame):
    """Text entry with live airport-search dropdown."""

    _DROPDOWN_H = 220

    def __init__(
        self,
        parent,
        placeholder: str = "Airport or city",
        on_select: Optional[Callable[[dict], None]] = None,
        width: int = 220,
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._on_select = on_select
        self._selected: Optional[dict] = None
        self._dropdown: Optional[tk.Toplevel] = None
        self._listbox:  Optional[tk.Listbox]  = None
        self._matches:  List[dict]             = []

        self._var = tk.StringVar()
        self._entry = ctk.CTkEntry(
            self, textvariable=self._var,
            placeholder_text=placeholder, width=width,
        )
        self._entry.pack(fill="x")

        self._var.trace_add("write", self._on_type)
        self._entry.bind("<Down>",     self._focus_list)
        self._entry.bind("<Escape>",   lambda _: self._close_dropdown())
        self._entry.bind("<FocusOut>", self._on_focus_out)

    def get(self) -> str:
        return self._var.get().strip().upper()

    def set(self, value: str) -> None:
        self._var.set(value)

    @property
    def selected_airport(self) -> Optional[dict]:
        return self._selected

    def _on_type(self, *_) -> None:
        self._selected = None
        self._matches  = search_airports(self._var.get())
        if self._matches:
            self._open_dropdown()
        else:
            self._close_dropdown()

    def _open_dropdown(self) -> None:
        if self._dropdown:
            self._populate_list()
            return
        self._dropdown = tk.Toplevel(self._entry)
        self._dropdown.wm_overrideredirect(True)
        self._dropdown.configure(bg="#1a1835")

        self._listbox = tk.Listbox(
            self._dropdown,
            bg="#1a1835", fg=TEXT,
            selectbackground=PURPLE, selectforeground="white",
            activestyle="none", relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 11),
            height=7, borderwidth=0,
        )
        self._listbox.pack(fill="both", expand=True, padx=1, pady=1)
        self._listbox.bind("<ButtonRelease-1>", self._on_pick)
        self._listbox.bind("<Return>",          self._on_pick)
        self._listbox.bind("<Escape>",          lambda _: self._close_dropdown())
        self._listbox.bind("<Up>",              self._list_up)

        self._populate_list()
        self._position_dropdown()

    def _populate_list(self) -> None:
        if not self._listbox:
            return
        self._listbox.delete(0, tk.END)
        for a in self._matches:
            self._listbox.insert(tk.END, f"  {airport_label(a)}")

    def _position_dropdown(self) -> None:
        if not self._dropdown:
            return
        self._entry.update_idletasks()
        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height()
        w = max(self._entry.winfo_width(), 420)
        self._dropdown.geometry(f"{w}x{self._DROPDOWN_H}+{x}+{y}")

    def _close_dropdown(self) -> None:
        if self._dropdown:
            self._dropdown.destroy()
            self._dropdown = None
            self._listbox  = None

    def _on_pick(self, _=None) -> None:
        if not self._listbox:
            return
        idx = self._listbox.curselection() or (0,)
        a = self._matches[idx[0]]
        self._selected = a
        self._var.set(a["iata"])
        self._close_dropdown()
        if self._on_select:
            self._on_select(a)

    def _focus_list(self, _=None) -> None:
        if self._listbox:
            self._listbox.focus_set()
            self._listbox.selection_set(0)

    def _list_up(self, _=None) -> None:
        if self._listbox and self._listbox.curselection() == (0,):
            self._entry.focus_set()

    def _on_focus_out(self, _=None) -> None:
        self.after(150, self._close_dropdown)


# ── DatePicker ────────────────────────────────────────────────────────────────

class DatePicker(ctk.CTkFrame):
    """
    An entry + calendar button.  Click the button to open a month calendar;
    click a day to fill the entry with that date (YYYY-MM-DD internally,
    shown as 'Aug 22, 2026').
    """

    def __init__(
        self,
        parent,
        placeholder: str = "Pick a date",
        min_date: Optional[date] = None,
        width: int = 160,
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._min_date = min_date or date.today()
        self._selected: Optional[date] = None
        self._var = tk.StringVar()

        self._entry = ctk.CTkEntry(
            self, textvariable=self._var,
            placeholder_text=placeholder,
            width=width, state="readonly",
        )
        self._entry.pack(side="left")

        ctk.CTkButton(
            self, text="📅", width=34, height=34,
            fg_color="transparent", border_width=1, border_color=BORDER,
            hover_color="#2d2850",
            command=self._open_calendar,
        ).pack(side="left", padx=(4, 0))

    def get(self) -> str:
        """Return selected date as YYYY-MM-DD, or empty string."""
        return self._selected.isoformat() if self._selected else ""

    def get_display(self) -> str:
        return self._var.get()

    def set(self, iso_date: str) -> None:
        try:
            d = date.fromisoformat(iso_date)
            self._selected = d
            self._var.set(d.strftime("%b %-d, %Y"))
        except Exception:
            try:
                # Windows-safe fallback
                d = date.fromisoformat(iso_date)
                self._selected = d
                self._var.set(d.strftime("%b %d, %Y").replace(" 0", "  "))
            except Exception:
                pass

    def _open_calendar(self) -> None:
        _CalendarPopup(self, min_date=self._min_date, callback=self._on_pick)

    def _on_pick(self, d: date) -> None:
        self._selected = d
        # Cross-platform day formatting (no leading zero)
        try:
            self._var.set(d.strftime("%b %-d, %Y"))
        except ValueError:
            self._var.set(d.strftime("%b %d, %Y").replace(" 0", "  "))


class _CalendarPopup(ctk.CTkToplevel):
    """Modal calendar popup used by DatePicker."""

    def __init__(
        self,
        parent,
        callback: Callable[[date], None],
        min_date: Optional[date] = None,
    ) -> None:
        super().__init__(parent)
        self._callback = callback
        self._min_date = min_date or date.today()
        self._today    = date.today()
        # Start on this month if min_date is this month, else min_date month
        self._view = date(self._today.year, self._today.month, 1)

        self.title("")
        self.resizable(False, False)
        self.configure(fg_color="#0e0c1c")
        self.grab_set()

        self._build()
        self._position(parent)

    def _build(self) -> None:
        # Navigation header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(
            hdr, text="‹", width=30, height=30,
            fg_color="transparent", hover_color=BORDER,
            command=self._prev,
        ).pack(side="left")
        self._title = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT
        )
        self._title.pack(side="left", expand=True)
        ctk.CTkButton(
            hdr, text="›", width=30, height=30,
            fg_color="transparent", hover_color=BORDER,
            command=self._next,
        ).pack(side="right")

        # Weekday headers
        wk = ctk.CTkFrame(self, fg_color="transparent")
        wk.pack(fill="x", padx=10)
        for d in ("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"):
            ctk.CTkLabel(
                wk, text=d, width=38,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=SUBTEXT,
            ).pack(side="left")

        # Grid frame
        self._grid = ctk.CTkFrame(self, fg_color="transparent")
        self._grid.pack(fill="both", padx=10, pady=(4, 12))
        self._refresh()

    def _refresh(self) -> None:
        for w in self._grid.winfo_children():
            w.destroy()
        self._title.configure(text=self._view.strftime("%B %Y"))

        for week in calendar.monthcalendar(self._view.year, self._view.month):
            row = ctk.CTkFrame(self._grid, fg_color="transparent")
            row.pack()
            for day in week:
                if day == 0:
                    ctk.CTkLabel(row, text="", width=38).pack(side="left", padx=1, pady=1)
                    continue
                d      = date(self._view.year, self._view.month, day)
                past   = d < self._min_date
                today  = d == self._today
                ctk.CTkButton(
                    row, text=str(day),
                    width=36, height=32,
                    corner_radius=8,
                    fg_color=PURPLE if today else "transparent",
                    hover_color=LAVENDER if not past else "transparent",
                    text_color=SUBTEXT if past else TEXT,
                    font=ctk.CTkFont(size=12),
                    state="disabled" if past else "normal",
                    command=(lambda dt=d: self._pick(dt)) if not past else None,
                ).pack(side="left", padx=1, pady=1)

    def _prev(self) -> None:
        y, m = self._view.year, self._view.month - 1
        if m < 1:
            y, m = y - 1, 12
        self._view = date(y, m, 1)
        self._refresh()

    def _next(self) -> None:
        y, m = self._view.year, self._view.month + 1
        if m > 12:
            y, m = y + 1, 1
        self._view = date(y, m, 1)
        self._refresh()

    def _pick(self, d: date) -> None:
        self._callback(d)
        self.destroy()

    def _position(self, parent) -> None:
        self.update_idletasks()
        try:
            x = parent.winfo_rootx()
            y = parent.winfo_rooty() + parent.winfo_height() + 4
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass
