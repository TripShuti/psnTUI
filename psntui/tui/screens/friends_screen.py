from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label, Static
from textual.containers import Vertical
from textual import events, work
from textual.message import Message

from ... import db as database
from ... import sync as sync_module
from ... import auth


def _fmt_ago(fetched_at: str) -> str:
    if not fetched_at:
        return "never"
    try:
        dt = datetime.fromisoformat(fetched_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = int((datetime.now(timezone.utc) - dt).total_seconds())
        if delta < 60:
            return f"{delta}s ago"
        if delta < 3600:
            return f"{delta // 60}m ago"
        return f"{delta // 3600}h ago"
    except Exception:
        return "unknown"


class FriendsReload(Message):
    ...


class FriendsScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    FriendsScreen {
        align: center middle;
    }
    #friends-container {
        width: 72;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
    }
    #friends-title {
        padding: 0 1;
        text-style: bold;
    }
    #friends-table {
        height: 1fr;
        min-height: 5;
        margin: 0 1;
    }
    #friends-status {
        height: 1;
        margin: 0 1 1 1;
        text-style: dim;
        text-align: center;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._loading = False
        self._friends_rows: list = []

    def on_mount(self) -> None:
        self._check_reload()

    def compose(self) -> ComposeResult:
        with Vertical(id="friends-container"):
            yield Label("Friends Leaderboard", id="friends-title")
            yield DataTable(id="friends-table", show_cursor=True)
            yield Static(id="friends-status")

    def _check_reload(self) -> None:
        conn = database.get_conn()
        fetched = database.get_friends_fetched_at(conn)
        age = _fmt_ago(fetched) if fetched else "never"
        status = self.query_one("#friends-status", Static)
        status.update(f"[dim]Last updated: {age}  |  c — compare  |  r — reload  |  Esc — close[/]")
        self._load_table()

    def action_reload(self) -> None:
        if self._loading:
            return
        self._do_reload()

    @work(thread=True)
    def _do_reload(self) -> None:
        self._loading = True
        self.app.call_from_thread(
            lambda: self.query_one("#friends-status", Static).update(
                "[dim]Reloading friends data...[/]"
            )
        )
        config = auth.load_config()
        npsso = config.get("npsso")
        if not npsso:
            self.app.call_from_thread(
                lambda: self.query_one("#friends-status", Static).update(
                    "[red]Not authenticated[/]"
                )
            )
            self._loading = False
            return

        def on_progress(current, total, name):
            self.app.call_from_thread(
                lambda: self.query_one("#friends-status", Static).update(
                    f"[dim]Fetching {current}/{total}  {name}[/]"
                )
            )

        try:
            sync_module.fetch_friends_leaderboard(npsso, progress_callback=on_progress)
        except Exception as e:
            self.app.call_from_thread(
                lambda: self.query_one("#friends-status", Static).update(
                    f"[red]Error: {e}[/]"
                )
            )
            self._loading = False
            return
        self.app.call_from_thread(self._on_reload_done)

    def _on_reload_done(self) -> None:
        self._loading = False
        conn = database.get_conn()
        fetched = database.get_friends_fetched_at(conn)
        age = _fmt_ago(fetched) if fetched else "unknown"
        self.query_one("#friends-status", Static).update(
            f"[dim]Last updated: {age}  |  c — compare  |  r — reload  |  Esc — close[/]"
        )
        self._load_table()

    def _load_table(self) -> None:
        conn = database.get_conn()
        rows = database.get_friends_leaderboard(conn)
        table = self.query_one("#friends-table", DataTable)
        table.clear(columns=True)
        table.add_column("Online ID", width=20)
        table.add_column("Lv.", width=5)
        table.add_column("P", width=4)
        table.add_column("G", width=4)
        table.add_column("S", width=4)
        table.add_column("B", width=4)

        self._friends_rows = list(rows)
        me_id = None
        config = auth.load_config()
        my_online_id = config.get("online_id")

        for r in rows:
            key = str(r["account_id"])
            if r["is_private"]:
                label = "🔒 private"
                table.add_row(
                    r["online_id"], label, label, label, label, label,
                    key=key,
                )
            else:
                table.add_row(
                    r["online_id"],
                    str(r["trophy_level"] or 0),
                    str(r["platinum"] or 0),
                    str(r["gold"] or 0),
                    str(r["silver"] or 0),
                    str(r["bronze"] or 0),
                    key=key,
                )
                if my_online_id and r["online_id"] == my_online_id:
                    me_id = len(table.rows) - 1

        if me_id is not None:
            try:
                table.move_cursor(row=me_id)
            except Exception:
                pass

    def action_compare(self) -> None:
        table = self.query_one("#friends-table", DataTable)
        if not table.rows:
            return
        cursor = table.cursor_coordinate
        if cursor.row >= len(self._friends_rows):
            return
        friend = self._friends_rows[cursor.row]
        if friend["is_private"]:
            self.query_one("#friends-status", Static).update(
                "[red]Cannot compare with private friend[/]"
            )
            return
        self.app.push_screen(
            FriendCompareDetailScreen(friend["account_id"], friend["online_id"])
        )

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss()
        elif event.key == "r":
            self.action_reload()
        elif event.key == "c":
            self.action_compare()


class FriendCompareScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    FriendCompareScreen {
        align: center middle;
    }
    #compare-container {
        width: 64;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
    }
    #compare-title {
        padding: 0 1;
        text-style: bold;
    }
    #compare-table {
        height: 1fr;
        min-height: 5;
        margin: 0 1;
    }
    #compare-status {
        height: 1;
        margin: 0 1 1 1;
        text-style: dim;
        text-align: center;
    }
    """

    def __init__(self, np_comm_id: str, np_title_id: str, game_name: str) -> None:
        super().__init__()
        self._np_comm_id = np_comm_id
        self._np_title_id = np_title_id
        self._game_name = game_name
        self._loading = False

    def on_mount(self) -> None:
        self._load_data()

    def compose(self) -> ComposeResult:
        with Vertical(id="compare-container"):
            yield Label(f"Friends — {self._game_name}", id="compare-title")
            yield DataTable(id="compare-table", show_cursor=True)
            yield Static(id="compare-status")

    def _load_data(self) -> None:
        conn = database.get_conn()
        rows = database.get_friend_game_comparison(conn, self._np_comm_id)
        if rows:
            self._render_table(rows)
            self.query_one("#compare-status", Static).update(
                "[dim]r — reload  |  Esc — close[/]"
            )
        else:
            self.query_one("#compare-status", Static).update(
                "[dim]No data — press r to fetch[/]"
            )

    def _render_table(self, rows) -> None:
        table = self.query_one("#compare-table", DataTable)
        table.clear(columns=True)
        table.add_column("Online ID", width=20)
        table.add_column("Progress", width=9)
        table.add_column("P", width=4)
        table.add_column("G", width=4)
        table.add_column("S", width=4)
        table.add_column("B", width=4)

        for r in rows:
            if r["is_private"]:
                label = "🔒 private"
                table.add_row(r["online_id"], label, label, label, label, label)
            else:
                progress = f"{r['progress'] or 0}%"
                table.add_row(
                    r["online_id"], progress,
                    str(r["earned_platinum"] or 0),
                    str(r["earned_gold"] or 0),
                    str(r["earned_silver"] or 0),
                    str(r["earned_bronze"] or 0),
                )

    def action_reload(self) -> None:
        if self._loading:
            return
        self._do_reload()

    @work(thread=True)
    def _do_reload(self) -> None:
        self._loading = True
        self.app.call_from_thread(
            lambda: self.query_one("#compare-status", Static).update(
                "[dim]Fetching friend data...[/]"
            )
        )
        config = auth.load_config()
        npsso = config.get("npsso")
        if not npsso:
            self.app.call_from_thread(
                lambda: self.query_one("#compare-status", Static).update(
                    "[red]Not authenticated[/]"
                )
            )
            self._loading = False
            return

        def on_progress(current, total, name):
            self.app.call_from_thread(
                lambda: self.query_one("#compare-status", Static).update(
                    f"[dim]Fetching {current}/{total}  {name}[/]"
                )
            )

        try:
            result = sync_module.fetch_friend_game_comparison(
                npsso, self._np_title_id, self._np_comm_id, self._game_name,
                progress_callback=on_progress,
            )
        except Exception as e:
            self.app.call_from_thread(
                lambda: self.query_one("#compare-status", Static).update(
                    f"[red]Error: {e}[/]"
                )
            )
            self._loading = False
            return
        self.app.call_from_thread(lambda: self._on_reload_done(result))

    def _on_reload_done(self, result: dict | None = None) -> None:
        self._loading = False
        if result:
            p = result.get("processed", 0)
            pr = result.get("private", 0)
            e = result.get("errors", 0)
            t = result.get("total", 0)
            self.query_one("#compare-status", Static).update(
                f"[dim]Done: {p}/{t} ok  |  {pr} private  |  {e} errors  |  r — reload  |  Esc — close[/]"
            )
        else:
            self.query_one("#compare-status", Static).update(
                "[dim]r — reload  |  Esc — close[/]"
            )
        self._load_data()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss()
        elif event.key == "r":
            self.action_reload()


class FriendCompareDetailScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    FriendCompareDetailScreen {
        align: center middle;
    }
    #cmpd-container {
        width: 90;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
    }
    #cmpd-title {
        padding: 0 1;
        text-style: bold;
    }
    #cmpd-table {
        height: 1fr;
        min-height: 5;
        margin: 0 1;
    }
    #cmpd-status {
        height: 1;
        margin: 0 1 1 1;
        text-style: dim;
        text-align: center;
    }
    """

    def __init__(self, account_id: str, friend_name: str) -> None:
        super().__init__()
        self._account_id = account_id
        self._friend_name = friend_name

    def compose(self) -> ComposeResult:
        with Vertical(id="cmpd-container"):
            yield Label(f"Comparison — {self._friend_name}", id="cmpd-title")
            yield DataTable(id="cmpd-table", show_cursor=False)
            yield Static(id="cmpd-status")

    def on_mount(self) -> None:
        self._load_data()

    def _load_data(self) -> None:
        conn = database.get_conn()
        rows = database.get_friend_comparison_detail(conn, self._account_id)
        if not rows:
            self.query_one("#cmpd-table", DataTable).add_columns("No shared games")
            self.query_one("#cmpd-table", DataTable).add_row("[dim]—[/]")
            self.query_one("#cmpd-status", Static).update(
                "[dim]No games in common with this friend  |  Esc — close[/]"
            )
            return
        self._render_table(rows)
        self.query_one("#cmpd-status", Static).update(
            "[dim]Esc — close[/]"
        )

    def _render_table(self, rows) -> None:
        table = self.query_one("#cmpd-table", DataTable)
        table.clear(columns=True)
        table.add_column("Game", width=24)
        table.add_column("Progress", width=14)
        table.add_column("P", width=9)
        table.add_column("G", width=9)
        table.add_column("S", width=9)
        table.add_column("B", width=9)

        sum_my_plat = sum_my_gold = sum_my_silver = sum_my_bronze = 0
        sum_fr_plat = sum_fr_gold = sum_fr_silver = sum_fr_bronze = 0

        for r in rows:
            mp = r["my_plat"] or 0
            mg = r["my_gold"] or 0
            ms = r["my_silver"] or 0
            mb = r["my_bronze"] or 0
            fp = r["friend_plat"] or 0
            fg = r["friend_gold"] or 0
            fs = r["friend_silver"] or 0
            fb = r["friend_bronze"] or 0

            sum_my_plat += mp
            sum_my_gold += mg
            sum_my_silver += ms
            sum_my_bronze += mb
            sum_fr_plat += fp
            sum_fr_gold += fg
            sum_fr_silver += fs
            sum_fr_bronze += fb

            my_prog = r["my_progress"] or 0
            fr_prog = r["friend_progress"] or 0
            progress = f"{my_prog}% / {fr_prog}%"

            table.add_row(
                r["title_name"][:24],
                progress,
                f"[bold]{mp}[/]/[dim]{fp}[/]",
                f"[bold]{mg}[/]/[dim]{fg}[/]",
                f"[bold]{ms}[/]/[dim]{fs}[/]",
                f"[bold]{mb}[/]/[dim]{fb}[/]",
            )

        table.add_row(
            "[bold]Total[/]",
            "",
            f"[bold]{sum_my_plat}[/]/[dim]{sum_fr_plat}[/]",
            f"[bold]{sum_my_gold}[/]/[dim]{sum_fr_gold}[/]",
            f"[bold]{sum_my_silver}[/]/[dim]{sum_fr_silver}[/]",
            f"[bold]{sum_my_bronze}[/]/[dim]{sum_fr_bronze}[/]",
        )

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss()
