"""领域模型: 轻量 dataclass, 表达数据库行。

放在 repositories 层, 供 UI 直接使用, 避免暴露 sqlite3.Row。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Project:
    id: int | None = None
    name: str = ""
    color: str = "#5c9bd1"
    status: str = "active"
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Todo:
    id: int | None = None
    title: str = ""
    notes: str = ""
    quadrant: int = 1  # 1..4 四象限
    done: bool = False
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""
    done_at: str | None = None
    project_id: int | None = None


@dataclass
class WorkLog:
    id: int | None = None
    content: str = ""
    logged_at: str = ""
    tag: str = ""
    # 若由某条待办勾选完成自动生成, 记录来源待办 id (取消完成时据此回删)
    source_todo_id: int | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Attachment:
    id: int | None = None
    reimbursement_id: int | None = None
    filename: str = ""
    original_name: str = ""
    mime: str = ""
    created_at: str = ""


@dataclass
class Reimbursement:
    id: int | None = None
    title: str = ""
    amount: float = 0.0
    notes: str = ""
    status: str = "pending"  # pending | done
    incurred_at: str | None = None
    reimbursed_at: str | None = None
    created_at: str = ""
    updated_at: str = ""
    attachments: list[Attachment] = field(default_factory=list)
