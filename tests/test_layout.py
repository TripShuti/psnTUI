import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from psntui import auth, db
from psntui.tui.app import psnTUI


class TestRightPanelLayout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        db.set_db_path(self.tmp)
        db.init_db()
        self.conn = db.get_conn()

        game = {
            "np_communication_id": "NPWR_TEST_00",
            "np_title_id": "CUSA_TEST",
            "title_name": "Test Game",
            "platform": "PS5",
            "title_icon": None,
            "category": "ps5_native",
            "progress": 100,
            "earned_trophies": 10,
            "defined_trophies": 10,
            "np_service_name": "trophy",
        }
        db.upsert_game(self.conn, game)
        db.update_game_stats(self.conn, "NPWR_TEST_00",
                             "CUSA_TEST", 3600, 1,
                             "2026-01-01T00:00:00", "2026-07-01T00:00:00")
        self.conn.commit()

    def tearDown(self):
        db.close_conn()
        os.unlink(self.tmp)

    def test_right_panel_fits_no_scroll(self):
        with (
            patch.object(auth, "is_authenticated", return_value=True),
            patch.object(auth, "load_config",
                         return_value={"npsso": "test", "online_id": "test"}),
        ):
            app = psnTUI()

            async def run():
                async with app.run_test(size=(190, 50)) as pilot:
                    await pilot.pause()
                    main = app.screen

                    cards = [
                        "recent-card",
                        "heatmap-card",
                        "month-card",
                        "playtime-card",
                        "rarity-card",
                        "hotkey-hint",
                    ]
                    for cid in cards:
                        w = main.query_one(f"#{cid}")
                        r = w.region
                        self.assertGreater(r.height, 0, f"{cid} has zero height")
                        self.assertGreater(r.width, 0, f"{cid} has zero width")

                    hotkey = main.query_one("#hotkey-hint")
                    self.assertLessEqual(
                        hotkey.region.y + hotkey.region.height, 50,
                        "hotkey-hint extends beyond terminal bottom"
                    )

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
