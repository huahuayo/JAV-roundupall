"""User-defined external tools (name + executable path)."""

from __future__ import annotations

from typing import Any

from src.sticker_store import get_connection


def init_custom_tools_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS custom_tools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT '',
                executable_path TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0
            );
            """
        )


def list_custom_tools() -> list[dict[str, Any]]:
    init_custom_tools_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, executable_path, sort_order
            FROM custom_tools
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def save_custom_tool(*, tool_id: int | None, name: str, executable_path: str, sort_order: int = 0) -> int:
    init_custom_tools_db()
    with get_connection() as conn:
        if tool_id:
            conn.execute(
                """
                UPDATE custom_tools
                SET name = ?, executable_path = ?, sort_order = ?
                WHERE id = ?
                """,
                (name, executable_path, sort_order, tool_id),
            )
            conn.commit()
            return int(tool_id)
        cur = conn.execute(
            """
            INSERT INTO custom_tools (name, executable_path, sort_order)
            VALUES (?, ?, ?)
            """,
            (name, executable_path, sort_order),
        )
        conn.commit()
        return int(cur.lastrowid)


def delete_custom_tool(tool_id: int) -> None:
    init_custom_tools_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM custom_tools WHERE id = ?", (tool_id,))
        conn.commit()
