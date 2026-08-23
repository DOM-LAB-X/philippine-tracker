"""
Shared UI widgets and helpers.
"""
import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

import customtkinter as ctk

# ── Airport database ────────────────────────────────────────────────────────

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
    """Return airports matching query against IATA, ICAO, name, or city."""
    if not query or len(query) < 1:
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


# ── Time formatting ─────────────────────────────────────────────────────────

def fmt_time(unix_ts) -> str:
    """Convert Unix timestamp to 12-hour time string, e.g. '2:34 PM'."""
    if unix_ts is None:
        return "—"
    try:
        t = datetime.fromtimestamp(int(unix_ts))
        h = t.hour % 12 or 12
        return f"{h}:{t.strftime('%M')} {('AM','PM')[t.hour >= 12]}"
    except Exception:
        return "—"


def fmt_datetime(unix_ts) -> str:
    """e.g. 'Aug 22, 3:05 PM'"""
    if unix_ts is None:
        return "—"
    try:
        t = datetime.fromtimestamp(int(unix_ts))
        h = t.hour % 12 or 12
        ampm = ("AM", "PM")[t.hour >= 12]
        return t.strftime(f"%b %-d,  {h}:%M {ampm}")
    except Exception:
        try:
            # Windows-compatible (no %-d)
            t = datetime.fromtimestamp(int(unix_ts))
            h = t.hour % 12 or 12
            ampm = ("AM", "PM")[t.hour >= 12]
            return t.strftime(f"%b %d,  {h}:%M {ampm}").replace(" 0", "  ")
        except Exception:
            return "—"


# ── AirportEntry widget ─────────────────────────────────────────────────────

class AirportEntry(ctk.CTkFrame):
    """
    A text entry that shows a live dropdown of matching airports as you type.
    Selecting an airport fills the entry with the IATA code and stores the
    full airport dict via the on_select callback.
    """

    _DROPDOWN_HEIGHT = 200

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
        self._listbox: Optional[tk.Listbox] = None
        self._matches: List[dict] = []

        self._var = tk.StringVar()
        self._entry = ctk.CTkEntry(
            self, textvariable=self._var, placeholder_text=placeholder, width=width
        )
        self._entry.pack(fill="x")

        self._var.trace_add("write", self._on_type)
        self._entry.bind("<Down>",    self._focus_list)
        self._entry.bind("<Escape>",  lambda _: self._close_dropdown())
        self._entry.bind("<FocusOut>", self._on_focus_out)

    # ── Public ──────────────────────────────────────────────────────────

    def get(self) -> str:
        return self._var.get().strip().upper()

    def set(self, value: str) -> None:
        self._var.set(value)

    @property
    def selected_airport(self) -> Optional[dict]:
        return self._selected

    # ── Internal ─────────────────────────────────────────────────────────

    def _on_type(self, *_) -> None:
        text = self._var.get()
        self._selected = None
        self._matches = search_airports(text)
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
        self._dropdown.configure(bg="#21262d")

        self._listbox = tk.Listbox(
            self._dropdown,
            bg="#21262d",
            fg="#e6edf3",
            selectbackground="#0038A8",
            selectforeground="white",
            activestyle="none",
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 11),
            height=6,
            borderwidth=0,
        )
        self._listbox.pack(fill="both", expand=True, padx=1, pady=1)
        self._listbox.bind("<ButtonRelease-1>", self._on_pick)
        self._listbox.bind("<Return>",          self._on_pick)
        self._listbox.bind("<Escape>",          lambda _: self._close_dropdown())
        self._listbox.bind("<Up>", self._list_up)

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
        w = self._entry.winfo_width()
        self._dropdown.geometry(f"{w}x{self._DROPDOWN_HEIGHT}+{x}+{y}")

    def _close_dropdown(self) -> None:
        if self._dropdown:
            self._dropdown.destroy()
            self._dropdown = None
            self._listbox = None

    def _on_pick(self, _=None) -> None:
        if not self._listbox:
            return
        idx = self._listbox.curselection()
        if not idx:
            idx = (0,)
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
