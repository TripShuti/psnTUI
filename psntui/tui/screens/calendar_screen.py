from datetime import date, timedelta
from calendar import monthrange

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static, Label
from textual.containers import Horizontal, Vertical
from textual.coordinate import Coordinate
from textual import events

from rich.text import Text

from ... import db as database


_WD = ["M", "T", "W", "T", "F", "S", "S"]
_TEAL_LEVELS = ["#3abaa0", "#2a9a80", "#1a7a60", "#0d5a45"]


def _heat_color(ratio: float) -> str:
    idx = min(int(ratio * len(_TEAL_LEVELS)), len(_TEAL_LEVELS) - 1)
    return _TEAL_LEVELS[idx]


def _fmt(sec: int) -> str:
    h, m = divmod(int(sec), 3600)
    m //= 60
    if h == 0:
        return f"{m}m"
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"


class _CalendarGrid(DataTable):
    def _on_click(self, event: events.Click) -> None:
        meta = event.style.meta
        if not meta:
            return
        row_index = meta.get("row", -2)
        column_index = meta.get("column", -2)
        if row_index < 0 or column_index < 0:
            return
        if self.cursor_type != "row" and meta.get("out_of_bounds", False):
            return
        try:
            self.cursor_coordinate = Coordinate(row_index, column_index)
        except KeyError:
            return
        self._post_selected_message()
        self._scroll_cursor_into_view(animate=True)
        event.stop()


class CalendarScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    CalendarScreen {
        align: center middle;
    }
    #calendar-container {
        width: 53;
        height: auto;
        border: solid $primary;
        background: $surface;
    }
    #calendar-header {
        layout: horizontal;
        height: 3;
    }
    #calendar-title {
        width: 1fr;
        height: 3;
        content-align: center middle;
    }
    #calendar-grid {
        height: auto;
        min-height: 8;
        margin: 0 1;
    }
    #calendar-detail {
        height: auto;
        max-height: 8;
        min-height: 3;
        border-top: solid $accent;
        padding: 0 1;
        margin-top: 1;
    }
    #calendar-legend {
        height: 1;
        margin: 0 1;
        text-style: dim;
    }
    #calendar-grid {
        scrollbar-size: 0 0;
        border: none;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        today = date.today()
        self._year = today.year
        self._month = today.month
        self._daily_data: dict[str, int] = {}
        self._cell_dates: dict[tuple[int, int], str] = {}
        self._earliest: tuple[int, int] | None = None
        self._update_bounds()

    def on_mount(self) -> None:
        self._load_month()

    def compose(self) -> ComposeResult:
        with Vertical(id="calendar-container"):
            with Horizontal(id="calendar-header"):
                yield Button("◄", id="calendar-prev", variant="default")
                yield Label(id="calendar-title")
                yield Button("►", id="calendar-next", variant="default")
            yield _CalendarGrid(id="calendar-grid")
            yield Label(id="calendar-legend")
            yield Static(id="calendar-detail")

    def _update_bounds(self) -> None:
        conn = database.get_conn()
        row = conn.execute(
            "SELECT MIN(date) FROM play_delta_history"
        ).fetchone()
        if row and row[0]:
            d = date.fromisoformat(row[0])
            self._earliest = (d.year, d.month)

    def _load_month(self) -> None:
        conn = database.get_conn()
        self._daily_data = database.get_daily_play_time(conn, self._year, self._month)
        self._render_grid()
        self._render_legend()
        self.query_one("#calendar-detail", Static).update(
            "[dim]Click any day for details[/]"
        )

    def _render_grid(self) -> None:
        self.query_one("#calendar-title", Label).update(
            f"{date(self._year, self._month, 1):%B %Y}"
        )

        table = self.query_one("#calendar-grid", _CalendarGrid)
        table.clear(columns=True)
        self._cell_dates.clear()

        for d in _WD:
            table.add_column(f"[dim]{d}[/]", width=5)

        _, days_in_month = monthrange(self._year, self._month)
        start_dow = date(self._year, self._month, 1).weekday()

        max_sec = max(self._daily_data.values()) if self._daily_data else 1

        all_days: list[int | None] = []
        for _ in range(start_dow):
            all_days.append(None)
        for d in range(1, days_in_month + 1):
            all_days.append(d)
        while len(all_days) % 7 != 0:
            all_days.append(None)

        for week_idx in range(len(all_days) // 7):
            row_cells: list[str | Text] = []
            for col in range(7):
                idx = week_idx * 7 + col
                day = all_days[idx]
                if day is None:
                    row_cells.append("")
                    continue
                day_str = f"{self._year:04d}-{self._month:02d}-{day:02d}"
                sec = self._daily_data.get(day_str, 0)
                self._cell_dates[(week_idx, col)] = day_str

                if sec == 0:
                    row_cells.append(str(day))
                else:
                    ratio = sec / max_sec
                    row_cells.append(Text(str(day), style=_heat_color(ratio)))
            table.add_row(*row_cells)

        table.cursor_type = "cell"

    def _render_legend(self) -> None:
        legend = Text(" Less ")
        for c in _TEAL_LEVELS:
            legend.append("█", c)
        legend.append(" More")
        self.query_one("#calendar-legend", Label).update(legend)

    def _can_go_back(self) -> bool:
        if not self._earliest:
            return False
        return (self._year, self._month) > self._earliest

    def _can_go_forward(self) -> bool:
        today = date.today()
        return (self._year, self._month) < (today.year, today.month)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "calendar-prev":
            if not self._can_go_back():
                return
            if self._month == 1:
                self._month = 12
                self._year -= 1
            else:
                self._month -= 1
            self._load_month()
        elif event.button.id == "calendar-next":
            if not self._can_go_forward():
                return
            if self._month == 12:
                self._month = 1
                self._year += 1
            else:
                self._month += 1
            self._load_month()

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        if event.data_table.id != "calendar-grid":
            return
        day_str = self._cell_dates.get(
            (event.coordinate.row, event.coordinate.column)
        )
        if not day_str:
            return
        self._show_day_detail(day_str)

    def _show_day_detail(self, day_str: str) -> None:
        sec = self._daily_data.get(day_str, 0)
        lines = [f"  [bold]{day_str}[/]  —  {_fmt(sec)}"]

        conn = database.get_conn()
        details = database.get_daily_play_details(conn, day_str)
        if details:
            lines.append("")
            for d in details:
                lines.append(
                    f"    {d['title_name']}  [dim]({_fmt(d['delta_seconds'])})[/]"
                )

        self.query_one("#calendar-detail", Static).update("\n".join(lines))

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss()
