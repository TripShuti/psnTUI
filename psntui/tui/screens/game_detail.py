from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label
from textual.containers import Container

from datetime import date, timedelta

from ... import db as database


class GameDetailScreen(Screen):
    BINDINGS = [
        ("escape", "back_to_main", "Back"),
        ("t", "set_play_time", "Set Play Time"),
    ]

    def action_set_play_time(self) -> None:
        self._show_set_time_input()

    def _show_set_time_input(self) -> None:
        input_w = Input(
            placeholder="Hours played (e.g. 25.5 or 2h 30m)…",
            id="time-input",
        )
        self.mount(Container(input_w, id="time-overlay"), before=0)
        input_w.focus()

    def _dismiss_time_input(self) -> None:
        try:
            self.query_one("#time-overlay").remove()
        except Exception:
            pass

    def _parse_hours(self, raw: str) -> int | None:
        raw = raw.strip().lower()
        try:
            if "h" in raw and "m" in raw:
                # "2h 30m"
                import re
                m = re.match(r"(\d+)\s*h\s*(\d+)\s*m", raw)
                if m:
                    return int(m.group(1)) * 3600 + int(m.group(2)) * 60
            elif "h" in raw:
                h = float(raw.replace("h", ""))
                return int(h * 3600)
            elif "m" in raw:
                m = int(raw.replace("m", ""))
                return m * 60
            else:
                h = float(raw)
                return int(h * 3600)
        except (ValueError, AttributeError):
            return None

    def action_back_to_main(self) -> None:
        self.app.switch_mode("main")

    CSS = """
    #game-detail-card {
        border: solid $primary;
        margin: 0 1;
        margin-bottom: 1;
        height: auto;
    }

    .detail-stats {
        padding: 0 1;
    }
    .trophy-card {
        border: solid $primary;
        margin: 0 1;
        padding: 0;
        height: 1fr;
    }
    DataTable {
        scrollbar-size: 0 0;
    }
    #time-overlay {
        dock: top;
        height: auto;
        border: solid $accent;
        background: $surface;
    }
    """

    def __init__(self):
        super().__init__()
        self._current_game: str | None = None

    def compose(self) -> ComposeResult:
        with Container(id="game-detail-card"):
            yield Label("", id="game-stats", classes="detail-stats")
            yield Label("", id="game-playtime", classes="detail-stats")
        with Container(classes="trophy-card"):
            yield DataTable(id="trophy-table")

    def on_key(self, event) -> None:
        if event.key == "escape":
            try:
                if self.query_one("#time-overlay"):
                    self._dismiss_time_input()
                    event.stop()
                    return
            except Exception:
                pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "time-input":
            event.stop()
            self._dismiss_time_input()
            sec = self._parse_hours(event.value.strip())
            if sec is None or sec <= 0:
                self.app.notify("Invalid time format", severity="error")
                return
            conn = database.get_conn()
            database.set_manual_play_time(conn, self._current_game, sec)
            conn.commit()
            self.app.notify(f"Play time saved: {sec//3600}h {(sec%3600)//60:02d}m")
            self._load_game_data()

    def on_screen_resume(self) -> None:
        game_id = getattr(self.app, "current_game_id", None)
        if game_id:
            self._current_game = game_id
            try:
                self._load_game_data()
            except Exception as e:
                self.app.notify(f"Failed to load game: {e}", severity="error")

    def load_game(self, np_comm_id: str) -> None:
        self._current_game = np_comm_id
        self._load_game_data()

    def _load_game_data(self) -> None:
        if not self._current_game:
            return

        conn = database.get_conn()
        game = database.get_game(conn, self._current_game)
        trophies = database.get_trophies(conn, self._current_game)

        if game:
            self.query_one("#game-detail-card").border_title = (
                f"  {game['title_name']}  ({game['platform'] or '–'})"
            )

            total = (game["defined_platinum"] + game["defined_gold"]
                     + game["defined_silver"] + game["defined_bronze"])
            earned = (game["earned_platinum"] + game["earned_gold"]
                      + game["earned_silver"] + game["earned_bronze"])
            progress = game["progress"] or 0
            stats = (
                f"  Progress: {progress}%  |  "
                f"P:{game['earned_platinum']}/{game['defined_platinum']}  "
                f"G:{game['earned_gold']}/{game['defined_gold']}  "
                f"S:{game['earned_silver']}/{game['defined_silver']}  "
                f"B:{game['earned_bronze']}/{game['defined_bronze']}  "
                f"Total: {earned}/{total}"
            )
            self.query_one("#game-stats", Label).update(stats)

        gs = database.get_game_stats(conn, self._current_game)
        if gs and gs["total_seconds"] > 0:
            total_sec = gs["total_seconds"]
            hours = total_sec // 3600
            mins = (total_sec % 3600) // 60
            today_s = date.today()
            week_start = today_s - timedelta(days=today_s.weekday())
            today_sec = database.get_play_time(
                conn, self._current_game, today_s.isoformat(), today_s.isoformat())
            week_sec = database.get_play_time(
                conn, self._current_game, week_start.isoformat(), today_s.isoformat())
            month_sec = database.get_play_time(
                conn, self._current_game, today_s.replace(day=1).isoformat(), today_s.isoformat())

            def fmt(sec: int) -> str:
                if sec == 0:
                    return "—"
                h = sec // 3600
                m = (sec % 3600) // 60
                if h:
                    return f"{h}h {m:02d}m"
                return f"{m}m"

            label = f"  Played: {hours}h {mins:02d}m  |  "
            label += f"Today: {fmt(today_sec)}  "
            label += f"Week: {fmt(week_sec)}  "
            label += f"Month: {fmt(month_sec)}"
            if gs["title_id"] is None:
                label += "  [dim](manual)[/]"
            self.query_one("#game-playtime", Label).update(label)
        else:
            self.query_one("#game-playtime", Label).update(
                "  [dim]No play time data[/]  —  press [accent]t[/] to set"
            )

        table = self.query_one("#trophy-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Type", "Rarity", "Rate", "Earned", "Date")

        self.query_one(".trophy-card").border_title = f"TROPHIES ({len(trophies)})"

        for t in trophies:
            earned_str = "✓" if t["earned"] else " "
            date_str = "–"
            if t["earned_date_time"]:
                date_str = t["earned_date_time"][:10]
            rate = f"{t['trophy_earn_rate']:.1f}%" if t["trophy_earn_rate"] is not None else "–"
            rar = t["trophy_rarity"] or "–"
            table.add_row(
                t["trophy_name"],
                t["trophy_type"] or "–",
                rar, rate, earned_str, date_str,
            )

        if not trophies:
            table.add_rows([["No trophies", "", "", "", "", ""]])

        table.cursor_type = "row"
