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
- **Headless sync** — optional systemd timer for automatic background sync

## Installation

```bash
pip install psntui
```

Or from source:

```bash
git clone https://github.com/TripShuti/psntui
cd psntui
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
2. Open DevTools → Application → Cookies
3. Copy the value of `npsso`

### Controls

| Key | Action |
|-----|--------|
| `r` | Sync trophies from PSN |
| `a` | Auth screen |
| `m` | Back to main screen |
| `q` | Quit |
| `Esc` | Back (from game detail) |
| Click | Select game / trophies / heatmap day |

### Headless sync (systemd)

```bash
bash systemd/install.sh
```

Installs a timer that syncs every 4 hours (15 min after boot).

Manual trigger:

```bash
psntui --sync
```

## Data

- Config + DB: `~/.config/psntui/` (Linux) / equivalent on macOS/Windows
- SQLite database with WAL mode

## Requirements

- Python ≥ 3.11
- PlayStation Network account with games on PS4/PS5
- NPSSO token from PSN

## License

MIT
