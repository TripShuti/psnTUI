# psnTUI

A terminal UI for browsing and syncing your PlayStation trophies — built for
people who live in the terminal and want their trophy data without opening
a browser or a bloated companion app.
<img width="1920" height="1046" alt="image" src="https://github.com/user-attachments/assets/f866e805-5505-4f02-abd7-ec03bee14b51" />


## Features

- **Sync trophies** from PSN — incremental, only re-fetches games that changed since the last sync
- **Game library** — progress, trophy counts (platinum/gold/silver/bronze), last activity
- **Trophy detail** — per-game list with rarity, earn rate, earned date
- **Weekly activity heatmap** — 11-week view, click any day to see what you earned
- **Month comparison** — current month vs previous month
- **Rarity distribution** — ultra rare / very rare / rare / common breakdown
- **Play time tracking** — total, today, this week, this month, per game (PS4/PS5 only)
- **Friend leaderboard** — trophy level, platinum/gold/silver/bronze counts for all friends
- **Per-game comparison** — compare trophy progress with a specific friend across all shared games
- **In-app search** — jump to any game in your library without scrolling
- **Headless sync** — scheduled background sync via systemd (Linux) or Task Scheduler (Windows)
- Keyboard-first, no mouse required

## Installation

Recommended — works the same on Linux, macOS, and Windows:

```bash
pipx install psntui
```

[pipx](https://pipx.pypa.io) installs the app in its own isolated environment
and puts it on your PATH, so you don't need to manage a virtualenv yourself.

Alternatively, with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install psntui
```

Or plain pip, if you already manage your own virtual environment:

```bash
pip install psntui
```

From source:

```bash
git clone https://github.com/TripShuti/psnTUI
cd psnTUI
pipx install .
```

## Usage

### First run

```bash
psntui
```

On first launch you'll land on the auth screen. Paste your NPSSO token and
click **Validate & Save** (or press `Skip` to browse the empty UI first).

### Getting your NPSSO token

1. Log in at https://ca.account.sony.com
2. Visit https://ca.account.sony.com/api/v1/ssocookie
3. Copy the 64-character value of `npsso` from the returned JSON

This token grants access to your PSN account data — treat it like a password.
psnTUI stores it locally with owner-only file permissions and never sends it
anywhere except Sony's own API.

### Controls

#### Main screen

| Key     | Action                                |
|---------|----------------------------------------|
| `r`     | Sync trophies from PSN                |
| `a`     | Auth screen                           |
| `l`     | Open friend leaderboard               |
| `t`     | Theme picker                          |
| `f`     | Search games                          |
| `q`     | Quit                                  |
| `Esc`   | Back (from game detail / search)      |
| Click   | Select game / trophy / heatmap day    |
| Click   | Play time card → open monthly calendar|

#### Friends leaderboard (`l`)

| Key     | Action                                |
|---------|----------------------------------------|
| `c`     | Compare with selected friend          |
| `r`     | Reload friend data from PSN           |
| `Esc`   | Close                                 |

#### Game detail

| Key     | Action                                |
|---------|----------------------------------------|
| `c`     | Compare friends on this game          |
| `t`     | Set play time (if no PSN data)        |
| `Esc`   | Back                                  |

### Headless sync — Linux (systemd)

> Requires cloning the repository — these files aren't bundled in the PyPI package.

```bash
git clone https://github.com/TripShuti/psnTUI
cd psnTUI
bash systemd/install.sh
```

Installs a user timer that syncs every 4 hours on a fixed schedule
(00:00, 04:00, 08:00, 12:00, 16:00, 20:00). Survives sleep/suspend — if a
scheduled sync is missed while the system was asleep, it runs once
immediately on wake, instead of skipping it entirely.

Check it:
```bash
systemctl --user status psntui-sync.timer
journalctl --user -u psntui-sync.service -n 20
```

### Headless sync — Windows (Task Scheduler)

```powershell
# Run once
psntui --sync

# Create a recurring task, every 4 hours
$action = New-ScheduledTaskAction -Execute "psntui" -Argument "--sync"
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 4) -AtStartup
Register-ScheduledTask -TaskName "psnTUI Sync" -Action $action -Trigger $trigger -RunLevel Highest
```

> Note: by default this won't wake a sleeping laptop, so syncs are skipped
> while it's asleep rather than caught up afterward. Add `-WakeToRun` to the
> trigger settings if you want it to wake the machine for scheduled syncs,
> or just run `psntui --sync` manually after waking.

### Manual trigger (any platform)

```bash
psntui --sync
```

## Data storage

| OS      | Location                                  |
|---------|--------------------------------------------|
| Linux   | `~/.config/psntui/`                       |
| macOS   | `~/Library/Application Support/psntui/`   |
| Windows | `%APPDATA%\psntui\`                       |

SQLite database with WAL mode. Your NPSSO token lives in `config.json` in
the same directory, with `0600` permissions on Linux/macOS.

## Requirements

- Python ≥ 3.11
- A terminal with Unicode and TrueColor support (Windows Terminal, any
  modern Linux/macOS terminal — legacy `cmd.exe` is not recommended)
- A PlayStation Network account with games on PS4/PS5
- An NPSSO token (see above)

## Development

```bash
git clone https://github.com/TripShuti/psnTUI
cd psnTUI
python -m venv .venv && source .venv/bin/activate
pip install -e .
pytest tests/
```

## Disclaimer

psnTUI uses [psnawp](https://pypi.org/project/psnawp/), an unofficial,
reverse-engineered wrapper around the PlayStation Network API. This is not
affiliated with or endorsed by Sony Interactive Entertainment. Use at your
own discretion — aggressive sync frequency may trigger PSN rate limiting.

## License

MIT
