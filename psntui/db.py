import sqlite3
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional
import time
import threading

DB_PATH: Path | None = None

_local = threading.local()


_lock = threading.Lock()


def set_db_path(path: Path) -> None:
    global DB_PATH
    with _lock:
        DB_PATH = path


def get_conn() -> sqlite3.Connection:
    if DB_PATH is None:
        raise RuntimeError("DB_PATH not set")
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            try:
                conn.close()
            except sqlite3.Error:
                pass
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _local.conn = conn
    return conn


def close_conn() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        _local.conn = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    np_communication_id TEXT PRIMARY KEY,
    np_title_id TEXT,
    title_name TEXT NOT NULL,
    title_icon_url TEXT,
    platform TEXT,
    defined_bronze INTEGER DEFAULT 0,
    defined_silver INTEGER DEFAULT 0,
    defined_gold INTEGER DEFAULT 0,
    defined_platinum INTEGER DEFAULT 0,
    earned_bronze INTEGER DEFAULT 0,
    earned_silver INTEGER DEFAULT 0,
    earned_gold INTEGER DEFAULT 0,
    earned_platinum INTEGER DEFAULT 0,
    progress INTEGER DEFAULT 0,
    last_updated_datetime TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trophies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    np_communication_id TEXT NOT NULL,
    trophy_id INTEGER NOT NULL,
    trophy_name TEXT,
    trophy_detail TEXT,
    trophy_type TEXT,
    trophy_icon_url TEXT,
    trophy_hidden INTEGER DEFAULT 0,
    trophy_group_id TEXT DEFAULT 'default',
    earned INTEGER DEFAULT 0,
    earned_date_time TEXT,
    trophy_rarity TEXT,
    trophy_earn_rate REAL,
    progress INTEGER,
    progress_rate INTEGER,
    UNIQUE(np_communication_id, trophy_id),
    FOREIGN KEY (np_communication_id) REFERENCES games(np_communication_id)
);

CREATE TABLE IF NOT EXISTS game_stats (
    np_communication_id TEXT PRIMARY KEY,
    title_id TEXT,
    total_seconds INTEGER NOT NULL DEFAULT 0,
    play_count INTEGER DEFAULT 0,
    first_played TEXT,
    last_played TEXT,
    FOREIGN KEY (np_communication_id) REFERENCES games(np_communication_id)
);

CREATE TABLE IF NOT EXISTS play_delta_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    np_communication_id TEXT NOT NULL,
    date TEXT NOT NULL,
    delta_seconds INTEGER NOT NULL,
    UNIQUE(np_communication_id, date),
    FOREIGN KEY (np_communication_id) REFERENCES games(np_communication_id)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT DEFAULT (datetime('now')),
    finished_at TEXT,
    status TEXT DEFAULT 'running',
    error_message TEXT,
    trophies_added INTEGER DEFAULT 0,
    games_updated INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS friends_cache (
    account_id TEXT PRIMARY KEY,
    online_id TEXT NOT NULL,
    trophy_level INTEGER,
    platinum INTEGER, gold INTEGER, silver INTEGER, bronze INTEGER,
    is_private INTEGER DEFAULT 0,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS friend_game_cache (
    account_id TEXT NOT NULL,
    np_communication_id TEXT NOT NULL,
    progress INTEGER, earned_platinum INTEGER, earned_gold INTEGER,
    earned_silver INTEGER, earned_bronze INTEGER,
    is_private INTEGER DEFAULT 0,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (account_id, np_communication_id)
);

"""


def init_db() -> None:
    conn = get_conn()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass
    conn.executescript(SCHEMA)

    conn.execute(
        "DELETE FROM play_delta_history WHERE delta_seconds > 86400"
    )

    try:
        conn.execute(
            "UPDATE sync_log SET status = 'error', error_message = 'Cancelled (stuck)',"
            " finished_at = datetime('now') WHERE status = 'running'"
        )
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()


def upsert_game(conn: sqlite3.Connection, g: dict) -> None:
    conn.execute("""
        INSERT INTO games (
            np_communication_id, np_title_id, title_name, title_icon_url, platform,
            defined_bronze, defined_silver, defined_gold, defined_platinum,
            earned_bronze, earned_silver, earned_gold, earned_platinum,
            progress, last_updated_datetime, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(np_communication_id) DO UPDATE SET
            np_title_id=excluded.np_title_id, title_name=excluded.title_name,
            title_icon_url=excluded.title_icon_url, platform=excluded.platform,
            defined_bronze=excluded.defined_bronze, defined_silver=excluded.defined_silver,
            defined_gold=excluded.defined_gold, defined_platinum=excluded.defined_platinum,
            earned_bronze=excluded.earned_bronze, earned_silver=excluded.earned_silver,
            earned_gold=excluded.earned_gold, earned_platinum=excluded.earned_platinum,
            progress=excluded.progress, last_updated_datetime=excluded.last_updated_datetime,
            updated_at=excluded.updated_at
    """, (
        g["np_communication_id"], g.get("np_title_id"), g["title_name"],
        g.get("title_icon_url"), g.get("platform"),
        g.get("defined_bronze", 0), g.get("defined_silver", 0),
        g.get("defined_gold", 0), g.get("defined_platinum", 0),
        g.get("earned_bronze", 0), g.get("earned_silver", 0),
        g.get("earned_gold", 0), g.get("earned_platinum", 0),
        g.get("progress", 0), g.get("last_updated_datetime"),
    ))


def upsert_trophy(conn: sqlite3.Connection, t: dict) -> None:
    conn.execute("""
        INSERT INTO trophies (
            np_communication_id, trophy_id, trophy_name, trophy_detail,
            trophy_type, trophy_icon_url, trophy_hidden, trophy_group_id,
            earned, earned_date_time, trophy_rarity, trophy_earn_rate,
            progress, progress_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(np_communication_id, trophy_id) DO UPDATE SET
            trophy_name=excluded.trophy_name, trophy_detail=excluded.trophy_detail,
            trophy_type=excluded.trophy_type, trophy_icon_url=excluded.trophy_icon_url,
            trophy_hidden=excluded.trophy_hidden,
            earned=excluded.earned, earned_date_time=excluded.earned_date_time,
            trophy_rarity=excluded.trophy_rarity, trophy_earn_rate=excluded.trophy_earn_rate,
            progress=excluded.progress, progress_rate=excluded.progress_rate
    """, (
        t["np_communication_id"], t["trophy_id"], t.get("trophy_name"),
        t.get("trophy_detail"), t.get("trophy_type"), t.get("trophy_icon_url"),
        int(t.get("trophy_hidden", False)), t.get("trophy_group_id", "default"),
        int(t.get("earned", False)), t.get("earned_date_time"),
        t.get("trophy_rarity"), t.get("trophy_earn_rate"),
        t.get("progress"), t.get("progress_rate"),
    ))


def write_game_with_trophies(conn: sqlite3.Connection, game: dict, trophies: list[dict]) -> None:
    upsert_game(conn, game)
    for t in trophies:
        upsert_trophy(conn, t)


def start_sync(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO sync_log (started_at) VALUES (datetime('now'))")
    return cur.lastrowid or 0


def finish_sync(conn: sqlite3.Connection, sync_id: int, status: str, trophies_added: int = 0,
                games_updated: int = 0, error_message: str | None = None) -> None:
    conn.execute("""
        UPDATE sync_log SET finished_at = datetime('now'), status = ?, trophies_added = ?,
            games_updated = ?, error_message = ?
        WHERE id = ?
    """, (status, trophies_added, games_updated, error_message, sync_id))


def get_last_sync_time(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute(
        "SELECT started_at FROM sync_log WHERE status = 'success' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if row:
        return datetime.fromisoformat(row["started_at"])
    return None


def game_exists(conn: sqlite3.Connection, np_comm_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM games WHERE np_communication_id = ?", (np_comm_id,)
    ).fetchone()
    return row is not None


def get_games(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM games ORDER BY title_name COLLATE NOCASE"
    ).fetchall()


def get_game_stats(conn: sqlite3.Connection, np_comm_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM game_stats WHERE np_communication_id = ?", (np_comm_id,)
    ).fetchone()


def update_game_stats(conn: sqlite3.Connection, np_comm_id: str,
                      title_id: str | None,
                      total_seconds: int,
                      play_count: int | None,
                      first_played: str | None,
                      last_played: str | None) -> None:
    old = conn.execute(
        "SELECT total_seconds FROM game_stats WHERE np_communication_id = ?",
        (np_comm_id,)
    ).fetchone()

    conn.execute("""
        INSERT OR REPLACE INTO game_stats
            (np_communication_id, title_id, total_seconds, play_count, first_played, last_played)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (np_comm_id, title_id, total_seconds, play_count or 0,
          first_played, last_played))

    if old is not None:
        delta = total_seconds - old["total_seconds"]
        if delta > 0:
            play_date = last_played[:10] if last_played else date.today().isoformat()
            conn.execute("""
                INSERT INTO play_delta_history (np_communication_id, date, delta_seconds)
                VALUES (?, ?, ?)
                ON CONFLICT(np_communication_id, date)
                DO UPDATE SET delta_seconds = delta_seconds + excluded.delta_seconds
            """, (np_comm_id, play_date, delta))


def get_play_time(conn: sqlite3.Connection, np_comm_id: str,
                  since: str, until: str) -> int:
    row = conn.execute("""
        SELECT COALESCE(SUM(delta_seconds), 0) as total
        FROM play_delta_history
        WHERE np_communication_id = ? AND date >= ? AND date <= ?
    """, (np_comm_id, since, until)).fetchone()
    return row["total"] if row else 0


def get_total_play_time(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(total_seconds), 0) as total FROM game_stats"
    ).fetchone()
    return row["total"] if row else 0


def get_total_play_delta(conn: sqlite3.Connection,
                         since: str, until: str) -> int:
    row = conn.execute("""
        SELECT COALESCE(SUM(delta_seconds), 0) as total
        FROM play_delta_history
        WHERE date >= ? AND date <= ?
    """, (since, until)).fetchone()
    return row["total"] if row else 0


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()


def get_daily_play_time(conn: sqlite3.Connection,
                        year: int, month: int) -> dict[str, int]:
    since, until = _month_bounds(year, month)
    rows = conn.execute("""
        SELECT date, COALESCE(SUM(delta_seconds), 0) as total
        FROM play_delta_history
        WHERE date >= ? AND date < ?
        GROUP BY date
    """, (since, until)).fetchall()
    return {r["date"]: r["total"] for r in rows}


def get_daily_play_details(conn: sqlite3.Connection,
                           date_str: str) -> list[dict]:
    return conn.execute("""
        SELECT g.title_name, pdh.delta_seconds
        FROM play_delta_history pdh
        JOIN games g ON g.np_communication_id = pdh.np_communication_id
        WHERE pdh.date = ? AND pdh.delta_seconds > 0
        ORDER BY pdh.delta_seconds DESC
    """, (date_str,)).fetchall()


def set_manual_play_time(conn: sqlite3.Connection,
                         np_comm_id: str,
                         total_seconds: int) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO game_stats
            (np_communication_id, title_id, total_seconds, play_count)
        VALUES (?, NULL, ?, 0)
    """, (np_comm_id, total_seconds))


def get_game(conn: sqlite3.Connection, np_comm_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM games WHERE np_communication_id = ?", (np_comm_id,)
    ).fetchone()


def get_trophies(conn: sqlite3.Connection, np_comm_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM trophies WHERE np_communication_id = ? ORDER BY trophy_id",
        (np_comm_id,)
    ).fetchall()


def get_recent_earned(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT t.*, g.title_name, g.title_icon_url
        FROM trophies t
        JOIN games g ON g.np_communication_id = t.np_communication_id
        WHERE t.earned = 1 AND t.earned_date_time IS NOT NULL
        ORDER BY t.earned_date_time DESC
        LIMIT ?
    """, (limit,)).fetchall()


def get_trophy_summary(conn: sqlite3.Connection) -> dict:
    row = conn.execute("""
        SELECT
            COUNT(DISTINCT np_communication_id) as total_games,
            SUM(CASE WHEN earned = 1 THEN 1 ELSE 0 END) as total_earned,
            COUNT(*) as total_trophies,
            SUM(CASE WHEN trophy_type = 'platinum' AND earned = 1 THEN 1 ELSE 0 END) as platinum,
            SUM(CASE WHEN trophy_type = 'gold' AND earned = 1 THEN 1 ELSE 0 END) as gold,
            SUM(CASE WHEN trophy_type = 'silver' AND earned = 1 THEN 1 ELSE 0 END) as silver,
            SUM(CASE WHEN trophy_type = 'bronze' AND earned = 1 THEN 1 ELSE 0 END) as bronze
        FROM trophies
    """).fetchone()
    return dict(row) if row else {}


def get_earned_by_date_range(conn: sqlite3.Connection, since: str, until: str) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT DATE(earned_date_time) as day, COUNT(*) as count
        FROM trophies
        WHERE earned = 1 AND earned_date_time >= ? AND earned_date_time < ?
        GROUP BY DATE(earned_date_time)
        ORDER BY day
    """, (since, until)).fetchall()


def get_trophies_by_date(conn: sqlite3.Connection, date_str: str) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT t.*, g.title_name
        FROM trophies t
        JOIN games g ON g.np_communication_id = t.np_communication_id
        WHERE t.earned = 1 AND DATE(t.earned_date_time) = ?
        ORDER BY t.earned_date_time
    """, (date_str,)).fetchall()


def get_consecutive_days(conn: sqlite3.Connection) -> int:
    rows = conn.execute("""
        SELECT DISTINCT DATE(earned_date_time) as day
        FROM trophies
        WHERE earned = 1 AND earned_date_time IS NOT NULL
        ORDER BY day DESC
    """).fetchall()

    if not rows:
        return 0

    streak = 0
    expected = date.today()

    for row in rows:
        d = date.fromisoformat(row["day"])
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d < expected:
            break
        # skip future dates (shouldn't happen, but defensive)

    return streak


def get_earned_month(conn: sqlite3.Connection, year: int, month: int) -> int:
    row = conn.execute("""
        SELECT COUNT(*) as count FROM trophies
        WHERE earned = 1
            AND strftime('%Y', earned_date_time) = ?
            AND strftime('%m', earned_date_time) = ?
    """, (str(year), f"{month:02d}")).fetchone()
    return row["count"] if row else 0


def upsert_friend(conn: sqlite3.Connection, f: dict) -> None:
    conn.execute("""
        INSERT INTO friends_cache
            (account_id, online_id, trophy_level, platinum, gold, silver, bronze,
             is_private, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id)
        DO UPDATE SET
            online_id = excluded.online_id,
            trophy_level = excluded.trophy_level,
            platinum = excluded.platinum,
            gold = excluded.gold,
            silver = excluded.silver,
            bronze = excluded.bronze,
            is_private = excluded.is_private,
            fetched_at = excluded.fetched_at
    """, (
        f["account_id"], f["online_id"], f.get("trophy_level"),
        f.get("platinum", 0), f.get("gold", 0), f.get("silver", 0),
        f.get("bronze", 0), f.get("is_private", 0), f["fetched_at"],
    ))


def upsert_friend_game(conn: sqlite3.Connection, fg: dict) -> None:
    conn.execute("""
        INSERT INTO friend_game_cache
            (account_id, np_communication_id, progress,
             earned_platinum, earned_gold, earned_silver, earned_bronze,
             is_private, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id, np_communication_id)
        DO UPDATE SET
            progress = excluded.progress,
            earned_platinum = excluded.earned_platinum,
            earned_gold = excluded.earned_gold,
            earned_silver = excluded.earned_silver,
            earned_bronze = excluded.earned_bronze,
            is_private = excluded.is_private,
            fetched_at = excluded.fetched_at
    """, (
        fg["account_id"], fg["np_communication_id"], fg.get("progress"),
        fg.get("earned_platinum", 0), fg.get("earned_gold", 0),
        fg.get("earned_silver", 0), fg.get("earned_bronze", 0),
        fg.get("is_private", 0), fg["fetched_at"],
    ))


def get_friends_leaderboard(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT *, (COALESCE(platinum,0) + COALESCE(gold,0)
                   + COALESCE(silver,0) + COALESCE(bronze,0)) as total
        FROM friends_cache
        ORDER BY trophy_level DESC
    """).fetchall()


def get_friend_game_comparison(conn: sqlite3.Connection,
                                np_comm_id: str) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT fgc.*, fc.online_id,
            (COALESCE(earned_platinum,0) + COALESCE(earned_gold,0)
             + COALESCE(earned_silver,0) + COALESCE(earned_bronze,0)) as earned_total
        FROM friend_game_cache fgc
        JOIN friends_cache fc ON fc.account_id = fgc.account_id
        WHERE fgc.np_communication_id = ?
        ORDER BY earned_total DESC
    """, (np_comm_id,)).fetchall()


def get_friend_comparison_detail(conn: sqlite3.Connection,
                                  friend_account_id: str) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT
          g.title_name, g.platform,
          g.progress AS my_progress,
          g.earned_platinum AS my_plat, g.earned_gold AS my_gold,
          g.earned_silver AS my_silver, g.earned_bronze AS my_bronze,
          COALESCE(gs.total_seconds, 0) AS my_seconds,
          fgc.progress AS friend_progress,
          fgc.earned_platinum AS friend_plat, fgc.earned_gold AS friend_gold,
          fgc.earned_silver AS friend_silver, fgc.earned_bronze AS friend_bronze
        FROM friend_game_cache fgc
        JOIN games g ON g.np_communication_id = fgc.np_communication_id
        LEFT JOIN game_stats gs ON gs.np_communication_id = fgc.np_communication_id
        WHERE fgc.account_id = ?
          AND fgc.is_private = 0
        ORDER BY g.title_name
    """, (friend_account_id,)).fetchall()


def get_friends_fetched_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT MAX(fetched_at) as fetched_at FROM friends_cache"
    ).fetchone()
    return row["fetched_at"] if row and row["fetched_at"] else None


