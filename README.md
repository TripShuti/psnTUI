# psnTUI

Terminal UI for browsing and syncing PlayStation trophies.

## Features

- **Sync trophies** from PSN — incremental, only fetches updated games
- **Game library** — progress, trophy counts, last activity
- **Trophy detail** — per-game list with rarity, earn rate, earned date
- **Activity heatmap** — 11-week view, click any day to see trophies earned
- **Month comparison** — current vs previous month
- **Rarity distribution** — ultra rare / very rare / rare / common breakdown
- **Play time tracking** — total, today, week, month per game (PS4/PS5 only)
- **Headless sync** — optional scheduled sync via systemd or Windows Task Scheduler

## Installation

```bash
pip install psntui
```

Or from source:

```bash
git clone https://github.com/TripShuti/psnTUI
cd psnTUI
pip install .
```

## Usage

### First run

```bash
psntui
```

Press `a` to authenticate, enter your NPSSO token (64-char code from
PlayStation), then press `s` to validate and save.

### Getting your NPSSO token

1. Log in to https://ca.account.sony.com
2. Open DevTools → Application → Cookies or go to https://ca.account.sony.com/api/v1/ssocookie
3. Copy the value of `npsso`

### Controls

| Key | Action |
|-----|--------|
| `r` | Sync trophies from PSN |
| `a` | Auth screen |
| `f` | Search game |
| `q` | Quit |
| `Esc` | Back (from game detail) |
| Click | Select game / trophies / heatmap day |

### Headless sync (Linux — systemd)

```bash
bash systemd/install.sh
```

Installs a timer that syncs every 4 hours (15 min after boot).

Manual trigger on any platform:

```bash
psntui --sync
```

### Headless sync (Windows — Task Scheduler)

Run `psntui --sync` manually or create a scheduled task:

```powershell
# Run once
psntui --sync

# Create a task that runs every 4 hours
$action = New-ScheduledTaskAction -Execute "psntui" -Argument "--sync"
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 4) -AtStartup
Register-ScheduledTask -TaskName "psnTUI Sync" -Action $action -Trigger $trigger -RunLevel Highest
```

## Data

- **Linux:** `~/.config/psntui/`
- **Windows:** `%APPDATA%\psntui\`
- **macOS:** `~/Library/Application Support/psntui/`
- SQLite database with WAL mode

## Requirements

- Python ≥ 3.11
- A terminal with Unicode and TrueColour support (Windows Terminal, Windows Console Host with Virtual Terminal enabled, or any modern terminal on Linux/macOS)
- PlayStation Network account with games on PS4/PS5
- NPSSO token from PSN

## License

MIT
