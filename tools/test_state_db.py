"""Quick tests for unified state database and catalog persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.catalog_db import read_catalog_from_db, rebind_catalog_folder, replace_catalog_in_db
from src.catalog_reader import CatalogEntry, read_catalog, upsert_catalog_rows, write_catalog
from src.state_db import get_state_db_path, init_state_database, set_state_db_path


class StateDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "test_state.db"
        set_state_db_path(str(self._db_path))
        init_state_database()

    def tearDown(self) -> None:
        import gc

        gc.collect()
        self._tmpdir.cleanup()

    def test_catalog_persists_without_local_folder(self) -> None:
        folder = str(Path(self._tmpdir.name) / "missing" / "ActressA")
        entries = {
            "ABC-123": CatalogEntry(
                code="ABC-123",
                title="Test",
                javdb_done=True,
                metadata_done=False,
                media_done=False,
            )
        }
        write_catalog(folder, entries, actress_name="ActressA")
        loaded = read_catalog_from_db(folder)
        self.assertIn("ABC-123", loaded)
        self.assertTrue(loaded["ABC-123"].javdb_done)
        self.assertFalse(loaded["ABC-123"].metadata_done)

    def test_rebind_by_actress_name_on_new_path(self) -> None:
        old_folder = Path(self._tmpdir.name) / "old_root" / "完成 ActressB"
        new_folder = Path(self._tmpdir.name) / "new_root" / "完成 ActressB"
        new_folder.parent.mkdir(parents=True, exist_ok=True)
        replace_catalog_in_db(
            str(old_folder),
            {"XYZ-001": CatalogEntry(code="XYZ-001", javdb_done=True)},
            actress_name="ActressB",
        )
        loaded = read_catalog(str(new_folder))
        self.assertIn("XYZ-001", loaded)
        self.assertTrue(loaded["XYZ-001"].javdb_done)

    def test_folder_rename_updates_catalog(self) -> None:
        old_folder = str(Path(self._tmpdir.name) / "sync" / "ActressC")
        new_folder = str(Path(self._tmpdir.name) / "sync" / "完成 ActressC")
        replace_catalog_in_db(
            old_folder,
            {"DEF-999": CatalogEntry(code="DEF-999")},
            actress_name="ActressC",
        )
        count = rebind_catalog_folder(old_folder, new_folder)
        self.assertEqual(count, 1)
        self.assertIn("DEF-999", read_catalog_from_db(new_folder))

    def test_upsert_marks_metadata_done(self) -> None:
        folder = str(Path(self._tmpdir.name) / "meta" / "ActressD")
        touched = upsert_catalog_rows(
            folder,
            actress_name="ActressD",
            rows=[{"code": "GHI-100"}],
            metadata_done=True,
        )
        self.assertEqual(touched, 1)
        entry = read_catalog(folder)["GHI-100"]
        self.assertTrue(entry.metadata_done)

    def test_default_db_path_under_app_dir(self) -> None:
        set_state_db_path("")
        path = get_state_db_path()
        self.assertTrue(path.name.endswith(".db"))


if __name__ == "__main__":
    unittest.main()
