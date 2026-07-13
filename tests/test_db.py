import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from psntui import db


class TestDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        db.set_db_path(self.tmp)
        db.init_db()
        self.conn = db.get_conn()

    def tearDown(self):
        import psntui.db
        psntui.db.close_conn()
        os.unlink(self.tmp)

    def _sample_game(self, **kwargs):
        data = {
            "np_communication_id": "NPWR12345_00",
            "np_title_id": "CUSA12345_00",
            "title_name": "Test Game",
            "title_icon_url": "https://example.com/icon.png",
            "platform": "PS5",
            "defined_bronze": 10,
            "defined_silver": 5,
            "defined_gold": 2,
            "defined_platinum": 1,
            "earned_bronze": 5,
            "earned_silver": 2,
            "earned_gold": 0,
            "earned_platinum": 0,
            "progress": 50,
            "last_updated_datetime": "2026-07-12T10:00:00",
        }
        data.update(kwargs)
        return data

    def _sample_trophy(self, trophy_id=1, **kwargs):
        data = {
            "np_communication_id": "NPWR12345_00",
            "trophy_id": trophy_id,
            "trophy_name": f"Trophy {trophy_id}",
            "trophy_detail": "Description",
            "trophy_type": "bronze",
            "trophy_icon_url": "https://example.com/t1.png",
            "trophy_hidden": False,
            "trophy_group_id": "default",
            "earned": True,
            "earned_date_time": f"2026-07-{11+trophy_id:02d}T10:00:00",
            "trophy_rarity": "common",
            "trophy_earn_rate": 80.0,
            "progress": None,
            "progress_rate": None,
        }
        data.update(kwargs)
        return data

    def test_init_db_creates_tables(self):
        tables = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r[0] for r in tables}
        self.assertIn("games", names)
        self.assertIn("trophies", names)
        self.assertIn("sync_log", names)

    def test_upsert_game(self):
        game = self._sample_game()
        db.upsert_game(self.conn, game)
        self.conn.commit()

        games = db.get_games(self.conn)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["title_name"], "Test Game")

    def test_upsert_game_updates_existing(self):
        game = self._sample_game()
        db.upsert_game(self.conn, game)
        self.conn.commit()

        game2 = self._sample_game(progress=75)
        db.upsert_game(self.conn, game2)
        self.conn.commit()

        games = db.get_games(self.conn)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["progress"], 75)

    def test_upsert_trophy(self):
        game = self._sample_game()
        db.upsert_game(self.conn, game)
        trophy = self._sample_trophy(1)
        db.upsert_trophy(self.conn, trophy)
        self.conn.commit()

        trophies = db.get_trophies(self.conn, "NPWR12345_00")
        self.assertEqual(len(trophies), 1)
        self.assertEqual(trophies[0]["trophy_name"], "Trophy 1")

    def test_get_recent_earned(self):
        game = self._sample_game()
        db.upsert_game(self.conn, game)
        for i in range(3):
            db.upsert_trophy(self.conn, self._sample_trophy(i))
        self.conn.commit()

        recent = db.get_recent_earned(self.conn, limit=2)
        self.assertEqual(len(recent), 2)

    def test_get_trophy_summary(self):
        game = self._sample_game()
        db.upsert_game(self.conn, game)
        for i in range(5):
            db.upsert_trophy(self.conn, self._sample_trophy(i))
        self.conn.commit()

        summary = db.get_trophy_summary(self.conn)
        self.assertEqual(summary["total_games"], 1)
        self.assertEqual(summary["total_earned"], 5)

    def test_game_exists(self):
        self.assertFalse(db.game_exists(self.conn, "NPWR12345_00"))
        game = self._sample_game()
        db.upsert_game(self.conn, game)
        self.conn.commit()
        self.assertTrue(db.game_exists(self.conn, "NPWR12345_00"))

    def test_sync_log(self):
        sid = db.start_sync(self.conn)
        db.finish_sync(self.conn, sid, "success", trophies_added=5, games_updated=2)
        self.conn.commit()

        last = db.get_last_sync_time(self.conn)
        self.assertIsNotNone(last)

    def test_consecutive_days(self):
        game = self._sample_game()
        db.upsert_game(self.conn, game)
        from datetime import date, timedelta
        today = date.today()
        for i in range(3):
            d = today - timedelta(days=i)
            db.upsert_trophy(self.conn, self._sample_trophy(
                trophy_id=i,
                earned_date_time=d.isoformat() + "T12:00:00",
            ))
        self.conn.commit()

        streak = db.get_consecutive_days(self.conn)
        self.assertGreaterEqual(streak, 1)

    def test_earned_month(self):
        game = self._sample_game()
        db.upsert_game(self.conn, game)
        db.upsert_trophy(self.conn, self._sample_trophy(
            trophy_id=1,
            earned_date_time="2026-07-15T10:00:00",
        ))
        self.conn.commit()

        count = db.get_earned_month(self.conn, 2026, 7)
        self.assertEqual(count, 1)

        count2 = db.get_earned_month(self.conn, 2026, 6)
        self.assertEqual(count2, 0)


    def test_get_daily_play_time(self):
        from datetime import date as dt_date
        today = dt_date.today()
        today_str = today.isoformat()
        today_year, today_month = today.year, today.month

        game1 = self._sample_game(np_communication_id="NPWR_A_00", title_name="Game A")
        game2 = self._sample_game(np_communication_id="NPWR_B_00", title_name="Game B")
        db.upsert_game(self.conn, game1)
        db.upsert_game(self.conn, game2)

        db.update_game_stats(self.conn, "NPWR_A_00", "CUSA_A", 0, 0, None, None)
        db.update_game_stats(self.conn, "NPWR_A_00", "CUSA_A", 1800, 1,
                             "2026-01-01T00:00:00", "2026-01-01T00:00:00")
        db.update_game_stats(self.conn, "NPWR_B_00", "CUSA_B", 0, 0, None, None)
        db.update_game_stats(self.conn, "NPWR_B_00", "CUSA_B", 7200, 2,
                             "2026-07-01T00:00:00", "2026-07-15T00:00:00")
        self.conn.commit()

        daily = db.get_daily_play_time(self.conn, today_year, today_month)
        self.assertIn(today_str, daily)
        self.assertEqual(daily[today_str], 9000)

        other_month = 6 if today_month != 6 else 5
        empty = db.get_daily_play_time(self.conn, today_year, other_month)
        self.assertEqual(empty, {})

    def test_get_daily_play_details(self):
        from datetime import date as dt_date
        today = dt_date.today()
        today_str = today.isoformat()

        game1 = self._sample_game(np_communication_id="NPWR_A_00", title_name="Game A")
        db.upsert_game(self.conn, game1)
        db.update_game_stats(self.conn, "NPWR_A_00", "CUSA_A", 0, 0, None, None)
        db.update_game_stats(self.conn, "NPWR_A_00", "CUSA_A", 1800, 1,
                             "2026-07-01T00:00:00", "2026-07-15T00:00:00")
        self.conn.commit()

        details = db.get_daily_play_details(self.conn, today_str)
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["title_name"], "Game A")
        self.assertEqual(details[0]["delta_seconds"], 1800)

        details_empty = db.get_daily_play_details(self.conn, "2026-07-14")
        self.assertEqual(details_empty, [])


if __name__ == "__main__":
    unittest.main()
