from textual.theme import Theme

PS1_THEME = Theme(
    name="ps1",
    primary="#5a8aaa",
    secondary="#4a6a80",
    accent="#00c8a0",
    foreground="#d0d0d0",
    background="#1a1a1e",
    surface="#282830",
    error="#d05050",
    success="#50b050",
    warning="#d0a050",
    dark=True,
)

PS2_THEME = Theme(
    name="ps2",
    primary="#7a8a9a",
    secondary="#5a6a78",
    accent="#3a7fd5",
    foreground="#d8dce0",
    background="#16181c",
    surface="#22262c",
    error="#d05050",
    success="#50b050",
    warning="#d0a050",
    dark=True,
)

PS3_THEME = Theme(
    name="ps3",
    primary="#2a2e38",
    secondary="#1a1e26",
    accent="#2ec4e6",
    foreground="#e0f4fa",
    background="#0a0c10",
    surface="#161a20",
    error="#d05050",
    success="#50b050",
    warning="#d0a050",
    dark=True,
)

PS4_THEME = Theme(
    name="ps4",
    primary="#2b4a8a",
    secondary="#1e3566",
    accent="#5aa0ff",
    foreground="#e8ecf5",
    background="#0d1a3a",
    surface="#132852",
    error="#d05050",
    success="#50b050",
    warning="#d0a050",
    dark=True,
)

PS5_THEME = Theme(
    name="ps5",
    primary="#e8e8ec",
    secondary="#9098a5",
    accent="#3a7fd5",
    foreground="#f0f0f4",
    background="#0c0d10",
    surface="#1a1c22",
    error="#d05050",
    success="#50b050",
    warning="#d0a050",
    dark=True,
)

ALL_THEMES = {
    "ps1": PS1_THEME,
    "ps2": PS2_THEME,
    "ps3": PS3_THEME,
    "ps4": PS4_THEME,
    "ps5": PS5_THEME,
}
