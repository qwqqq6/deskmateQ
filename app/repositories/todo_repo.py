"""待办仓储: 四象限 todolist 的数据访问。"""
from __future__ import annotations

from app.core.database import Database, db as default_db
from app.repositories.models import Todo
from app.utils.dates import now_iso

# 哨兵: 不过滤项目 (区别于 None=无项目)
_FILTER_ALL = object()


def _row_to_todo(row) -> Todo:
    return Todo(
        id=row["id"],
        title=row["title"],
        notes=row["notes"],
        quadrant=row["quadrant"],
        done=bool(row["done"]),
        sort_order=row["sort_order"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        done_at=row["done_at"],
        project_id=row["project_id"],
    )


class TodoRepository:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or default_db

    def list_by_quadrant(self, quadrant: int, project_filter=_FILTER_ALL) -> list[Todo]:
        base = "SELECT * FROM todos WHERE quadrant=?"
        order = " ORDER BY done ASC, sort_order ASC, id ASC"
        if project_filter is _FILTER_ALL:
            rows = self._db.query(base + order, (quadrant,))
        elif project_filter is None:
            rows = self._db.query(base + " AND project_id IS NULL" + order, (quadrant,))
        else:
            rows = self._db.query(base + " AND project_id=?" + order, (quadrant, project_filter))
        return [_row_to_todo(r) for r in rows]

    def all(self) -> list[Todo]:
        rows = self._db.query("SELECT * FROM todos ORDER BY quadrant, sort_order")
        return [_row_to_todo(r) for r in rows]

    def add(self, title: str, quadrant: int = 1, notes: str = "",
            project_id: int | None = None) -> Todo:
        ts = now_iso()
        nxt = self._db.query_one(
            "SELECT COALESCE(MAX(sort_order),0)+1 AS n FROM todos WHERE quadrant=?",
            (quadrant,),
        )["n"]
        cur = self._db.execute(
            "INSERT INTO todos (title,notes,quadrant,done,sort_order,created_at,updated_at,project_id) "
            "VALUES (?,?,?,0,?,?,?,?)",
            (title, notes, quadrant, nxt, ts, ts, project_id),
        )
        return self.get(cur.lastrowid)

    def get(self, todo_id: int) -> Todo | None:
        row = self._db.query_one("SELECT * FROM todos WHERE id=?", (todo_id,))
        return _row_to_todo(row) if row else None

    def update(self, todo: Todo) -> None:
        self._db.execute(
            "UPDATE todos SET title=?,notes=?,quadrant=?,done=?,sort_order=?,"
            "updated_at=?,done_at=?,project_id=? WHERE id=?",
            (todo.title, todo.notes, todo.quadrant, 1 if todo.done else 0,
             todo.sort_order, now_iso(), todo.done_at, todo.project_id, todo.id),
        )

    def set_done(self, todo_id: int, done: bool) -> None:
        self._db.execute(
            "UPDATE todos SET done=?,done_at=?,updated_at=? WHERE id=?",
            (1 if done else 0, now_iso() if done else None, now_iso(), todo_id),
        )

    def move_quadrant(self, todo_id: int, quadrant: int) -> None:
        nxt = self._db.query_one(
            "SELECT COALESCE(MAX(sort_order),0)+1 AS n FROM todos WHERE quadrant=?",
            (quadrant,),
        )["n"]
        self._db.execute(
            "UPDATE todos SET quadrant=?,sort_order=?,updated_at=? WHERE id=?",
            (quadrant, nxt, now_iso(), todo_id),
        )

    def delete(self, todo_id: int) -> None:
        self._db.execute("DELETE FROM todos WHERE id=?", (todo_id,))

    def clear_done(self, quadrant: int | None = None) -> int:
        if quadrant is None:
            cur = self._db.execute("DELETE FROM todos WHERE done=1")
        else:
            cur = self._db.execute(
                "DELETE FROM todos WHERE done=1 AND quadrant=?", (quadrant,)
            )
        return cur.rowcount

    def count_pending_by_project(self, project_id: int) -> int:
        row = self._db.query_one(
            "SELECT COUNT(*) AS n FROM todos WHERE project_id=? AND done=0", (project_id,)
        )
        return row["n"] if row else 0
