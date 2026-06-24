"""工作日志仓储: 随手记录, 自动时间, 支持按周查询 (周报)。"""
from __future__ import annotations

from datetime import datetime

from app.core.database import Database, db as default_db
from app.repositories.models import WorkLog
from app.utils.dates import now_iso, week_bounds


def _row_to_log(row) -> WorkLog:
    return WorkLog(
        id=row["id"],
        content=row["content"],
        logged_at=row["logged_at"],
        tag=row["tag"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class WorkLogRepository:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or default_db

    def add(self, content: str, tag: str = "", logged_at: str | None = None) -> WorkLog:
        ts = now_iso()
        logged = logged_at or ts
        cur = self._db.execute(
            "INSERT INTO worklogs (content, logged_at, tag, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (content, logged, tag, ts, ts),
        )
        return self.get(cur.lastrowid)

    def get(self, log_id: int) -> WorkLog | None:
        row = self._db.query_one("SELECT * FROM worklogs WHERE id = ?", (log_id,))
        return _row_to_log(row) if row else None

    def recent(self, limit: int = 200) -> list[WorkLog]:
        rows = self._db.query(
            "SELECT * FROM worklogs ORDER BY logged_at DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [_row_to_log(r) for r in rows]

    def in_week(self, ref: datetime | None = None) -> list[WorkLog]:
        start, end = week_bounds(ref)
        rows = self._db.query(
            "SELECT * FROM worklogs WHERE logged_at >= ? AND logged_at < ? "
            "ORDER BY logged_at ASC, id ASC",
            (start.isoformat(), end.isoformat()),
        )
        return [_row_to_log(r) for r in rows]

    def update(self, log: WorkLog) -> None:
        self._db.execute(
            "UPDATE worklogs SET content=?, logged_at=?, tag=?, updated_at=? WHERE id=?",
            (log.content, log.logged_at, log.tag, now_iso(), log.id),
        )

    def delete(self, log_id: int) -> None:
        self._db.execute("DELETE FROM worklogs WHERE id = ?", (log_id,))
