import time
import sqlite3
from datetime import datetime, timezone
from typing import Any
from threading import Lock

from pyrate_limiter import Rate
from psnawp_api import PSNAWP
from psnawp_api.core.request_builder import RequestBuilder
from psnawp_api.models.trophies import PlatformType

from . import db

_sync_lock = Lock()
REQUEST_TIMEOUT = 60


def _parse_date_utc(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


_request_patch_applied = False

def _ensure_request_timeout() -> None:
    global _request_patch_applied
    if _request_patch_applied:
        return
    _orig_request = RequestBuilder.request
    def _patched_request(self, method, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        return _orig_request(self, method, **kwargs)
    RequestBuilder.request = _patched_request
    _request_patch_applied = True


def _extract_game_data(title: Any) -> dict:
    platform = list(title.title_platform)[0].value if title.title_platform else None
    return {
        "np_communication_id": title.np_communication_id,
        "np_title_id": title.np_title_id,
        "title_name": title.title_name,
        "title_icon_url": title.title_icon_url,
        "platform": platform,
        "defined_bronze": title.defined_trophies.bronze,
        "defined_silver": title.defined_trophies.silver,
        "defined_gold": title.defined_trophies.gold,
        "defined_platinum": title.defined_trophies.platinum,
        "earned_bronze": title.earned_trophies.bronze,
        "earned_silver": title.earned_trophies.silver,
        "earned_gold": title.earned_trophies.gold,
        "earned_platinum": title.earned_trophies.platinum,
        "progress": title.progress,
        "last_updated_datetime": (
            title.last_updated_datetime.isoformat()
            if title.last_updated_datetime
            else None
        ),
    }


def _extract_trophy_data(np_comm_id: str, trophy: Any) -> dict:
    return {
        "np_communication_id": np_comm_id,
        "trophy_id": trophy.trophy_id,
        "trophy_name": trophy.trophy_name,
        "trophy_detail": trophy.trophy_detail,
        "trophy_type": trophy.trophy_type.value.lower() if trophy.trophy_type else None,
        "trophy_icon_url": trophy.trophy_icon_url,
        "trophy_hidden": bool(trophy.trophy_hidden),
        "trophy_group_id": trophy.trophy_group_id or "default",
        "earned": bool(trophy.earned) if hasattr(trophy, "earned") else False,
        "earned_date_time": (
            trophy.earned_date_time.isoformat()
            if hasattr(trophy, "earned_date_time") and trophy.earned_date_time
            else None
        ),
        "trophy_rarity": (
            trophy.trophy_rarity.name.lower()
            if hasattr(trophy, "trophy_rarity") and trophy.trophy_rarity
            else None
        ),
        "trophy_earn_rate": (
            float(trophy.trophy_earn_rate)
            if hasattr(trophy, "trophy_earn_rate") and trophy.trophy_earn_rate is not None
            else None
        ),
        "progress": (
            int(trophy.progress)
            if hasattr(trophy, "progress") and trophy.progress is not None
            else None
        ),
        "progress_rate": (
            int(trophy.progress_rate)
            if hasattr(trophy, "progress_rate") and trophy.progress_rate is not None
            else None
        ),
    }


def _get_platform(title: Any) -> PlatformType:
    if title.title_platform:
        return list(title.title_platform)[0]
    return PlatformType.PS4


def sync_trophies(npsso: str, progress_callback=None) -> dict:
    with _sync_lock:
        return _do_sync(npsso, progress_callback)


def _do_sync(npsso: str, progress_callback=None) -> dict:
    result = {
        "status": "success",
        "trophies_added": 0,
        "games_updated": 0,
        "error": None,
        "warnings": [],
    }

    for attempt in range(3):
        try:
            conn = db.get_conn()
        except sqlite3.Error as e:
            result["status"] = "error"
            result["error"] = f"Database connection failed: {e}"
            return result

        conn.rollback()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass

        try:
            last_sync = db.get_last_sync_time(conn)
            sync_id = db.start_sync(conn)
            conn.commit()
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < 2:
                time.sleep(2)
                continue
            result["status"] = "error"
            result["error"] = f"Database locked after retries: {e}"
            return result

    try:
        _ensure_request_timeout()
        psnawp = PSNAWP(npsso_cookie=npsso, rate_limit=Rate(1, 1))
        client = psnawp.me()
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Authentication failed: {e}"
        db.finish_sync(conn, sync_id, "error", error_message=str(e))
        conn.commit()
        return result

    all_titles = list(client.trophy_titles(limit=None))

    title_stats_map: dict[str, Any] = {}
    try:
        for ts in client.title_stats(limit=None):
            if ts.name and ts.name not in title_stats_map:
                title_stats_map[ts.name] = ts
    except Exception as e:
        result["warnings"].append(f"Could not fetch play time stats: {e}")

    for idx, title in enumerate(all_titles):
        if progress_callback:
            progress_callback(idx, len(all_titles), title.title_name)

        np_comm_id = title.np_communication_id
        if not np_comm_id:
            continue

        game_in_db = db.game_exists(conn, np_comm_id)
        needs_update = not game_in_db

        if not needs_update and title.last_updated_datetime and last_sync:
            ts = title.last_updated_datetime
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ls = last_sync
            if ls.tzinfo is None:
                ls = ls.replace(tzinfo=timezone.utc)
            needs_update = ts > ls

        if needs_update:
            platform = _get_platform(title)
            try:
                trophies = list(
                    client.trophies(
                        np_comm_id,
                        platform,
                        include_progress=True,
                    )
                )
            except Exception as e:
                if len(result["warnings"]) < 20:
                    result["warnings"].append(f"Skipped {title.title_name}: {e}")
                continue

            trophy_dicts = []
            for t in trophies:
                try:
                    trophy_dicts.append(_extract_trophy_data(np_comm_id, t))
                except Exception:
                    continue
            game_data = _extract_game_data(title)

            db.write_game_with_trophies(conn, game_data, trophy_dicts)

            result["games_updated"] += 1
            if last_sync:
                ls = last_sync
                if ls.tzinfo is None:
                    ls = ls.replace(tzinfo=timezone.utc)
                new_trophies = [
                    t
                    for t in trophy_dicts
                    if t["earned"]
                    and t["earned_date_time"]
                    and _parse_date_utc(t["earned_date_time"]) > ls
                ]
                result["trophies_added"] += len(new_trophies)
            else:
                result["trophies_added"] += sum(1 for t in trophy_dicts if t["earned"])

        ts_stats = title_stats_map.get(title.title_name)
        if ts_stats and ts_stats.play_duration is not None:
            db.update_game_stats(
                conn, np_comm_id,
                title_id=ts_stats.title_id,
                total_seconds=int(ts_stats.play_duration.total_seconds()),
                play_count=ts_stats.play_count,
                first_played=ts_stats.first_played_date_time.isoformat()
                if ts_stats.first_played_date_time else None,
                last_played=ts_stats.last_played_date_time.isoformat()
                if ts_stats.last_played_date_time else None,
            )

    try:
        db.finish_sync(
            conn, sync_id, result["status"],
            trophies_added=result["trophies_added"],
            games_updated=result["games_updated"],
        )
        conn.commit()
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Failed to finalise sync: {e}"

    return result
