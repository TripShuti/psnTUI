import hashlib
import re
import time
import sqlite3
from datetime import datetime, timezone
from typing import Any
from threading import Lock

from pyrate_limiter import Rate
from psnawp_api import PSNAWP
from psnawp_api.core.request_builder import RequestBuilder
from psnawp_api.core.psnawp_exceptions import PSNAWPForbiddenError
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


_RE_TM = re.compile(r"[™®]")
_RE_NEWLINE = re.compile(r"[\u000a\u000d]")
_RE_SUFFIX = re.compile(r"\s+trophies$", re.IGNORECASE)
_RE_WS = re.compile(r"\s+")


def _normalize_name(name: str) -> str:
    s = _RE_NEWLINE.sub("", name)
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = _RE_TM.sub("", s)
    s = _RE_SUFFIX.sub("", s)
    s = _RE_WS.sub(" ", s)
    return s.strip().lower()


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
        psnawp = PSNAWP(npsso_cookie=npsso, rate_limit=Rate(1, 3))
        client = psnawp.me()
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Authentication failed: {e}"
        db.finish_sync(conn, sync_id, "error", error_message=str(e))
        conn.commit()
        return result

    all_titles = list(client.trophy_titles(limit=None))

    stats_by_id: dict[str, Any] = {}
    stats_by_name: dict[str, Any] = {}
    try:
        for ts in client.title_stats(limit=None):
            if ts.title_id and ts.title_id not in stats_by_id:
                stats_by_id[ts.title_id] = ts
            if ts.name:
                key = _normalize_name(ts.name)
                if key not in stats_by_name:
                    stats_by_name[key] = ts
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

        ts_stats = stats_by_id.get(title.np_title_id)
        if not ts_stats:
            ts_stats = stats_by_name.get(_normalize_name(title.title_name))
        if ts_stats:
            if ts_stats.title_id and ts_stats.title_id != title.np_title_id:
                conn.execute(
                    "UPDATE games SET np_title_id = ? WHERE np_communication_id = ?",
                    (ts_stats.title_id, np_comm_id)
                )
            if ts_stats.play_duration is not None:
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
        else:
            existing = db.get_game_stats(conn, np_comm_id)
            if not existing or existing["total_seconds"] == 0:
                title_id_hint = ""
                if title.np_title_id:
                    title_id_hint = f" (id={title.np_title_id})"
                result["warnings"].append(
                    f"No play time data for '{title.title_name}'{title_id_hint} "
                    f"— not in PSN gamelist"
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


def write_sync_log(warnings: list[str]) -> None:
    if not warnings:
        return
    log_path = db.DB_PATH.parent / "sync.log"
    hash_path = log_path.with_suffix(".log.hash")
    new_hash = hashlib.sha256("".join(warnings).encode()).hexdigest()
    try:
        old_hash = hash_path.read_text().strip()
        if old_hash == new_hash:
            return
    except (OSError, FileNotFoundError):
        pass
    now = datetime.now().isoformat(timespec="seconds")
    lines = [f"[{now}] Sync warnings ({len(warnings)}):"]
    for w in warnings:
        lines.append(f"  ⚠ {w}")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
        hash_path.write_text(new_hash)
    except OSError:
        pass


def fetch_friends_leaderboard(npsso: str, progress_callback=None) -> dict:
    conn = db.get_conn()
    psnawp = PSNAWP(npsso_cookie=npsso)
    client = psnawp.me()
    friends = list(client.friends_list(limit=1000))
    now = datetime.now(timezone.utc).isoformat()
    processed = 0
    private = 0
    errors = 0
    games_stored = 0

    total = len(friends)
    for i, friend in enumerate(friends):
        try:
            summary = friend.trophy_summary()
            db.upsert_friend(conn, {
                "account_id": friend.account_id,
                "online_id": friend.online_id,
                "trophy_level": summary.trophy_level,
                "platinum": summary.earned_trophies.platinum,
                "gold": summary.earned_trophies.gold,
                "silver": summary.earned_trophies.silver,
                "bronze": summary.earned_trophies.bronze,
                "is_private": 0,
                "fetched_at": now,
            })

            try:
                for tt in friend.trophy_titles():
                    npid = tt.np_communication_id
                    if not npid or not npid.startswith("NPWR"):
                        continue
                    db.upsert_friend_game(conn, {
                        "account_id": friend.account_id,
                        "np_communication_id": npid,
                        "progress": tt.progress or 0,
                        "earned_platinum": tt.earned_trophies.platinum,
                        "earned_gold": tt.earned_trophies.gold,
                        "earned_silver": tt.earned_trophies.silver,
                        "earned_bronze": tt.earned_trophies.bronze,
                        "is_private": 0,
                        "fetched_at": now,
                    })
                    games_stored += 1
            except Exception:
                pass

            processed += 1
        except PSNAWPForbiddenError:
            db.upsert_friend(conn, {
                "account_id": friend.account_id,
                "online_id": friend.online_id,
                "trophy_level": None,
                "platinum": 0, "gold": 0, "silver": 0, "bronze": 0,
                "is_private": 1,
                "fetched_at": now,
            })
            private += 1
        except Exception:
            errors += 1
        if progress_callback:
            progress_callback(i + 1, total, friend.online_id)

    conn.commit()
    return {
        "processed": processed,
        "private": private,
        "errors": errors,
        "total": total,
        "games_stored": games_stored,
    }


def fetch_friend_game_comparison(npsso: str, np_title_id: str,
                                  np_comm_id: str, game_name: str,
                                  progress_callback=None) -> dict:
    conn = db.get_conn()
    psnawp = PSNAWP(npsso_cookie=npsso)
    client = psnawp.me()
    friends = list(client.friends_list(limit=1000))
    now = datetime.now(timezone.utc).isoformat()
    processed = 0
    private = 0
    errors = 0

    total = len(friends)

    def store(friend, tt):
        et = tt.earned_trophies
        db.upsert_friend_game(conn, {
            "account_id": friend.account_id,
            "np_communication_id": tt.np_communication_id or "",
            "progress": tt.progress or 0,
            "earned_platinum": et.platinum,
            "earned_gold": et.gold,
            "earned_silver": et.silver,
            "earned_bronze": et.bronze,
            "is_private": 0,
            "fetched_at": now,
        })

    def store_private(friend):
        db.upsert_friend_game(conn, {
            "account_id": friend.account_id,
            "np_communication_id": "",
            "progress": None,
            "earned_platinum": 0, "earned_gold": 0,
            "earned_silver": 0, "earned_bronze": 0,
            "is_private": 1,
            "fetched_at": now,
        })

    for i, friend in enumerate(friends):
        try:
            found = False
            try:
                for tt in friend.trophy_titles_for_title([np_title_id]):
                    store(friend, tt)
                    found = True
                    break
            except PSNAWPForbiddenError:
                store_private(friend)
                private += 1
                found = True
            except Exception:
                pass

            if not found:
                for tt in friend.trophy_titles():
                    if tt.np_communication_id == np_comm_id:
                        store(friend, tt)
                        found = True
                        break
            processed += 1
        except PSNAWPForbiddenError:
            store_private(friend)
            private += 1
        except Exception:
            errors += 1
        if progress_callback:
            progress_callback(i + 1, total, friend.online_id)

    conn.commit()
    return {
        "processed": processed,
        "private": private,
        "errors": errors,
        "total": total,
    }
