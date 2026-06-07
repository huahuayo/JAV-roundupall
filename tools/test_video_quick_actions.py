"""Unit tests for shared video quick-action controller."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.library_index import IndexedVideo
from src.ui.video_quick_actions import VideoActionsController, selection_from_payload


class VideoQuickActionsTests(unittest.TestCase):
    def test_selection_from_indexed_video(self) -> None:
        video = IndexedVideo(
            code="ABC-123",
            title="Sample Title",
            folder_path="C:\\lib\\actress",
            video_path="C:\\lib\\actress\\ABC-123.mp4",
            actress_name="Tester",
            actress_names=["Tester"],
            categories=["TagA"],
            category_key="video_downloaded",
            metadata_path="",
            cover_path="",
            detail_url="",
        )
        data = selection_from_payload(video)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data["code"], "ABC-123")
        self.assertEqual(data["label"], "Sample Title")
        self.assertEqual(data["category_key"], "video_downloaded")

    def test_open_video_requires_selection(self) -> None:
        app = MagicMock()
        ctrl = VideoActionsController(app)
        ctrl.open_video()
        app.set_status.assert_called_with("请先在列表中选择一部影片")

    def test_copy_code(self) -> None:
        app = MagicMock()
        ctrl = VideoActionsController(app)
        ctrl.set_selection({"code": "XYZ-001", "folder_path": "", "video_path": ""})
        ctrl.copy_code()
        app.clipboard_clear.assert_called_once()
        app.clipboard_append.assert_called_with("XYZ-001")

    def test_mark_refined_navigates(self) -> None:
        app = MagicMock()
        ctrl = VideoActionsController(app)
        ctrl.set_selection(
            {
                "code": "XYZ-001",
                "folder_path": "C:\\a",
                "video_path": "C:\\a\\x.mp4",
                "label": "Title",
            }
        )
        with patch("src.ui.video_quick_actions.add_refined_video") as add:
            ctrl.mark_refined()
            add.assert_called_once()
            app.navigate_to_drain.assert_called_once()

    def test_delete_video_calls_callbacks(self) -> None:
        app = MagicMock()
        app.trash_tab = MagicMock()
        app.library_tab = MagicMock()
        after = MagicMock()
        ctrl = VideoActionsController(app, on_after_delete=after)
        ctrl.set_selection(
            {
                "code": "XYZ-001",
                "folder_path": "C:\\a",
                "video_path": "C:\\a\\x.mp4",
                "label": "Title",
            }
        )
        with patch("src.ui.video_quick_actions.simpledialog.askstring", return_value="test reason"):
            with patch("src.ui.video_quick_actions.load_video_detail") as load_detail:
                load_detail.return_value.metadata = {"标题": "Title"}
                with patch("src.ui.video_quick_actions.move_video_to_recycle") as move:
                    ctrl.delete_video()
                    move.assert_called_once()
                    after.assert_called_once()
                    app.library_tab.refresh_tree.assert_called_once()
                    app.trash_tab.refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
