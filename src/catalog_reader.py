"""Read and update per-folder 目录.txt catalogs with per-task completion flags."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.parser import normalize_code

CATALOG_FILENAME = "目录.txt"

TASK_JAVDB = "javdb"
TASK_METADATA = "metadata"
TASK_MEDIA = "media"

YES_VALUES = frozenset({"是", "yes", "y", "1", "true", "done", "✓", "已完成"})
NO_VALUES = frozenset({"否", "no", "n", "0", "false", "-", "未完成"})


@dataclass
class CatalogEntry:
    code: str
    title: str = "-"
    detail_url: str = "-"
    local_file: str = "-"
    date: str = "-"
    metadata_done: bool = False
    media_done: bool = False
    javdb_done: bool = False


def _parse_flag(text: str, *, default: bool = False) -> bool:
    raw = str(text or "").strip().lower()
    if raw in YES_VALUES:
        return True
    if raw in NO_VALUES:
        return False
    return default


def _format_flag(value: bool) -> str:
    return "是" if value else "否"


def _catalog_header_lines(actress_name: str) -> list[str]:
    return [
        "# JAV Manager 目录",
        f"# 女优: {actress_name}",
        "# 格式: 番号 | 标题 | 详情页 | 本地文件 | 添加日期 | 元数据 | 封面预览 | JavDB同步",
        "# 任务列填 是/否；执行任务前会读取本文件，仅处理对应列为「否」的番号",
        "",
    ]


def parse_catalog_line(parts: list[str]) -> CatalogEntry | None:
    if not parts:
        return None
    code = normalize_code(parts[0])
    if not code:
        return None

    title = parts[1] if len(parts) > 1 else "-"
    detail_url = parts[2] if len(parts) > 2 else "-"
    local_file = parts[3] if len(parts) > 3 else "-"
    date = parts[4] if len(parts) > 4 else "-"

    if len(parts) <= 5:
        return CatalogEntry(
            code=code,
            title=title,
            detail_url=detail_url,
            local_file=local_file,
            date=date,
            metadata_done=False,
            media_done=False,
            javdb_done=True,
        )

    return CatalogEntry(
        code=code,
        title=title,
        detail_url=detail_url,
        local_file=local_file,
        date=date,
        metadata_done=_parse_flag(parts[5]),
        media_done=_parse_flag(parts[6]) if len(parts) > 6 else False,
        javdb_done=_parse_flag(parts[7]) if len(parts) > 7 else False,
    )


def format_catalog_line(entry: CatalogEntry) -> str:
    return " | ".join(
        [
            entry.code,
            entry.title or "-",
            entry.detail_url or "-",
            entry.local_file or "-",
            entry.date or "-",
            _format_flag(entry.metadata_done),
            _format_flag(entry.media_done),
            _format_flag(entry.javdb_done),
        ]
    )


def _read_catalog_from_txt(catalog_path: Path) -> dict[str, CatalogEntry]:
    entries: dict[str, CatalogEntry] = {}
    if not catalog_path.is_file():
        return entries
    try:
        content = catalog_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entries
    for line in content.splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        parts = [part.strip() for part in text.split("|")]
        entry = parse_catalog_line(parts)
        if entry:
            entries[entry.code] = entry
    return entries


def read_catalog(folder_path: str | Path) -> dict[str, CatalogEntry]:
    from src.catalog_db import read_catalog_from_db, replace_catalog_in_db

    entries = read_catalog_from_db(folder_path)
    if entries:
        return entries

    catalog_path = Path(folder_path) / CATALOG_FILENAME
    entries = _read_catalog_from_txt(catalog_path)
    if entries:
        actress_name = _guess_actress_name(Path(folder_path), catalog_path, entries)
        replace_catalog_in_db(folder_path, entries, actress_name=actress_name)
    return entries


def _guess_actress_name(root: Path, catalog_path: Path, entries: dict[str, CatalogEntry]) -> str:
    if catalog_path.is_file():
        try:
            for line in catalog_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# 女优:"):
                    name = line.split(":", 1)[1].strip()
                    if name:
                        return name
        except OSError:
            pass
    return root.name


def read_catalog_codes(folder_path: str | Path) -> set[str]:
    return set(read_catalog(folder_path).keys())


def write_catalog(folder_path: str | Path, entries: dict[str, CatalogEntry], *, actress_name: str = "") -> None:
    from src.catalog_db import replace_catalog_in_db

    root = Path(folder_path)
    key = str(folder_path or "").strip()
    if not key or not entries:
        return

    catalog_path = root / CATALOG_FILENAME if root.is_dir() else None
    name = actress_name.strip()
    if not name and catalog_path and catalog_path.is_file():
        try:
            for line in catalog_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# 女优:"):
                    name = line.split(":", 1)[1].strip()
                    break
        except OSError:
            name = ""
    if not name:
        name = root.name if root.name else Path(key).name

    replace_catalog_in_db(folder_path, entries, actress_name=name)

    if not catalog_path:
        return

    lines = _catalog_header_lines(name)
    for code in sorted(entries.keys(), key=lambda item: item.upper()):
        lines.append(format_catalog_line(entries[code]))
    lines.append("")
    catalog_path.write_text("\n".join(lines), encoding="utf-8")


def _resolve_local_file_path(row: dict[str, Any], folder_root: Path) -> str:
    source_path = str(row.get("source_path") or "").strip()
    if source_path:
        return source_path
    source_file = str(row.get("source_file") or "").strip()
    if not source_file:
        return ""
    candidate = folder_root / source_file
    if candidate.is_file():
        return str(candidate.resolve())
    return source_file


def upsert_catalog_rows(
    folder_path: str | Path,
    *,
    actress_name: str,
    rows: list[dict[str, Any]],
    javdb_done: bool | None = None,
    metadata_done: bool | None = None,
    media_done: bool | None = None,
) -> int:
    root = Path(folder_path)
    if not rows:
        return 0

    entries = read_catalog(folder_path)
    date = datetime.now().strftime("%Y-%m-%d")
    touched = 0

    for row in rows:
        code = normalize_code(str(row.get("code") or ""))
        if not code:
            continue
        existing = entries.get(code)
        if existing:
            entry = CatalogEntry(
                code=code,
                title=existing.title,
                detail_url=existing.detail_url,
                local_file=existing.local_file,
                date=existing.date,
                metadata_done=existing.metadata_done,
                media_done=existing.media_done,
                javdb_done=existing.javdb_done,
            )
        else:
            entry = CatalogEntry(code=code, date=date)

        title = str(row.get("title") or "").strip()
        if title:
            entry.title = title
        detail = str(row.get("detail_url") or row.get("javbus_url") or "").strip()
        if detail:
            entry.detail_url = detail
        local_file = _resolve_local_file_path(row, root)
        if local_file:
            entry.local_file = local_file

        if javdb_done is not None:
            entry.javdb_done = javdb_done
        elif "javdb_done" in row:
            entry.javdb_done = bool(row.get("javdb_done"))
        if metadata_done is not None:
            entry.metadata_done = metadata_done
        elif "metadata_done" in row:
            entry.metadata_done = bool(row.get("metadata_done"))
        if media_done is not None:
            entry.media_done = media_done
        elif "media_done" in row:
            entry.media_done = bool(row.get("media_done"))

        entries[code] = entry
        touched += 1

    if touched:
        write_catalog(folder_path, entries, actress_name=actress_name)
    return touched


def mark_catalog_tasks(
    folder_path: str | Path,
    *,
    actress_name: str,
    codes: list[str],
    javdb_done: bool | None = None,
    metadata_done: bool | None = None,
    media_done: bool | None = None,
) -> int:
    rows = [{"code": code} for code in codes if normalize_code(code)]
    return upsert_catalog_rows(
        folder_path,
        actress_name=actress_name,
        rows=rows,
        javdb_done=javdb_done,
        metadata_done=metadata_done,
        media_done=media_done,
    )


def _entry_needs_task(entry: CatalogEntry | None, task: str) -> bool:
    if entry is None:
        return True
    if task == TASK_JAVDB:
        return not entry.javdb_done
    if task == TASK_METADATA:
        return not entry.metadata_done
    if task == TASK_MEDIA:
        return not entry.media_done
    return True


def filter_codes_for_task(
    folder_path: str | Path,
    codes: list[dict[str, Any]],
    task: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    catalog = read_catalog(folder_path)
    pending: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in codes:
        code = normalize_code(str(item.get("code") or ""))
        if not code:
            continue
        entry = catalog.get(code)
        if _entry_needs_task(entry, task):
            pending.append(item)
        else:
            skipped.append(item)
    return pending, skipped, bool(catalog)


def filter_codes_for_metadata_work(
    folder_path: str | Path,
    codes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    catalog = read_catalog(folder_path)
    pending: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in codes:
        code = normalize_code(str(item.get("code") or ""))
        if not code:
            continue
        entry = catalog.get(code)
        if entry is None or not entry.metadata_done or not entry.media_done:
            pending.append(item)
        else:
            skipped.append(item)
    return pending, skipped, bool(catalog)


def apply_task_filter_to_folders(
    folders: list[dict[str, Any]],
    task: str,
) -> tuple[list[dict[str, Any]], int]:
    filtered: list[dict[str, Any]] = []
    skipped_total = 0
    for folder in folders:
        folder_path = str(folder.get("folder_path") or "")
        codes = folder.get("codes") or []
        if not isinstance(codes, list):
            codes = []
        pending, skipped, has_catalog = filter_codes_for_task(folder_path, codes, task)
        skipped_total += len(skipped)
        if not pending:
            continue
        updated = dict(folder)
        updated["codes"] = pending
        updated["skipped_catalog_codes"] = [str(item.get("code") or "") for item in skipped]
        updated["catalog_skip_count"] = len(skipped)
        updated["has_catalog"] = has_catalog
        updated["total_codes_in_folder"] = len(codes)
        filtered.append(updated)
    return filtered, skipped_total


def apply_metadata_work_filter_to_folders(
    folders: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    filtered: list[dict[str, Any]] = []
    skipped_total = 0
    for folder in folders:
        folder_path = str(folder.get("folder_path") or "")
        codes = folder.get("codes") or []
        if not isinstance(codes, list):
            codes = []
        pending, skipped, has_catalog = filter_codes_for_metadata_work(folder_path, codes)
        skipped_total += len(skipped)
        if not pending:
            continue
        updated = dict(folder)
        updated["codes"] = pending
        updated["skipped_catalog_codes"] = [str(item.get("code") or "") for item in skipped]
        updated["catalog_skip_count"] = len(skipped)
        updated["has_catalog"] = has_catalog
        updated["total_codes_in_folder"] = len(codes)
        filtered.append(updated)
    return filtered, skipped_total


def filter_pending_codes(
    folder_path: str | Path,
    codes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    return filter_codes_for_task(folder_path, codes, TASK_JAVDB)


def apply_catalog_filter_to_folders(folders: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    return apply_task_filter_to_folders(folders, TASK_JAVDB)


def append_catalog_entries(
    folder_path: str | Path,
    *,
    actress_name: str,
    rows: list[dict[str, Any]],
) -> int:
    ok_rows = [row for row in rows if row.get("ok")]
    return upsert_catalog_rows(
        folder_path,
        actress_name=actress_name,
        rows=ok_rows,
        javdb_done=True,
    )
