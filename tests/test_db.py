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

        daily_jan = db.get_daily_play_time(self.conn, 2026, 1)
        self.assertEqual(daily_jan, {"2026-01-01": 1800})

        daily_jul = db.get_daily_play_time(self.conn, 2026, 7)
        self.assertEqual(daily_jul, {"2026-07-15": 7200})

        empty = db.get_daily_play_time(self.conn, 2026, 6)
        self.assertEqual(empty, {})

    def test_get_daily_play_details(self):
        game1 = self._sample_game(np_communication_id="NPWR_A_00", title_name="Game A")
        db.upsert_game(self.conn, game1)
        db.update_game_stats(self.conn, "NPWR_A_00", "CUSA_A", 0, 0, None, None)
        db.update_game_stats(self.conn, "NPWR_A_00", "CUSA_A", 1800, 1,
                             "2026-07-01T00:00:00", "2026-07-15T00:00:00")
        self.conn.commit()

        details = db.get_daily_play_details(self.conn, "2026-07-15")
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["title_name"], "Game A")
        self.assertEqual(details[0]["delta_seconds"], 1800)

        details_empty = db.get_daily_play_details(self.conn, "2026-07-14")
        self.assertEqual(details_empty, [])

    def test_upsert_friend(self):
        db.upsert_friend(self.conn, {
            "account_id": "acc1", "online_id": "FriendA",
            "trophy_level": 10, "platinum": 5, "gold": 10,
            "silver": 50, "bronze": 200, "is_private": 0,
            "fetched_at": "2026-07-15T12:00:00",
        })
        db.upsert_friend(self.conn, {
            "account_id": "acc2", "online_id": "FriendB",
            "trophy_level": 5, "platinum": 1, "gold": 5,
            "silver": 20, "bronze": 100, "is_private": 0,
            "fetched_at": "2026-07-15T12:00:00",
        })
        db.upsert_friend(self.conn, {
            "account_id": "acc3", "online_id": "PrivateC",
            "trophy_level": 0, "platinum": 0, "gold": 0,
            "silver": 0, "bronze": 0, "is_private": 1,
            "fetched_at": "2026-07-15T12:00:00",
        })
        self.conn.commit()

        rows = db.get_friends_leaderboard(self.conn)
        self.assertEqual(len(rows), 3)
        # FriendA: 5+10+50+200 = 265
        self.assertEqual(rows[0]["online_id"], "FriendA")
        self.assertEqual(rows[0]["total"], 265)
        # FriendB: 1+5+20+100 = 126
        self.assertEqual(rows[1]["online_id"], "FriendB")
        self.assertEqual(rows[1]["total"], 126)
        # PrivateC: 0
        self.assertEqual(rows[2]["online_id"], "PrivateC")
        self.assertEqual(rows[2]["total"], 0)
        self.assertEqual(rows[2]["is_private"], 1)

    def test_upsert_friend_updates_existing(self):
        db.upsert_friend(self.conn, {
            "account_id": "acc1", "online_id": "OldName",
            "trophy_level": 5, "platinum": 1, "gold": 2,
            "silver": 10, "bronze": 50, "is_private": 0,
            "fetched_at": "2026-07-15T12:00:00",
        })
        self.conn.commit()
        rows = db.get_friends_leaderboard(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["online_id"], "OldName")
        self.assertEqual(rows[0]["total"], 1 + 2 + 10 + 50)

        db.upsert_friend(self.conn, {
            "account_id": "acc1", "online_id": "NewName",
            "trophy_level": 10, "platinum": 5, "gold": 10,
            "silver": 50, "bronze": 200, "is_private": 0,
            "fetched_at": "2026-07-15T13:00:00",
        })
        self.conn.commit()
        rows = db.get_friends_leaderboard(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["online_id"], "NewName")
        self.assertEqual(rows[0]["total"], 265)

    def test_get_friends_fetched_at(self):
        self.assertIsNone(db.get_friends_fetched_at(self.conn))
        db.upsert_friend(self.conn, {
            "account_id": "acc1", "online_id": "A",
            "trophy_level": 0, "platinum": 0, "gold": 0,
            "silver": 0, "bronze": 0, "is_private": 0,
            "fetched_at": "2026-07-14T12:00:00",
        })
        db.upsert_friend(self.conn, {
            "account_id": "acc2", "online_id": "B",
            "trophy_level": 0, "platinum": 0, "gold": 0,
            "silver": 0, "bronze": 0, "is_private": 0,
            "fetched_at": "2026-07-15T12:00:00",
        })
        self.conn.commit()
        self.assertEqual(db.get_friends_fetched_at(self.conn), "2026-07-15T12:00:00")

    def test_upsert_friend_game_and_comparison(self):
        db.upsert_friend(self.conn, {
            "account_id": "acc1", "online_id": "FriendA",
            "trophy_level": 0, "platinum": 0, "gold": 0,
            "silver": 0, "bronze": 0, "is_private": 0,
            "fetched_at": "2026-07-15T12:00:00",
        })
        db.upsert_friend(self.conn, {
            "account_id": "acc2", "online_id": "PrivateC",
            "trophy_level": 0, "platinum": 0, "gold": 0,
            "silver": 0, "bronze": 0, "is_private": 1,
            "fetched_at": "2026-07-15T12:00:00",
        })
        db.upsert_friend_game(self.conn, {
            "account_id": "acc1", "np_communication_id": "NPWR_GAME_00",
            "progress": 100, "earned_platinum": 1, "earned_gold": 2,
            "earned_silver": 5, "earned_bronze": 20, "is_private": 0,
            "fetched_at": "2026-07-15T12:00:00",
        })
        db.upsert_friend_game(self.conn, {
            "account_id": "acc2", "np_communication_id": "NPWR_GAME_00",
            "progress": 0, "earned_platinum": 0, "earned_gold": 0,
            "earned_silver": 0, "earned_bronze": 0, "is_private": 1,
            "fetched_at": "2026-07-15T12:00:00",
        })
        self.conn.commit()

        rows = db.get_friend_game_comparison(self.conn, "NPWR_GAME_00")
        self.assertEqual(len(rows), 2)
        # FriendA: 1+2+5+20 = 28
        self.assertEqual(rows[0]["online_id"], "FriendA")
        self.assertEqual(rows[0]["earned_total"], 28)
        self.assertEqual(rows[0]["progress"], 100)
        # PrivateC
        self.assertEqual(rows[1]["online_id"], "PrivateC")
        self.assertEqual(rows[1]["is_private"], 1)
        self.assertEqual(rows[1]["earned_total"], 0)


if __name__ == "__main__":
    unittest.main()
