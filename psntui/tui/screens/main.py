from datetime import datetime, date, timedelta
from calendar import monthrange

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Label, Static
from textual.containers import Container, Horizontal, VerticalScroll
from textual.coordinate import Coordinate
from textual import events

from rich.text import Text

from ... import db as database


class HeatmapTable(DataTable):
    def _set_hover(self, show: bool) -> None:
        if hasattr(self, "_set_hover_cursor"):
            self._set_hover_cursor(show)

    def _on_mouse_move(self, event: events.MouseMove) -> None:
        meta = event.style.meta
        if not meta:
            self._set_hover(False)
            return
        row_index = meta.get("row", -2)
        column_index = meta.get("column", -2)
        if row_index < 0 or column_index < 0 or column_index == 0:
            self._set_hover(False)
            return
        self._set_hover(True)
        if self.cursor_type != "row" and meta.get("out_of_bounds", False):
            self._set_hover(False)
            return
        if self.show_cursor and self.cursor_type != "none":
            try:
                self.hover_coordinate = Coordinate(row_index, column_index)
            except KeyError:
                pass

    def _on_click(self, event: events.Click) -> None:
        meta = event.style.meta
        if "row" not in meta or "column" not in meta:
            return
        if self.cursor_type != "row" and meta.get("out_of_bounds", False):
            return

        row_index = meta["row"]
        column_index = meta["column"]

        if row_index < 0 or column_index < 0 or column_index == 0:
            return

        self.cursor_coordinate = Coordinate(row_index, column_index)
        self._post_selected_message()
        self._scroll_cursor_into_view(animate=True)
        event.stop()

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def _heat_color(ratio: float) -> str:
    """Teal intensity scale: lighter -> darker = more activity."""
    levels = ["#3abaa0", "#2a9a80", "#1a7a60", "#0d5a45"]
    idx = min(int(ratio * len(levels)), len(levels) - 1)
    return levels[idx]


class MainScreen(Screen):
    CSS = """
    .main-horizontal {
        layout: horizontal;
        height: 1fr;
    }
    #games-card {
        width: 1fr;
        height: 1fr;
        border: solid $primary;
    }
    #games-table {
        height: 1fr;
    }
    .right-panel {
        width: 1fr;
        height: 1fr;
    }
    #recent-card, #heatmap-card, #month-card, #rarity-card {
        border: solid $primary;
    }
    #recent-card {
        height: 13;
        margin-bottom: 1;
    }
    #heatmap-card, #month-card, #rarity-card {
        height: auto;
        margin-bottom: 1;
    }
    #heatmap {
        height: 9;
    }
    #heatmap-legend {
        margin: 0 1;
        margin-bottom: 1;
        text-style: dim;
    }
    #day-detail-scroll {
        height: 6;
        max-height: 6;
        margin: 0 1;
        margin-bottom: 1;
        border: none;
        overflow-y: auto;
        scrollbar-size: 0 0;
    }
    #day-detail-scroll.active {
        border: solid $primary;
    }
    #day-detail {
        padding: 0 1;
    }
    DataTable {
        scrollbar-size: 0 0;
    }
    .compare-card {
        padding: 0 1;
        height: auto;
    }
    #rarity-dist {
        height: auto;
    }
    .rarity-row {
        layout: horizontal;
        height: auto;
        margin: 0 1;
    }
    .rarity-label {
        width: 12;
    }
    .rarity-bar-bg {
        width: 1fr;
        height: 1;
    }
    .rarity-bar-fg {
        color: $accent;
    }
    .rarity-count {
        width: 8;
        text-align: right;
    }
    #search-overlay {
        dock: top;
        height: auto;
        border: solid $accent;
        background: $surface;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._games: list = []
        self._search_active = False

    def on_mount(self) -> None:
        self.query_one("#games-card").border_title = "GAMES"
        self.query_one("#recent-card").border_title = "RECENT"
        self.query_one("#heatmap-card").border_title = "WEEKLY ACTIVITY"
        self.query_one("#month-card").border_title = "MONTH"
        self.query_one("#rarity-card").border_title = "RARITY"

    def compose(self) -> ComposeResult:
        with Horizontal(classes="main-horizontal"):
            with Container(id="games-card"):
                yield DataTable(id="games-table")
            with VerticalScroll(classes="right-panel"):
                with Container(id="recent-card"):
                    yield DataTable(id="recent-table")
                with Container(id="heatmap-card"):
                    yield HeatmapTable(id="heatmap")
                    yield Label(id="heatmap-legend")
                    with VerticalScroll(id="day-detail-scroll"):
                        yield Static(id="day-detail")
                with Container(id="month-card"):
                    yield Container(id="month-compare", classes="compare-card")
                with Container(id="rarity-card"):
                    yield Container(id="rarity-dist")

    def on_screen_resume(self) -> None:
        try:
            self._load_data()
        except Exception as e:
            self.app.notify(f"Load error: {e}", severity="error")

    def _load_data(self) -> None:
        conn = database.get_conn()
        self._load_games(conn)
        self._load_recent(conn)
        self._render_heatmap(conn)
        self._render_month_compare(conn)
        self._render_rarity(conn)

    def _load_games(self, conn) -> None:
        self._games = database.get_games(conn)
        self._render_games_table()

    def _render_games_table(self) -> None:
        table = self.query_one("#games-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Platform", "Progress", "P", "G", "S", "B", "Last Trophy")

        for g in self._games:
            plat = g["platform"] or "–"
            progress = f"{g['progress']}%" if g["progress"] is not None else "–%"
            last = "–"
            if g["last_updated_datetime"]:
                last = g["last_updated_datetime"][:10]
            plat_count = g["earned_platinum"]
            if plat_count > 0:
                plat_display = Text(str(plat_count), style="bold #b0b0e0")
            else:
                plat_display = str(plat_count)
            table.add_row(
                g["title_name"], plat, progress,
                plat_display, str(g["earned_gold"]),
                str(g["earned_silver"]), str(g["earned_bronze"]),
                last,
            )

        if not self._games:
            table.add_rows([["No games synced yet", "", "", "", "", "", "", ""]])

        table.cursor_type = "row"
        self._search_active = False

    def _show_search(self) -> None:
        if self._search_active:
            return
        self._search_active = True
        from textual.widgets import Input
        search = Container(
            Input(placeholder="Filter games…", id="game-search"),
            id="search-overlay",
        )
        self.mount(search, before=0)
        self.query_one("#game-search", Input).focus()

    def _dismiss_search(self) -> None:
        self._search_active = False
        try:
            overlay = self.query_one("#search-overlay")
            overlay.remove()
        except Exception:
            pass
        self.query_one("#games-table", DataTable).focus()

    def _filter_games(self, query: str) -> None:
        if not query:
            return
        for i, g in enumerate(self._games):
            if query.lower() in g["title_name"].lower():
                table = self.query_one("#games-table", DataTable)
                table.move_cursor(row=i, column=0)
                self.app.notify(f"→ {g['title_name']}")
                return
        self.app.notify(f"No game matches '{query}'", severity="warning")

    def on_input_submitted(self, event) -> None:
        if event.input.id == "game-search":
            event.stop()
            query = event.value.strip()
            self._filter_games(query)
            self._dismiss_search()

    def on_key(self, event) -> None:
        if event.key == "escape" and self._search_active:
            event.stop()
            self._dismiss_search()

    def _load_recent(self, conn) -> None:
        recent = database.get_recent_earned(conn, limit=10)

        table = self.query_one("#recent-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Game", "Trophy", "Type", "Rarity", "Date")

        for t in recent:
            rar = t["trophy_rarity"] or "–"
            date_str = "–"
            if t["earned_date_time"]:
                date_str = t["earned_date_time"][:10]
            table.add_rows([
                [t["title_name"], t["trophy_name"],
                 t["trophy_type"] or "–",
                 rar, date_str]
            ])

        if not recent:
            table.add_rows([["–", "No trophies yet", "", "", ""]])

        table.cursor_type = "row"



    def _render_heatmap(self, conn) -> None:
        today = date.today()
        weeks_back = 10
        start_date = today - timedelta(weeks=weeks_back, days=today.weekday())

        since = start_date.isoformat()
        until = (today + timedelta(days=1)).isoformat()

        earned_rows = database.get_earned_by_date_range(conn, since, until)
        date_counts: dict[str, int] = {}
        max_count = 1
        for r in earned_rows:
            day = r["day"]
            count = r["count"]
            date_counts[day] = count
            if count > max_count:
                max_count = count

        table = self.query_one("#heatmap", DataTable)
        table.clear(columns=True)
        self._heatmap_dates: dict[tuple[int, int], str] = {}

        table.add_column("")  # col 0: weekday names
        for w in range(weeks_back + 1):
            ws = start_date + timedelta(weeks=w)
            table.add_column(ws.strftime("%b %d"))

        for d in range(7):
            cells: list[str | Text] = [WEEKDAYS[d][:3]]
            for w in range(weeks_back + 1):
                day_date = start_date + timedelta(weeks=w, days=d)
                day_str = day_date.isoformat()
                self._heatmap_dates[(w, d)] = day_str
                if day_date > today:
                    cells.append(" ")
                    continue
                count = date_counts.get(day_str, 0)
                if count == 0:
                    cells.append("·")
                else:
                    cells.append(Text("■", style=_heat_color(count / max_count)))
            table.add_row(*cells)

        table.cursor_type = "cell"
        detail = self.query_one("#day-detail", Static)
        detail.update("[dim]Click any day in the heatmap to see trophy details[/]")
        self.query_one("#day-detail-scroll", VerticalScroll).remove_class("active")

        legend_text = Text(" Less  ")
        for c in ["#3abaa0", "#2a9a80", "#1a7a60", "#0d5a45"]:
            legend_text.append("█", c)
        legend_text.append("  More")
        self.query_one("#heatmap-legend", Label).update(legend_text)

    def _show_day_detail(self, day_str: str) -> None:
        if not day_str:
            return
        conn = database.get_conn()
        trophies = database.get_trophies_by_date(conn, day_str)
        detail = self.query_one("#day-detail", Static)
        if not trophies:
            detail.update(f"[dim]  {day_str}: no trophies[/]")
            return
        lines = [f"  [bold]{day_str}[/]  ({len(trophies)} trophies)"]
        for t in trophies:
            name = t["trophy_name"] or "?"
            game = t["title_name"] or "?"
            lines.append(f"    {name}  [dim]({game})[/]")
        detail.update("\n".join(lines))
        self.query_one("#day-detail-scroll", VerticalScroll).add_class("active")
        self.query_one("#day-detail-scroll", VerticalScroll).scroll_home(animate=False)

    def _render_month_compare(self, conn) -> None:
        container = self.query_one("#month-compare")
        container.remove_children()

        today = date.today()
        this_year = today.year
        this_month = today.month

        this_count = database.get_earned_month(conn, this_year, this_month)

        last_month = this_month - 1
        last_year = this_year
        if last_month == 0:
            last_month = 12
            last_year -= 1
        last_count = database.get_earned_month(conn, last_year, last_month)

        this_name = today.strftime("%B %Y")
        last_name = date(last_year, last_month, 1).strftime("%B %Y")

        self.query_one("#month-card").border_title = f"{this_name} vs {last_name}"

        container.mount(Label(f"  {this_name}: {this_count} trophies"))
        container.mount(Label(f"  {last_name}: {last_count} trophies"))

        if last_count > 0:
            change = ((this_count - last_count) / last_count) * 100
            if change > 0:
                change_str = f"  Change: +{change:.0f}% ↑"
            elif change < 0:
                change_str = f"  Change: {change:.0f}% ↓"
            else:
                change_str = "  Change: 0% →"
        elif this_count > 0:
            change_str = "  New this month! 🎉"
        else:
            change_str = "  No activity yet"

        container.mount(Label(change_str))

    def _render_rarity(self, conn) -> None:
        container = self.query_one("#rarity-dist")
        container.remove_children()

        rows = conn.execute("""
            SELECT trophy_rarity, COUNT(*) as count
            FROM trophies
            WHERE earned = 1 AND trophy_rarity IS NOT NULL
            GROUP BY trophy_rarity
            ORDER BY CASE trophy_rarity
                WHEN 'ultra_rare' THEN 1
                WHEN 'very_rare' THEN 2
                WHEN 'rare' THEN 3
                WHEN 'common' THEN 4
            END
        """).fetchall()

        if not rows:
            container.mount(Label("  No rarity data yet"))
            return

        total = sum(r["count"] for r in rows)
        max_count = max(r["count"] for r in rows) if rows else 1
        bar_width = 25

        rarity_names = {
            "ultra_rare": "Ultra Rare",
            "very_rare": "Very Rare",
            "rare": "Rare",
            "common": "Common",
        }

        for r in rows:
            rar = r["trophy_rarity"]
            count = r["count"]
            pct = (count / total) * 100 if total > 0 else 0
            bar_len = int((count / max_count) * bar_width) if max_count > 0 else 0
            bar = "█" * max(bar_len, 1 if count > 0 else 0)

            row = Horizontal(
                Label(f"  {rarity_names.get(rar, rar)}", classes="rarity-label"),
                Label(bar, classes="rarity-bar-bg rarity-bar-fg"),
                Label(f"  {count} ({pct:.0f}%)", classes="rarity-count"),
                classes="rarity-row",
            )
            container.mount(row)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id
        cursor_row = event.cursor_row

        if table_id == "games-table":
            if cursor_row is not None and cursor_row < len(self._games):
                np_comm_id = self._games[cursor_row]["np_communication_id"]
                self.app.current_game_id = np_comm_id
                self.app.switch_mode("game_detail")

        elif table_id == "recent-table":
            if cursor_row is not None:
                conn = database.get_conn()
                recent = list(database.get_recent_earned(conn, limit=10))
                if cursor_row < len(recent):
                    np_comm_id = recent[cursor_row]["np_communication_id"]
                    self.app.current_game_id = np_comm_id
                    self.app.switch_mode("game_detail")


    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        if event.data_table.id != "heatmap":
            return
        day_str = self._heatmap_dates.get((event.coordinate.column - 1, event.coordinate.row))
        if day_str:
            self._show_day_detail(day_str)
