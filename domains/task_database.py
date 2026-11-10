"""Small SQLite task database used as the second agent domain."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class TaskDatabase:
    """Create, read, update, and delete simple tasks."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal',
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )

    def add(self, title: str, priority: str = "normal") -> dict[str, object]:
        title = title.strip()
        priority = priority.lower()
        if not title:
            raise ValueError("A task title cannot be empty.")
        if priority not in {"low", "normal", "high"}:
            raise ValueError("Priority must be low, normal, or high.")

        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tasks (title, priority, status, created_at)
                VALUES (?, ?, 'open', ?)
                """,
                (title, priority, created_at),
            )
            task_id = int(cursor.lastrowid)
        return {
            "id": task_id,
            "title": title,
            "priority": priority,
            "status": "open",
            "created_at": created_at,
        }

    def list_tasks(self, status: str = "all") -> list[dict[str, object]]:
        status = status.lower()
        if status not in {"all", "open", "done"}:
            raise ValueError("Status must be all, open, or done.")

        query = "SELECT * FROM tasks"
        parameters: tuple[str, ...] = ()
        if status != "all":
            query += " WHERE status = ?"
            parameters = (status,)
        query += " ORDER BY id"

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def complete(self, task_id: int) -> dict[str, object]:
        completed_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET status = 'done', completed_at = ?
                WHERE id = ? AND status = 'open'
                """,
                (completed_at, task_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(
                    f"Open task {task_id} was not found or is already complete."
                )
        return {
            "id": task_id,
            "status": "done",
            "completed_at": completed_at,
        }

    def delete(self, task_id: int) -> dict[str, object]:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM tasks WHERE id = ?",
                (task_id,),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Task {task_id} was not found.")
        return {"id": task_id, "deleted": True}
