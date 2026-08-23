"""
Shared UI widgets: AirportEntry autocomplete, DatePicker calendar, time helpers.

Calendar uses tk.Toplevel (not CTkToplevel) to avoid grab_set() crashes.
Date formatting is cross-platform (no strftime %-d which breaks on Windows).
"""
import calendar
import json
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from typing import Callable, List, Optional

import customtkinter as ctk

# ── Palette ──────────────────────────────────────────────────────────────────
PURPLE   = "#7c3aed"
LAVENDER = "#a78bfa"
CARD     = "#141228"
CARD_ALT = "#1a1835"
BORDER   = "#2d2850"
SIDEBAR  = "#0e0c1c"
TEXT     = "#ede9fe"
SUBTEXT  = "#8b7ec8"
BG       = "#080812"

# ── Airline database ─────────────────────────────────────────────────────────
AIRLINES_DB: list[dict] = [
    {"code": "PR",  "alias": "PAL", "name": "Philippine Airlines"},
    {"code": "5J",  "alias": "CEB", "name": "Cebu Pacific"},
    {"code": "Z2",  "alias": "APA", "name": "AirAsia Philippines"},
    {"code": "DG",  "alias": "PAX", "name": "PAL Express"},
    {"code": "JL",  "alias": "JAL", "name": "Japan Airlines"},
    {"code": "NH",  "alias": "ANA", "name": "All Nippon Airways"},
    {"code": "KE",  "alias": "KAL", "name": "Korean Air"},
    {"code": "OZ",  "alias": "AAR", "name": "Asiana Airlines"},
    {"code": "SQ",  "alias": "SIA", "name": "Singapore Airlines"},
    {"code": "CX",  "alias": "CPA", "name": "Cathay Pacific"},
    {"code": "EK",  "alias": "UAE", "name": "Emirates"},
    {"code": "QR",  "alias": "QTR", "name": "Qatar Airways"},
    {"code": "EY",  "alias": "ETD", "name": "Etihad Airways"},
    {"code": "TG",  "alias": "THA", "name": "Thai Airways"},
    {"code": "MH",  "alias": "MAS", "name": "Malaysia Airlines"},
    {"code": "GA",  "alias": "GIA", "name": "Garuda Indonesia"},
    {"code": "CI",  "alias": "CAL", "name": "China Airlines"},
    {"code": "BR",  "alias": "EVA", "name": "EVA Air"},
    {"code": "UA",  "alias": "UAL", "name": "United Airlines"},
    {"code": "AA",  "alias": "AAL", "name": "American Airlines"},
    {"code": "DL",  "alias": "DAL", "name": "Delta Air Lines"},
    {"code": "HA",  "alias": "HAL", "name": "Hawaiian Airlines"},
    {"code": "CZ",  "alias": "CSN", "name": "China Southern"},
    {"code": "MU",  "alias": "CES", "name": "China Eastern"},
    {"code": "CA",  "alias": "CCA", "name": "Air China"},
    {"code": "VN",  "alias": "HVN", "name": "Vietnam Airlines"},
    {"code": "VJ",  "alias": "VJC", "name": "VietJet Air"},
    {"code": "TR",  "alias": "TGW", "name": "Scoot"},
    {"code": "AK",  "alias": "AXM", "name": "AirAsia"},
    {"code": "D7",  "alias": "XAX", "name": "AirAsia X"},
]


def search_airlines(query: str, max_results: int = 8) -> list[dict]:
    """Match query against IATA code, alias, or airline name."""
    if not query:
        return []
    q = query.upper().strip()
    exact, partial = [], []
    for a in AIRLINES_DB:
        if a["code"] == q or a["alias"] == q:
            exact.append(a)
        elif (
            a["code"].startswith(q)
            or a["alias"].startswith(q)
            or q in a["name"].upper()
        ):
            partial.append(a)
    return (exact + partial)[:max_results]


def airline_label(a: dict) -> str:
    return f"{a['alias']}  —  {a['name']}  ({a['code']})"


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
    """Match query against IATA, ICAO, airport name, city, or country."""
    if not query:
        return []
    q = query.upper().strip()
    airports = _load_airports()
    exact, partial = [], []
    for a in airports:
        if a["iata"] == q or a.get("icao", "") == q:
            exact.append(a)
        elif (
            a["iata"].startswith(q)
            or q in a["name"].upper()
            or q in a["city"].upper()
            or q in a["country"].upper()
        ):
            partial.append(a)
    results = (exact + partial)[:max_results]
    return results


def airport_label(a: dict) -> str:
    return f"{a['iata']}  —  {a['city']}, {a['country']}  ({a['name']})"


def iata_to_icao(iata: str) -> str:
    for a in _load_airports():
        if a["iata"].upper() == iata.upper():
            return a.get("icao", iata)
    return iata


# ── Time helpers ──────────────────────────────────────────────────────────────

def _day_str(d: date) -> str:
    """Cross-platform: 'Nov 14, 2026' without leading zero, any OS."""
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def fmt_time(unix_ts) -> str:
    if unix_ts is None:
        return "—"
    try:
        t = datetime.fromtimestamp(int(unix_ts))
        h = t.hour % 12 or 12
        return f"{h}:{t.strftime('%M')} {('AM', 'PM')[t.hour >= 12]}"
    except Exception:
        return "—"


def fmt_iso_time(iso_str: str) -> str:
    """'2026-11-14T14:30:00'  →  '2:30 PM'"""
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

    _DROPDOWN_H = 230

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

        self._suppress: bool = False

        self._var.trace_add("write", self._on_type)
        self._entry.bind("<Down>",     self._focus_list)
        self._entry.bind("<Escape>",   lambda _: self._close_dropdown())
        self._entry.bind("<FocusOut>", self._on_focus_out)

    def get(self) -> str:
        return self._var.get().strip().upper()

    def set(self, value: str) -> None:
        """Set value programmatically without opening the autocomplete dropdown."""
        self._suppress = True
        self._var.set(value)
        self._suppress = False
        self._close_dropdown()

    @property
    def selected_airport(self) -> Optional[dict]:
        return self._selected

    def _on_type(self, *_) -> None:
        if self._suppress:
            return
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
        root = self._entry.winfo_toplevel()
        self._dropdown = tk.Toplevel(root)
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
        w = max(self._entry.winfo_width(), 440)
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
        self.after(180, self._close_dropdown)


# ── AirlineEntry ─────────────────────────────────────────────────────────────

class AirlineEntry(ctk.CTkFrame):
    """
    Multi-select airline autocomplete.

    Works like AirportEntry but supports comma-separated multiple airlines:
      • Type 'JAL' → dropdown shows Japan Airlines
      • Select → entry shows 'JAL'
      • Type ', A' → dropdown filters on 'A' → select ANA → 'JAL, ANA'

    get() returns the raw text (e.g. 'JAL, ANA, PAL').
    Use resolve_airline_codes() from api.amadeus to convert to IATA codes.
    """

    _DROPDOWN_H = 220

    def __init__(
        self,
        parent,
        placeholder: str = "e.g. JAL, ANA, PAL",
        width: int = 220,
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._dropdown:  Optional[tk.Toplevel] = None
        self._listbox:   Optional[tk.Listbox]  = None
        self._matches:   list                  = []
        self._suppress:  bool                  = False  # blocks dropdown on programmatic set

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
        return self._var.get().strip()

    def set(self, value: str) -> None:
        """Set value programmatically without opening the autocomplete dropdown."""
        self._suppress = True
        self._var.set(value)
        self._suppress = False
        self._close_dropdown()

    def clear(self) -> None:
        self._suppress = True
        self._var.set("")
        self._suppress = False
        self._close_dropdown()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _current_token(self) -> str:
        """Return the token the user is currently typing (after last comma)."""
        parts = self._var.get().split(",")
        return parts[-1].strip()

    def _on_type(self, *_) -> None:
        if self._suppress:
            return
        token = self._current_token()
        self._matches = search_airlines(token) if token else []
        if self._matches:
            self._open_dropdown()
        else:
            self._close_dropdown()

    def _open_dropdown(self) -> None:
        if self._dropdown:
            self._populate_list()
            return
        root = self._entry.winfo_toplevel()
        self._dropdown = tk.Toplevel(root)
        self._dropdown.wm_overrideredirect(True)
        self._dropdown.configure(bg="#1a1835")

        self._listbox = tk.Listbox(
            self._dropdown,
            bg="#1a1835", fg=TEXT,
            selectbackground=PURPLE, selectforeground="white",
            activestyle="none", relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 11),
            height=6, borderwidth=0,
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
            self._listbox.insert(tk.END, f"  {airline_label(a)}")

    def _position_dropdown(self) -> None:
        if not self._dropdown:
            return
        self._entry.update_idletasks()
        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height()
        w = max(self._entry.winfo_width(), 380)
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
        chosen = self._matches[idx[0]]

        # Replace only the current (last) token, keep previous selections
        existing = self._var.get()
        parts = [p.strip() for p in existing.split(",")]
        parts[-1] = chosen["alias"]          # use the familiar 3-letter name
        self._var.set(", ".join(p for p in parts if p))
        self._close_dropdown()
        # Move cursor to end of entry
        self._entry.after(10, lambda: self._entry.icursor(tk.END))

    def _focus_list(self, _=None) -> None:
        if self._listbox:
            self._listbox.focus_set()
            self._listbox.selection_set(0)

    def _list_up(self, _=None) -> None:
        if self._listbox and self._listbox.curselection() == (0,):
            self._entry.focus_set()

    def _on_focus_out(self, _=None) -> None:
        self.after(180, self._close_dropdown)


# ── DatePicker ────────────────────────────────────────────────────────────────

class DatePicker(ctk.CTkFrame):
    """
    Read-only display entry + 📅 button that opens a stable calendar popup.

    Bug fixes vs prior version:
    - Uses tk.Toplevel (not CTkToplevel) — avoids grab_set() crashes
    - No grab_set() at all — closes on FocusOut instead
    - Cross-platform date display (no strftime %-d)
    - Entry uses state="normal" so StringVar updates always render
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
        self._min_date  = min_date or date.today()
        self._selected: Optional[date] = None
        self._var = tk.StringVar()

        # state="normal" is required — readonly prevents StringVar from
        # updating the visual display in some customtkinter versions
        self._entry = ctk.CTkEntry(
            self, textvariable=self._var,
            placeholder_text=placeholder,
            width=width,
        )
        self._entry.pack(side="left")

        ctk.CTkButton(
            self, text="📅", width=36, height=34,
            fg_color="transparent",
            border_width=1, border_color=BORDER,
            hover_color=BORDER,
            command=self._open_calendar,
        ).pack(side="left", padx=(4, 0))

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self) -> str:
        """Return selected date as YYYY-MM-DD, or '' if nothing selected."""
        # Also accept typed ISO dates
        raw = self._var.get().strip()
        if self._selected:
            return self._selected.isoformat()
        # Try to parse typed text
        for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                from datetime import datetime as _dt
                d = _dt.strptime(raw, fmt).date()
                self._selected = d
                return d.isoformat()
            except ValueError:
                pass
        return ""

    def set(self, iso_date: str) -> None:
        """Populate from a YYYY-MM-DD string."""
        try:
            d = date.fromisoformat(iso_date)
            self._selected = d
            self._var.set(_day_str(d))
        except Exception:
            pass

    def clear(self) -> None:
        self._selected = None
        self._var.set("")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _open_calendar(self) -> None:
        _CalendarPopup(self, callback=self._on_pick, min_date=self._min_date)

    def _on_pick(self, d: date) -> None:
        self._selected = d
        self._var.set(_day_str(d))


# ── Calendar popup (tk.Toplevel — no CTkToplevel, no grab_set) ───────────────

class _CalendarPopup(tk.Toplevel):
    """
    Borderless calendar dropdown.

    Why tk.Toplevel and not CTkToplevel:
      CTkToplevel + grab_set() can freeze / crash the parent app on Windows
      because grab_set() intercepts all input globally. Using tk.Toplevel
      with FocusOut-based closing is stable on all platforms.
    """

    # Colours (plain tk — not customtkinter)
    _BG       = "#0e0c1c"
    _CARD     = "#141228"
    _BORDER   = "#2d2850"
    _PURPLE   = "#7c3aed"
    _LAVENDER = "#a78bfa"
    _TEXT     = "#ede9fe"
    _DIM      = "#8b7ec8"
    _TODAY_FG = "#ffffff"

    def __init__(
        self,
        parent,
        callback: Callable[[date], None],
        min_date: Optional[date] = None,
    ) -> None:
        # Attach to the true Tk root so the popup stays on top
        root = parent.winfo_toplevel()
        super().__init__(root)

        self._callback = callback
        self._min_date = min_date or date.today()
        self._today    = date.today()
        self._view     = date(self._today.year, self._today.month, 1)

        self.wm_overrideredirect(True)          # borderless
        self.configure(bg=self._BORDER)         # 1-px purple border effect

        self._build()
        self._position(parent)

        # Close when focus leaves — delay 200ms to avoid
        # immediately closing if a child widget gets focus
        self.bind("<FocusOut>", lambda _: self.after(200, self._check_close))
        # Escape closes only this popup, not the whole app (bind not bind_all)
        self.bind("<Escape>", lambda _: self._safe_destroy())
        # Set focus so FocusOut fires when user clicks elsewhere
        self.after(50, self.focus_set)

    # ── Build ─────────────────────────────────────────────────────────────────

    # Sunday-first calendar — fixes day-of-week column alignment
    _CAL = calendar.Calendar(firstweekday=6)

    def _build(self) -> None:
        inner = tk.Frame(self, bg=self._BG, padx=10, pady=10)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        # Navigation header
        nav = tk.Frame(inner, bg=self._BG)
        nav.pack(fill="x", pady=(0, 6))

        self._prev_btn = tk.Button(
            nav, text="‹", width=3,
            bg=self._BG, fg=self._TEXT,
            activebackground=self._BORDER, activeforeground=self._TEXT,
            relief="flat", bd=0, cursor="hand2",
            command=self._prev,
        )
        self._prev_btn.pack(side="left")

        self._title = tk.Label(
            nav, text="",
            bg=self._BG, fg=self._TEXT,
            font=("Segoe UI", 12, "bold"),
        )
        self._title.pack(side="left", expand=True)

        tk.Button(
            nav, text="›", width=3,
            bg=self._BG, fg=self._TEXT,
            activebackground=self._BORDER, activeforeground=self._TEXT,
            relief="flat", bd=0, cursor="hand2",
            command=self._next,
        ).pack(side="right")

        # Weekday header (Sunday-first to match _CAL)
        wk = tk.Frame(inner, bg=self._BG)
        wk.pack(fill="x", pady=(0, 2))
        for label in ("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"):
            tk.Label(
                wk, text=label, width=4,
                bg=self._BG, fg=self._DIM,
                font=("Segoe UI", 9),
            ).pack(side="left")

        # Day grid
        self._grid = tk.Frame(inner, bg=self._BG)
        self._grid.pack(fill="both")

        self._refresh()

    def _refresh(self) -> None:
        for w in self._grid.winfo_children():
            w.destroy()

        self._title.configure(text=self._view.strftime("%B %Y"))

        # Disable ‹ if already at the earliest selectable month
        today_first = date(self._today.year, self._today.month, 1)
        self._prev_btn.configure(
            state="disabled" if self._view <= today_first else "normal",
            fg=self._DIM if self._view <= today_first else self._TEXT,
        )

        # Use Sunday-first calendar (fixes day-of-week column alignment)
        for week in self._CAL.monthdayscalendar(self._view.year, self._view.month):
            row = tk.Frame(self._grid, bg=self._BG)
            row.pack(anchor="w")
            for day in week:
                if day == 0:
                    tk.Label(row, text="", width=4, bg=self._BG).pack(
                        side="left", padx=2, pady=2)
                    continue
                d       = date(self._view.year, self._view.month, day)
                past    = d < self._min_date
                today   = d == self._today
                bg      = self._PURPLE if today else self._BG
                fg      = self._TODAY_FG if today else (self._DIM if past else self._TEXT)
                hover   = self._LAVENDER
                cursor  = "arrow" if past else "hand2"
                state   = "disabled" if past else "normal"

                btn = tk.Button(
                    row,
                    text=str(day),
                    width=3,
                    bg=bg, fg=fg,
                    activebackground=hover,
                    activeforeground=self._BG,
                    relief="flat", bd=0,
                    padx=2, pady=4,
                    font=("Segoe UI", 11),
                    cursor=cursor,
                    state=state,
                )
                if not past:
                    btn.configure(command=lambda dt=d: self._pick(dt))
                btn.pack(side="left", padx=2, pady=2)

    # ── Helpers ───────────────────────────────────────────────────────────────

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
        self._safe_destroy()

    def _check_close(self) -> None:
        """Destroy only if focus has truly left this window.

        Walks the widget.master chain instead of comparing string names,
        which is more reliable across tkinter versions.
        """
        try:
            focused = self.focus_get()
            if focused is None:
                self._safe_destroy()
                return
            # Walk up the hierarchy to see if focused widget is inside us
            w = focused
            while w is not None:
                if w is self:
                    return  # focus still inside popup — keep open
                try:
                    w = w.master
                except Exception:
                    break
            self._safe_destroy()
        except Exception:
            self._safe_destroy()

    def _safe_destroy(self) -> None:
        try:
            self.destroy()
        except Exception:
            pass

    def _position(self, parent) -> None:
        self.update_idletasks()
        try:
            x = parent.winfo_rootx()
            y = parent.winfo_rooty() + parent.winfo_height() + 2
            w = self.winfo_reqwidth()
            h = self.winfo_reqheight()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            if x + w > sw:
                x = sw - w - 8
            if y + h > sh:
                y = parent.winfo_rooty() - h - 2
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass
