"""项目仓储。"""
from __future__ import annotations

from app.core.database import Database, db as default_db
from app.repositories.models import Project
from app.utils.dates import now_iso


def _row(row) -> Project:
    return Project(
        id=row["id"], name=row["name"], color=row["color"],
        status=row["status"], sort_order=row["sort_order"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class ProjectRepository:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or default_db

    def list_active(self) -> list[Project]:
        return [_row(r) for r in self._db.query(
            "SELECT * FROM projects WHERE status='active' ORDER BY sort_order ASC, id ASC"
        )]

    def list_archived(self) -> list[Project]:
        return [_row(r) for r in self._db.query(
            "SELECT * FROM projects WHERE status='archived' ORDER BY updated_at DESC"
        )]

    def get(self, project_id: int) -> Project | None:
        row = self._db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
        return _row(row) if row else None

    def add(self, name: str, color: str = "#5c9bd1") -> Project:
        ts = now_iso()
        nxt = self._db.query_one(
            "SELECT COALESCE(MAX(sort_order),0)+1 AS n FROM projects WHERE status='active'"
        )["n"]
        cur = self._db.execute(
            "INSERT INTO projects (name,color,status,sort_order,created_at,updated_at) "
            "VALUES (?,?,'active',?,?,?)",
            (name, color, nxt, ts, ts),
        )
        return self.get(cur.lastrowid)

    def update(self, project: Project) -> None:
        self._db.execute(
            "UPDATE projects SET name=?,color=?,status=?,sort_order=?,updated_at=? WHERE id=?",
            (project.name, project.color, project.status, project.sort_order, now_iso(), project.id),
        )

    def archive(self, project_id: int) -> None:
        self._db.execute(
            "UPDATE projects SET status='archived',updated_at=? WHERE id=?",
            (now_iso(), project_id),
        )

    def restore(self, project_id: int) -> None:
        nxt = self._db.query_one(
            "SELECT COALESCE(MAX(sort_order),0)+1 AS n FROM projects WHERE status='active'"
        )["n"]
        self._db.execute(
            "UPDATE projects SET status='active',sort_order=?,updated_at=? WHERE id=?",
            (nxt, now_iso(), project_id),
        )

    def delete(self, project_id: int) -> None:
        """永久删除项目，关联待办的 project_id 置 NULL。"""
        self._db.execute(
            "UPDATE todos SET project_id=NULL, updated_at=? WHERE project_id=?",
            (now_iso(), project_id),
        )
        self._db.execute("DELETE FROM projects WHERE id=?", (project_id,))

    def name_exists(self, name: str, exclude_id: int | None = None) -> bool:
        if exclude_id is None:
            row = self._db.query_one(
                "SELECT 1 FROM projects WHERE name=? AND status='active'", (name,)
            )
        else:
            row = self._db.query_one(
                "SELECT 1 FROM projects WHERE name=? AND status='active' AND id!=?",
                (name, exclude_id),
            )
        return row is not None
