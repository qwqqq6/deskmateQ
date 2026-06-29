"""SQLite 数据库连接与 schema 管理。

提供线程安全的连接、外键约束、行工厂 (dict-like 访问) 以及
基于 user_version 的轻量迁移机制。
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from app.core.paths import paths

# schema 版本, 每次结构变更递增并在 _MIGRATIONS 增加对应步骤。
SCHEMA_VERSION = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    -- 四象限: 1 紧急重要, 2 重要不紧急, 3 紧急不重要, 4 不紧急不重要
    quadrant    INTEGER NOT NULL DEFAULT 1,
    done        INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    done_at     TEXT,
    project_id  INTEGER
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#5c9bd1',
    status      TEXT NOT NULL DEFAULT 'active',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS worklogs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT NOT NULL,
    -- 记录发生时间, 用于周报归类 (ISO8601 本地时间)
    logged_at   TEXT NOT NULL,
    tag         TEXT NOT NULL DEFAULT '',
    -- 若该日志由某条待办勾选完成自动生成, 记录来源待办 id; 取消完成时据此回删
    source_todo_id INTEGER,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reimbursements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    amount      REAL NOT NULL DEFAULT 0,
    notes       TEXT NOT NULL DEFAULT '',
    -- 状态: pending 待报销, done 已报销
    status      TEXT NOT NULL DEFAULT 'pending',
    incurred_at TEXT,
    reimbursed_at TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attachments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reimbursement_id INTEGER NOT NULL,
    -- 相对 attachments_dir 的文件名
    filename        TEXT NOT NULL,
    original_name   TEXT NOT NULL DEFAULT '',
    mime            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    FOREIGN KEY (reimbursement_id) REFERENCES reimbursements(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_todos_quadrant ON todos(quadrant, done, sort_order);
CREATE INDEX IF NOT EXISTS idx_worklogs_logged ON worklogs(logged_at);
CREATE INDEX IF NOT EXISTS idx_reimb_status ON reimbursements(status, created_at);
CREATE INDEX IF NOT EXISTS idx_attach_reimb ON attachments(reimbursement_id);
"""

# 未来迁移步骤: {目标版本: [sql, ...]}
_MIGRATIONS: dict[int, list[str]] = {
    # v2: worklogs 增加 source_todo_id, 支持四象限勾选完成自动写日志
    2: [
        "ALTER TABLE worklogs ADD COLUMN source_todo_id INTEGER",
        "CREATE INDEX IF NOT EXISTS idx_worklogs_source ON worklogs(source_todo_id)",
    ],
    # v3: 新增 projects 表; todos 增加 project_id
    3: [
        "CREATE TABLE IF NOT EXISTS projects ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL, "
        "color TEXT NOT NULL DEFAULT '#5c9bd1', "
        "status TEXT NOT NULL DEFAULT 'active', "
        "sort_order INTEGER NOT NULL DEFAULT 0, "
        "created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)",
        "ALTER TABLE todos ADD COLUMN project_id INTEGER",
        "CREATE INDEX IF NOT EXISTS idx_todos_project ON todos(project_id)",
    ],
}


class Database:
    """封装 SQLite 连接。

    使用同一连接 + 锁保证桌面单进程多 widget 访问下的线程安全;
    数据量小, 不需要连接池。
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or paths.db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._init_schema()

    @property
    def path(self) -> Path:
        return self._db_path

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.executescript(_SCHEMA)
            cur.close()
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            for target in range(version + 1, SCHEMA_VERSION + 1):
                for stmt in _MIGRATIONS.get(target, []):
                    try:
                        self._conn.execute(stmt)
                    except sqlite3.OperationalError as exc:
                        # 新库由 _SCHEMA 已含新列, 重复执行 ALTER 会报
                        # "duplicate column"; 幂等忽略即可
                        if "duplicate column" not in str(exc).lower():
                            raise
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._conn.commit()

    # --- 通用执行助手 -------------------------------------------------
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def checkpoint(self) -> None:
        """将 WAL 落盘, 便于备份得到完整数据库文件。"""
        with self._lock:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._conn.commit()


# 全局单例
db = Database()
