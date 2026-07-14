import argparse
import sys


def headless_sync():
    from . import auth, db, sync

    config = auth.load_config()
    if not config.get("npsso"):
        print("Error: Not authenticated. Run 'psntui' and use the auth screen.")
        sys.exit(1)

    db.set_db_path(auth.get_db_path())
    db.init_db()

    online_id = config.get("online_id", "unknown")
    print(f"Syncing trophies for {online_id}...")

    def on_progress(current, total, name):
        if total > 0:
            pct = int((current / total) * 100)
            print(f"  [{pct:3d}%] ({current+1}/{total}) {name}", end="\r")
        else:
            print(f"  ({current+1}) {name}", end="\r")

    result = sync.sync_trophies(config["npsso"], progress_callback=on_progress)
    print()

    if result["status"] == "error":
        print(f"Sync failed: {result['error']}")
        sys.exit(1)
    print(f"Done: +{result['trophies_added']} trophies, {result['games_updated']} games updated")
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"  ⚠ {w}")
        sync.write_sync_log(result["warnings"])
        log_path = db.DB_PATH.parent / "sync.log"
        print(f"  (see {log_path})")
    db.close_conn()


def _dump_stats():
    from . import auth, sync as sync_module

    config = auth.load_config()
    if not config.get("npsso"):
        print("Error: Not authenticated.")
        sys.exit(1)

    from pyrate_limiter import Rate
    from psnawp_api import PSNAWP

    psnawp = PSNAWP(npsso_cookie=config["npsso"], rate_limit=Rate(1, 3))
    client = psnawp.me()

    stats_names: set[str] = set()
    for ts in client.title_stats(limit=None):
        if ts.name:
            stats_names.add(sync_module._normalize_name(ts.name))

    trophy_names: set[str] = set()
    for tt in client.trophy_titles(limit=None):
        if tt.title_name:
            trophy_names.add(sync_module._normalize_name(tt.title_name))

    print(f"Stats API has {len(stats_names)} titles")
    print(f"Trophy API has {len(trophy_names)} titles")
    print()

    missing = sorted(trophy_names - stats_names)
    matched = sorted(trophy_names & stats_names)

    print(f"Games WITH play time ({len(matched)}):")
    for n in matched:
        print(f"  ✓ {n}")
    print()
    print(f"Games WITHOUT play time ({len(missing)}):")
    for n in missing:
        print(f"  ✗ {n}")


def main():
    parser = argparse.ArgumentParser(
        prog="psntui",
        description="PSN Trophy Tracker TUI",
    )
    parser.add_argument(
        "--sync", action="store_true",
        help="Run headless sync (for cron/systemd)",
    )
    parser.add_argument(
        "--stats-dump", action="store_true",
        help="Dump all game names from title_stats API (debug)",
    )

    args = parser.parse_args()

    if args.sync:
        headless_sync()
        return

    if args.stats_dump:
        _dump_stats()
        return

    from . import auth, db
    from .tui.app import psnTUI

    db.set_db_path(auth.get_db_path())
    db.init_db()

    app = psnTUI()
    app.run()


if __name__ == "__main__":
    main()
