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
    db.close_conn()


def main():
    parser = argparse.ArgumentParser(
        prog="psntui",
        description="PSN Trophy Tracker TUI",
    )
    parser.add_argument(
        "--sync", action="store_true",
        help="Run headless sync (for cron/systemd)",
    )

    args = parser.parse_args()

    if args.sync:
        headless_sync()
        return

    from . import auth, db
    from .tui.app import psnTUI

    db.set_db_path(auth.get_db_path())
    db.init_db()

    app = psnTUI()
    app.run()


if __name__ == "__main__":
    main()
