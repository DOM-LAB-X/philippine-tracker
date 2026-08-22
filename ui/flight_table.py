import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import List

import customtkinter as ctk

COLUMNS = [
    ("callsign",          "Callsign",   100, "center"),
    ("departure_airport", "From",        70, "center"),
    ("arrival_airport",   "To",          70, "center"),
    ("first_seen",        "Departed",    95, "center"),
    ("last_seen",         "Last Seen",   95, "center"),
    ("status",            "Status",      85, "center"),
    ("baro_altitude_m",   "Altitude",    90, "center"),
    ("velocity_ms",       "Speed",       85, "center"),
    ("origin_country",    "Country",    110, "w"),
]


def _unix_to_local(ts) -> str:
    if ts is None:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%H:%M:%S")
    except Exception:
        return "—"


def _m_to_ft(m) -> str:
    if m is None:
        return "—"
    return f"{int(m * 3.28084):,} ft"


def _ms_to_kts(ms) -> str:
    if ms is None:
        return "—"
    return f"{int(ms * 1.944):,} kts"


def _flight_to_row(f: dict) -> tuple:
    on_ground = f.get("on_ground")
    if on_ground is True:
        status = "On Ground"
    elif on_ground is False:
        status = "Airborne"
    else:
        status = "—"

    return (
        f.get("callsign") or "—",
        f.get("departure_airport") or "—",
        f.get("arrival_airport") or "—",
        _unix_to_local(f.get("first_seen")),
        _unix_to_local(f.get("last_seen")),
        status,
        _m_to_ft(f.get("baro_altitude_m")),
        _ms_to_kts(f.get("velocity_ms")),
        f.get("origin_country") or "—",
    )


class FlightTable(ctk.CTkFrame):
    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._sort_col: str = ""
        self._sort_desc: bool = False
        self._build()

    def _build(self) -> None:
        self._apply_style()

        col_ids = [c[0] for c in COLUMNS]
        self._tree = ttk.Treeview(
            self,
            columns=col_ids,
            show="headings",
            style="PhilFlight.Treeview",
            selectmode="browse",
        )
        for col_id, label, width, anchor in COLUMNS:
            self._tree.heading(
                col_id,
                text=label,
                command=lambda c=col_id: self._on_header_click(c),
            )
            self._tree.column(col_id, width=width, minwidth=50, anchor=anchor)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._empty = ctk.CTkLabel(
            self,
            text="No flights found. Adjust filters or wait for the next refresh.",
            font=ctk.CTkFont(size=13),
            text_color=("gray50", "gray60"),
        )

    def update_flights(self, flights: List[dict]) -> None:
        for iid in self._tree.get_children():
            self._tree.delete(iid)

        if not flights:
            self._empty.place(relx=0.5, rely=0.5, anchor="center")
            return

        self._empty.place_forget()
        for i, f in enumerate(flights):
            tag = "even" if i % 2 == 0 else "odd"
            self._tree.insert("", "end", iid=str(i), values=_flight_to_row(f), tags=(tag,))

        self._tree.tag_configure("even", background="#1e1e2e")
        self._tree.tag_configure("odd", background="#252538")

    def _on_header_click(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = False

        items = [
            (self._tree.set(iid, col), iid) for iid in self._tree.get_children()
        ]
        items.sort(reverse=self._sort_desc, key=lambda x: x[0].lower())
        for idx, (_, iid) in enumerate(items):
            self._tree.move(iid, "", idx)

    @staticmethod
    def _apply_style() -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "PhilFlight.Treeview",
            background="#1e1e2e",
            foreground="#cdd6f4",
            fieldbackground="#1e1e2e",
            rowheight=28,
            font=("Segoe UI", 11),
            borderwidth=0,
        )
        style.configure(
            "PhilFlight.Treeview.Heading",
            background="#313244",
            foreground="#cdd6f4",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
        )
        style.map(
            "PhilFlight.Treeview",
            background=[("selected", "#585b70")],
            foreground=[("selected", "#ffffff")],
        )
