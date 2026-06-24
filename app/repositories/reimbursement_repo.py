"""报销仓储: 待报销/已报销记录, 含附件 (截图/文件) 管理。

附件按报销记录分目录存放: ``attachments/{reimbursement_id}/原始文件名``,
这样"打开该项文件夹"看到的正好是这一项的全部文件。数据库 ``filename``
字段存储相对 attachments_dir 的路径 (含子目录), 兼容历史平铺文件。
删除记录时级联删除附件行, 并清理磁盘文件与该项目录。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.core.database import Database, db as default_db
from app.core.paths import paths
from app.repositories.models import Attachment, Reimbursement
from app.utils.dates import now_iso

STATUS_PENDING = "pending"
STATUS_DONE = "done"


def _row_to_reimb(row) -> Reimbursement:
    return Reimbursement(
        id=row["id"],
        title=row["title"],
        amount=row["amount"],
        notes=row["notes"],
        status=row["status"],
        incurred_at=row["incurred_at"],
        reimbursed_at=row["reimbursed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_attach(row) -> Attachment:
    return Attachment(
        id=row["id"],
        reimbursement_id=row["reimbursement_id"],
        filename=row["filename"],
        original_name=row["original_name"],
        mime=row["mime"],
        created_at=row["created_at"],
    )


class ReimbursementRepository:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or default_db

    # --- 报销记录 ----------------------------------------------------
    def list_by_status(self, status: str) -> list[Reimbursement]:
        rows = self._db.query(
            "SELECT * FROM reimbursements WHERE status = ? ORDER BY created_at DESC, id DESC",
            (status,),
        )
        items = [_row_to_reimb(r) for r in rows]
        for it in items:
            it.attachments = self.list_attachments(it.id)
        return items

    def get(self, reimb_id: int) -> Reimbursement | None:
        row = self._db.query_one("SELECT * FROM reimbursements WHERE id = ?", (reimb_id,))
        if not row:
            return None
        item = _row_to_reimb(row)
        item.attachments = self.list_attachments(item.id)
        return item

    def add(self, title: str, amount: float = 0.0, notes: str = "",
            status: str = STATUS_PENDING, incurred_at: str | None = None) -> Reimbursement:
        ts = now_iso()
        cur = self._db.execute(
            "INSERT INTO reimbursements (title, amount, notes, status, incurred_at, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, amount, notes, status, incurred_at, ts, ts),
        )
        return self.get(cur.lastrowid)

    def update(self, item: Reimbursement) -> None:
        self._db.execute(
            "UPDATE reimbursements SET title=?, amount=?, notes=?, status=?, "
            "incurred_at=?, reimbursed_at=?, updated_at=? WHERE id=?",
            (
                item.title,
                item.amount,
                item.notes,
                item.status,
                item.incurred_at,
                item.reimbursed_at,
                now_iso(),
                item.id,
            ),
        )

    def set_status(self, reimb_id: int, status: str) -> None:
        reimbursed = now_iso() if status == STATUS_DONE else None
        self._db.execute(
            "UPDATE reimbursements SET status=?, reimbursed_at=?, updated_at=? WHERE id=?",
            (status, reimbursed, now_iso(), reimb_id),
        )

    def delete(self, reimb_id: int) -> None:
        # 先清理磁盘附件 (含整个项目目录), 再删行 (外键级联删除附件行)
        for att in self.list_attachments(reimb_id):
            self._remove_file(att.filename)
        self._remove_item_dir(reimb_id)
        self._db.execute("DELETE FROM reimbursements WHERE id = ?", (reimb_id,))

    def total_amount(self, status: str) -> float:
        row = self._db.query_one(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM reimbursements WHERE status = ?",
            (status,),
        )
        return float(row["s"]) if row else 0.0

    # --- 附件 --------------------------------------------------------
    def list_attachments(self, reimb_id: int) -> list[Attachment]:
        rows = self._db.query(
            "SELECT * FROM attachments WHERE reimbursement_id = ? ORDER BY id ASC",
            (reimb_id,),
        )
        return [_row_to_attach(r) for r in rows]

    def add_attachment(self, reimb_id: int, source_path: str) -> Attachment:
        """复制外部文件到该报销项的附件目录并登记。返回附件记录。

        文件落到 ``attachments/{reimb_id}/原始文件名``, 保留原名以便
        用户在文件夹中直接辨认; 同名时自动追加序号避免覆盖。
        """
        src = Path(source_path)
        item_dir = self.item_dir(reimb_id)
        item_dir.mkdir(parents=True, exist_ok=True)
        dest = self._unique_dest(item_dir, src.name)
        shutil.copy2(src, dest)
        # filename 存相对 attachments_dir 的 posix 路径
        rel = dest.relative_to(paths.attachments_dir).as_posix()
        mime = _guess_mime(dest.suffix.lower())
        ts = now_iso()
        cur = self._db.execute(
            "INSERT INTO attachments (reimbursement_id, filename, original_name, mime, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (reimb_id, rel, src.name, mime, ts),
        )
        row = self._db.query_one("SELECT * FROM attachments WHERE id = ?", (cur.lastrowid,))
        return _row_to_attach(row)

    def delete_attachment(self, attachment_id: int) -> None:
        row = self._db.query_one(
            "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
        )
        if row:
            self._remove_file(row["filename"])
            self._db.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))

    def attachment_path(self, attachment: Attachment) -> Path:
        return paths.attachments_dir / attachment.filename

    def item_dir(self, reimb_id: int) -> Path:
        """返回某报销项的附件目录 (可能尚未创建)。"""
        return paths.attachments_dir / str(reimb_id)

    def ensure_item_dir(self, reimb_id: int) -> Path:
        d = self.item_dir(reimb_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _unique_dest(folder: Path, name: str) -> Path:
        """在 folder 下为 name 生成不冲突的目标路径。"""
        candidate = folder / name
        if not candidate.exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        i = 1
        while True:
            candidate = folder / f"{stem} ({i}){suffix}"
            if not candidate.exists():
                return candidate
            i += 1

    @staticmethod
    def _remove_file(filename: str) -> None:
        try:
            (paths.attachments_dir / filename).unlink(missing_ok=True)
        except OSError:
            pass

    def _remove_item_dir(self, reimb_id: int) -> None:
        try:
            shutil.rmtree(self.item_dir(reimb_id), ignore_errors=True)
        except OSError:
            pass


def _guess_mime(ext: str) -> str:
    images = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
    if ext in images:
        return f"image/{ext.lstrip('.')}"
    if ext == ".pdf":
        return "application/pdf"
    return "application/octet-stream"
