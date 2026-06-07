from src.actress_folder_store import record_actress_folder, lookup_actress_folder_record, sanitize_actress_name
from src.magnet_txt_batch_store import (
    build_merged_summary_text,
    find_actress_folder,
    merge_magnet_link_file,
    parse_magnet_summary_txt,
    write_magnet_batch_files,
)
from src.state_db import init_state_database, set_state_db_path


def test_parse_summary() -> None:
    text = """
4K资源：
SSIS-100
ABC-200

字幕资源：
SSIS-101

高清资源：
SSIS-300

无合适资源：
SSIS-400
"""
    parsed = parse_magnet_summary_txt(text)
    assert parsed["four_k"] == ["SSIS-100", "ABC-200"]
    assert parsed["subtitle"] == ["SSIS-101"]
    assert parsed["hd"] == ["SSIS-300"]
    assert parsed["none"] == ["SSIS-400"]
    codes = [row["code"] for row in parsed["manual_match"]]
    assert codes == ["SSIS-100", "ABC-200", "SSIS-300", "SSIS-400"]


def test_write_batch_files(tmp_path) -> None:
    written = write_magnet_batch_files(
        tmp_path,
        {
            "破解.txt": "magnet:?xt=urn:btih:abc\n",
            "总结.txt": "4K资源：\nSSIS-100\n",
        },
    )
    assert "破解.txt" in written
    assert (tmp_path / "破解.txt").read_text(encoding="utf-8").startswith("magnet:")


def test_merge_magnet_link_file(tmp_path) -> None:
    path = tmp_path / "破解.txt"
    path.write_text("magnet:?xt=urn:btih:aaa\n", encoding="utf-8")
    merged = merge_magnet_link_file(path, "magnet:?xt=urn:btih:bbb\nmagnet:?xt=urn:btih:aaa\n")
    lines = [line for line in merged.splitlines() if line]
    assert lines == ["magnet:?xt=urn:btih:aaa", "magnet:?xt=urn:btih:bbb"]


def test_merge_summary_updates_processed_codes_only() -> None:
    existing = """
4K资源：
OLD-100

字幕资源：
OLD-200

高清资源：
OLD-300

无合适资源：
OLD-400
"""
    new_summary = {
        "fourK": ["NEW-100"],
        "subtitle": [],
        "hd": ["NEW-300"],
        "none": ["NEW-500"],
    }
    merged = build_merged_summary_text(existing, new_summary, {"NEW-100", "NEW-300", "NEW-500"})
    parsed = parse_magnet_summary_txt(merged)
    assert parsed["four_k"] == ["NEW-100", "OLD-100"]
    assert parsed["subtitle"] == ["OLD-200"]
    assert parsed["hd"] == ["NEW-300", "OLD-300"]
    assert parsed["none"] == ["NEW-500", "OLD-400"]


def test_sanitize_actress_name() -> None:
    assert sanitize_actress_name("花咲澪\n\n 11 部影片") == "花咲澪"
    assert sanitize_actress_name("Test（3 部）") == "Test"
    assert sanitize_actress_name("  VR Queen  ") == "VR Queen"


def test_find_actress_folder_with_pending_sync_prefix(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "state.db"
    set_state_db_path(str(db_path))
    init_state_database()

    pending_root = tmp_path / "pending"
    pending_root.mkdir()
    actress_dir = pending_root / "1 花咲澪"
    actress_dir.mkdir()

    monkeypatch.setattr(
        "src.magnet_txt_batch_store.load_library_locations",
        lambda: {"pending_download": [str(pending_root)]},
    )
    found = find_actress_folder("花咲澪")
    assert found is not None
    assert found.resolve() == actress_dir.resolve()


def test_lookup_actress_folder_from_database(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "state.db"
    set_state_db_path(str(db_path))
    init_state_database()

    network_folder = tmp_path / "1 花咲澪"
    network_folder.mkdir()
    record_actress_folder(
        actress_name="花咲澪",
        javdb_id="abc123",
        folder_path=str(network_folder.resolve()),
        folder_name=network_folder.name,
        library_kind="pending_download",
    )

    monkeypatch.setattr(
        "src.magnet_txt_batch_store.load_library_locations",
        lambda: {"pending_download": [str(tmp_path / "empty")]},
    )

    record = lookup_actress_folder_record("花咲澪", javdb_id="abc123")
    assert record is not None
    assert record["source"] == "database"
    assert record["folder_path"] == str(network_folder.resolve())

    found = find_actress_folder("花咲澪", javdb_id="abc123")
    assert found is not None
    assert found.resolve() == network_folder.resolve()


def test_lookup_actress_folder_returns_db_without_path_verify(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    set_state_db_path(str(db_path))
    init_state_database()

    missing_folder = tmp_path / "network" / "1 花咲澪"
    record_actress_folder(
        actress_name="花咲澪",
        folder_path=str(missing_folder),
        folder_name=missing_folder.name,
        library_kind="pending_download",
    )

    record = lookup_actress_folder_record("花咲澪")
    assert record is not None
    assert record["source"] == "database"
    assert record["folder_path"] == str(missing_folder)
