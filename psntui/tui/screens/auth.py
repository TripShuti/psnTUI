from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Label, Button, Input, Static
from textual.containers import Container, Vertical


class AuthScreen(Screen):
    CSS = """
    AuthScreen {
        align: center middle;
    }

    .auth-box {
        width: 60;
        height: auto;
        padding: 2;
        border: solid $primary;
    }

    .auth-title {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    .auth-step {
        margin-bottom: 1;
    }

    #npsso-input {
        margin-bottom: 1;
    }

    #auth-status {
        margin-top: 1;
        text-align: center;
    }

    .auth-buttons {
        layout: horizontal;
        width: 100%;
        height: auto;
    }

    .auth-buttons Button {
        width: 1fr;
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Vertical(
                Label("psnTUI — Authentication", classes="auth-title"),
                Label("1. Log into my.playstation.com in your browser", classes="auth-step"),
                Label("2. Visit ca.account.sony.com/api/v1/ssocookie", classes="auth-step"),
                Label('3. Copy the 64-character NPSSO code from the JSON', classes="auth-step"),
                Input(placeholder="Paste NPSSO code here", id="npsso-input"),
                Container(
                    Button("Validate & Save", id="auth-save", variant="primary"),
                    Button("Skip (start without auth)", id="auth-skip", variant="default"),
                    classes="auth-buttons",
                ),
                Label("", id="auth-status"),
            ),
            classes="auth-box",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "auth-save":
            self._do_auth()
        elif event.button.id == "auth-skip":
            self.app.switch_mode("main")

    def _do_auth(self) -> None:
        from ... import auth

        npsso = self.query_one("#npsso-input", Input).value.strip()
        status = self.query_one("#auth-status", Label)

        if not npsso or len(npsso) != 64:
            status.update("[red]NPSSO must be exactly 64 characters[/]")
            return

        status.update("[yellow]Validating...[/]")
        online_id = auth.validate_npsso(npsso)

        if online_id is None:
            status.update("[red]Invalid NPSSO. Make sure you copied it correctly.[/]")
            return

        auth.save_config({"npsso": npsso, "online_id": online_id})
        status.update(f"[green]Authenticated as {online_id}![/]")
        self.app.switch_mode("main")
