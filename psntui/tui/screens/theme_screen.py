from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import OptionList, Label
from textual.containers import Vertical
from textual.widgets.option_list import Option
from textual import events

from ..theme import ALL_THEMES
from ... import auth

_THEME_OPTIONS = [
    ("ps1", "PS1  —  BSOD navy"),
    ("ps2", "PS2  —  steel blue"),
    ("ps3", "PS3  —  midnight black"),
    ("ps4", "PS4  —  Sony blue"),
    ("ps5", "PS5  —  pearl white"),
]


class ThemeScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    ThemeScreen {
        align: center middle;
    }
    #theme-container {
        width: 40;
        height: auto;
        border: solid $primary;
        background: $surface;
    }
    #theme-title {
        padding: 1 2;
        text-style: bold;
    }
    #theme-list {
        height: auto;
        margin: 0 1 1 1;
    }
    #theme-hint {
        height: 1;
        margin: 0 1 1 1;
        text-style: dim;
        text-align: center;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._original_theme: str = ""

    def on_mount(self) -> None:
        self._original_theme = self.app.theme
        list_w = self.query_one("#theme-list", OptionList)
        for i, (key, label) in enumerate(_THEME_OPTIONS):
            list_w.add_option(Option(label, id=key))
            if key == self._original_theme:
                list_w.highlighted = i

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-container"):
            yield Label("Select Theme", id="theme-title")
            yield OptionList(id="theme-list")
            yield Label("Enter — apply · Esc — cancel", id="theme-hint")

    def _apply(self, theme_name: str) -> None:
        self.app.theme = theme_name

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id:
            self._apply(event.option.id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            auth.save_theme_preference(event.option.id)
            self.dismiss()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self._apply(self._original_theme)
            self.dismiss()
