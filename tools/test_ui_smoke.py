"""Smoke tests for UI wiring and task handlers (no GUI mainloop)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = None

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._app is not None:
            cls._app.destroy()

    def setUp(self) -> None:
        if UiSmokeTests._app is None:
            from src.app import JavManagerApp

            UiSmokeTests._app = JavManagerApp()

    @property
    def app(self):
        return UiSmokeTests._app

    def test_layout_widgets_exist(self) -> None:
        required = [
            "page_stack",
            "page_frames",
            "library_tab",
            "actress_tab",
            "category_tab",
            "status_label",
            "edge_status_label",
            "header_code_entry",
            "global_task_progress",
            "_nav_buttons",
            "_pending_download_progress",
            "_pending_download_sync_label",
            "_pending_download_start_btn",
            "_magnet_saved_progress",
            "_magnet_saved_start_btn",
            "_video_downloaded_progress",
            "_video_downloaded_start_btn",
            "_video_cracked_progress",
            "_video_cracked_start_btn",
            "_video_cracked_metadata_btn",
            "_loose_video_progress",
            "_loose_video_start_btn",
        ]
        for name in required:
            self.assertTrue(hasattr(self.app, name), f"missing widget: {name}")
        self.assertIn("settings", self.app._nav_buttons)
        self.assertIn("library", self.app.page_frames)

    def test_library_path_containers_all_keys(self) -> None:
        from src.library_location_settings import LIBRARY_LOCATION_KEYS

        for key, _ in LIBRARY_LOCATION_KEYS:
            self.assertIn(key, self.app._library_path_containers, key)

    def test_task_starters_call_bridge(self) -> None:
        ok = {"ok": True, "message": "started"}
        scan_result = ([{"folder_name": "test", "codes": []}], ["C:\\test"])
        starters = [
            ("_start_pending_download_task", "request_pending_download_sync", None),
            ("_start_magnet_saved_task", "request_magnet_saved_sync", None),
            ("_start_video_downloaded_task", "request_video_downloaded_sync", None),
            ("_start_video_cracked_task", "request_video_cracked_sync", scan_result),
            ("_start_loose_video_task", "request_loose_video_sync", None),
            ("_start_video_cracked_metadata_task", "request_video_metadata_sync", scan_result),
        ]
        from src import bridge_server

        for method_name, bridge_method, scan_payload in starters:
            with self.subTest(method=method_name):
                with patch.object(bridge_server.bridge_server, bridge_method, return_value=ok) as mocked:
                    if scan_payload is not None:
                        with patch.object(
                            self.app,
                            "_run_library_scan_task",
                            side_effect=lambda *, on_scanned, **kwargs: on_scanned(scan_payload),
                        ):
                            getattr(self.app, method_name)()
                    else:
                        getattr(self.app, method_name)()
                    mocked.assert_called_once()

    def test_bridge_progress_handlers_no_crash(self) -> None:
        events = [
            ("pending_download_sync_progress", "_update_pending_download_progress"),
            ("magnet_saved_sync_progress", "_update_magnet_saved_progress"),
            ("video_downloaded_sync_progress", "_update_video_downloaded_progress"),
            ("video_cracked_sync_progress", "_update_video_cracked_progress"),
            ("loose_video_sync_progress", "_update_loose_video_progress"),
            ("video_metadata_sync_progress", "_update_video_metadata_progress"),
        ]
        payload = {"current": 1, "total": 3, "message": "test", "phase": "marking"}
        for _event, handler in events:
            with self.subTest(handler=handler):
                getattr(self.app, handler)(payload)

    def test_bridge_done_handlers_no_crash(self) -> None:
        payload = {"success_count": 1, "total": 1, "log_paths": [], "folder_results": []}
        self.app._update_pending_download_done(payload)
        self.app._update_magnet_saved_done(payload)
        self.app._update_video_downloaded_done(payload)
        self.app._update_video_cracked_done(payload)
        self.app._update_loose_video_done(payload)
        self.app._update_video_metadata_done({**payload, "library_kind": "video_downloaded"})
        self.app._update_video_metadata_done({**payload, "library_kind": "video_cracked"})

    def test_extension_disconnect_resets_buttons(self) -> None:
        self.app._pending_download_start_btn.configure(state="disabled")
        with patch.object(self.app, "_reset_sync_start_buttons") as reset:
            with patch("src.app.bridge_server.reset_stuck_sync_flags") as clear_flags:
                self.app._on_extension_disconnected("edge")
                clear_flags.assert_called_once()
                reset.assert_called_once()

    def test_library_tree_builds(self) -> None:
        from src.library_media_loader import build_library_tree

        tree = build_library_tree()
        self.assertEqual(len(tree), 5)
        labels = [node.label for node in tree]
        self.assertEqual(labels, ["待下载", "磁链已保存", "已下载", "已破解", "散片"])

    def test_refresh_library_tree(self) -> None:
        self.app._refresh_library_tree()

    def test_show_page_settings(self) -> None:
        self.app.show_page("settings")
        self.assertEqual(self.app._current_page, "settings")

    def test_category_and_actress_have_quick_actions(self) -> None:
        self.assertTrue(hasattr(self.app.category_tab, "_actions"))
        self.assertTrue(hasattr(self.app.actress_tab, "_actions"))
        self.assertTrue(hasattr(self.app.library_tab, "_actions"))
        self.assertTrue(hasattr(self.app.drain_tab, "_actions"))

    def test_save_library_locations_roundtrip(self) -> None:
        from src.pending_download_scanner import PENDING_DOWNLOAD_KEY

        self.app._add_library_path_row(PENDING_DOWNLOAD_KEY, "C:\\test-path")
        with patch("src.app.messagebox.showerror") as err:
            with patch("src.app.save_library_locations") as save:
                save.return_value = self.app._collect_library_locations_from_ui()
                self.app._save_library_locations()
                save.assert_called_once()
                err.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
