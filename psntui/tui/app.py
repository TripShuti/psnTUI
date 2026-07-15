from textual.app import App
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static
from textual import work
from textual.worker import WorkerFailed

from .. import auth, db
from .. import sync as sync_module

from .theme import ALL_THEMES
from .screens.auth import AuthScreen
from .screens.main import MainScreen
from .screens.game_detail import GameDetailScreen
from .screens.theme_screen import ThemeScreen
from .screens.friends_screen import FriendsScreen


class SyncProgress(Message):
    def __init__(self, current: int, total: int, name: str) -> None:
        super().__init__()
        self.current = current
        self.total = total
        self.name = name


class SyncResult(Message):
    def __init__(self, result: dict) -> None:
        super().__init__()
        self.result = result


class psnTUI(App):
    TITLE = "psnTUI"
    CSS_PATH = "app.tcss"

    MODES = {
        "auth": AuthScreen,
        "main": MainScreen,
        "game_detail": GameDetailScreen,
    }

    BINDINGS = [
        Binding("r", "sync", "Sync"),
        Binding("a", "auth", "Auth"),
        Binding("t", "open_theme_picker", "Theme"),
        Binding("l", "open_friends_leaderboard", "Friends"),
        Binding("f", "search", "Search"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._syncing = False
        self._sync_bar = None

    def on_mount(self) -> None:
        for t in ALL_THEMES.values():
            self.register_theme(t)
        config = auth.load_config()
        self.theme = config.get("theme", "ps1")
        if auth.is_authenticated():
            self.switch_mode("main")
        else:
            self.switch_mode("auth")

    def action_sync(self) -> None:
        if self._syncing:
            self.notify("Sync already in progress", severity="warning")
            return
        config = auth.load_config()
        if not config.get("npsso"):
            self.notify("Authenticate first (press 'a')", severity="error")
            return
        self._syncing = True
        self._put_bar("⏳ Syncing...", "")
        self._run_sync(config["npsso"])

    def action_auth(self) -> None:
        self.switch_mode("auth")

    def action_open_theme_picker(self) -> None:
        self.push_screen(ThemeScreen())

    def action_open_friends_leaderboard(self) -> None:
        self.push_screen(FriendsScreen())

    def action_search(self) -> None:
        if hasattr(self.screen, "_show_search"):
            self.screen._show_search()

    @work(thread=True)
    def _run_sync(self, npsso: str) -> None:
        def on_progress(current: int, total: int, name: str) -> None:
            self.post_message(SyncProgress(current, total, name))
        result = sync_module.sync_trophies(npsso, progress_callback=on_progress)
        self.post_message(SyncResult(result))

    def on_sync_progress(self, event: SyncProgress) -> None:
        self._put_bar(
            f"⏳ Syncing... ({event.current+1}/{event.total}) {event.name}", ""
        )

    def on_sync_result(self, event: SyncResult) -> None:
        self._syncing = False
        r = event.result
        if r["status"] == "error":
            self._put_bar(f"✗ Sync failed: {r['error']}", "error")
        else:
            msg = (
                f"✓ Done: +{r['trophies_added']} trophies, "
                f"{r['games_updated']} games"
            )
            if r.get("warnings"):
                msg += f"  ⚠ {len(r['warnings'])} warnings"
                sync_module.write_sync_log(r["warnings"])
                log_path = db.DB_PATH.parent / "sync.log"
                msg += f"  ([dim]see {log_path}[/])"
            self._put_bar(msg, "success")
        self._refresh_current_screen()

    def on_worker_failed(self, event: WorkerFailed) -> None:
        self._syncing = False
        self._put_bar(f"✗ Sync crashed: {event.error}", "error")

    def _put_bar(self, text: str, style: str) -> None:
        if self._sync_bar is not None:
            bar = self._sync_bar
        else:
            bar = Static(id="sync-status")
            bar.border_title = "SYNC STATUS"
            self.mount(bar)
            self._sync_bar = bar
        bar.update(text)
        if style:
            bar.classes = style
        if not self._syncing:
            self.set_timer(6, self._clear_bar)

    def _clear_bar(self) -> None:
        if self._sync_bar is not None:
            self._sync_bar.remove()
            self._sync_bar = None

    def _refresh_current_screen(self) -> None:
        screen = self.screen
        for method in ("_load_data", "_load_games", "_load_stats", "_load_game_data"):
            if hasattr(screen, method):
                getattr(screen, method)()
                break
