"""报销记录面板。

分"待报销 / 已报销"两个分组展示, 每条记录含标题、金额、备注、
附件 (截图/文件) 缩略入口。支持新增、编辑、状态切换、删除,
以及一键打开该报销项的附件文件夹。新增/编辑使用弹出对话框。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.repositories.models import Reimbursement
from app.repositories.reimbursement_repo import (
    ReimbursementRepository, STATUS_DONE, STATUS_PENDING,
)
from app.ui.components.reimbursement_dialog import ReimbursementDialog
from app.ui.theme import COLORS
from app.utils.system import open_path

class ReimbursementCard(QFrame):
    """单条报销卡片。"""

    changed = Signal()

    def __init__(self, item: Reimbursement, repo: ReimbursementRepository,
                 parent_panel: "ReimbursementPanel") -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setAcceptDrops(True)
        self._item = item
        self._repo = repo
        self._panel = parent_panel

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        top = QHBoxLayout()
        title = QLabel(item.title or "(未命名)")
        title.setObjectName("SectionTitle")
        title.setWordWrap(True)
        top.addWidget(title, 1)
        amount = QLabel(f"¥ {item.amount:.2f}")
        amount.setStyleSheet(
            f"color: {COLORS['accent']}; font-weight: 700; font-size: 15px;"
        )
        top.addWidget(amount)
        lay.addLayout(top)

        if item.notes:
            notes = QLabel(item.notes)
            notes.setObjectName("Dim")
            notes.setWordWrap(True)
            lay.addWidget(notes)

        meta = QHBoxLayout()
        info_bits = []
        if item.attachments:
            info_bits.append(f"📎 {len(item.attachments)} 个附件")
        if item.status == STATUS_DONE and item.reimbursed_at:
            from app.utils.dates import fmt_human
            info_bits.append(f"已报销 {fmt_human(item.reimbursed_at, with_time=False)}")
        if info_bits:
            meta_lbl = QLabel("  ·  ".join(info_bits))
            meta_lbl.setObjectName("Faint")
            meta.addWidget(meta_lbl)
        meta.addStretch(1)
        lay.addLayout(meta)

        # 操作行
        actions = QHBoxLayout()
        actions.setSpacing(6)

        folder = QPushButton("📁 文件夹")
        folder.setObjectName("Ghost")
        folder.setCursor(Qt.PointingHandCursor)
        folder.setToolTip("打开该项的附件文件夹")
        folder.clicked.connect(self._on_open_folder)
        actions.addWidget(folder)

        actions.addStretch(1)

        toggle = QPushButton(
            "标记待报销" if item.status == STATUS_DONE else "标记已报销"
        )
        toggle.setObjectName("Ghost" if item.status == STATUS_DONE else "Primary")
        toggle.setCursor(Qt.PointingHandCursor)
        toggle.clicked.connect(self._on_toggle)
        actions.addWidget(toggle)

        edit = QPushButton("编辑")
        edit.setCursor(Qt.PointingHandCursor)
        edit.clicked.connect(self._on_edit)
        actions.addWidget(edit)

        delete = QPushButton("删除")
        delete.setObjectName("Ghost")
        delete.setCursor(Qt.PointingHandCursor)
        delete.clicked.connect(self._on_delete)
        actions.addWidget(delete)
        lay.addLayout(actions)

    # --- 拖放: 直接把文件拖到卡片即追加为该项附件 ----------------------
    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        added = 0
        for url in event.mimeData().urls():
            if url.isLocalFile():
                try:
                    self._repo.add_attachment(self._item.id, url.toLocalFile())
                    added += 1
                except OSError:
                    pass
        if added:
            event.acceptProposedAction()
            self.changed.emit()

    def _on_open_folder(self) -> None:
        folder = self._repo.ensure_item_dir(self._item.id)
        open_path(folder)

    def _on_toggle(self) -> None:
        new_status = (
            STATUS_PENDING if self._item.status == STATUS_DONE else STATUS_DONE
        )
        self._repo.set_status(self._item.id, new_status)
        self.changed.emit()

    def _on_edit(self) -> None:
        dlg = ReimbursementDialog(self._repo, existing=self._item, parent=self._panel)
        if dlg.exec():
            self.changed.emit()

    def _on_delete(self) -> None:
        resp = QMessageBox.question(
            self, "删除报销", f"确认删除“{self._item.title or '该记录'}”及其附件?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            self._repo.delete(self._item.id)
            self.changed.emit()


class ReimbursementPanel(QWidget):
    data_changed = Signal()

    def __init__(self, repo: ReimbursementRepository | None = None) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._repo = repo or ReimbursementRepository()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # 顶部: 标题 + 新增
        head = QHBoxLayout()
        title = QLabel("报销记录")
        title.setObjectName("PanelTitle")
        head.addWidget(title)
        head.addStretch(1)
        add_btn = QPushButton("+ 新增报销")
        add_btn.setObjectName("Primary")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        head.addWidget(add_btn)
        root.addLayout(head)

        # 汇总条
        self._summary = QLabel()
        self._summary.setObjectName("Dim")
        root.addWidget(self._summary)

        # 滚动内容
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._host = QWidget()
        self._list = QVBoxLayout(self._host)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(6)
        self._list.addStretch(1)
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll, 1)

        self.reload()

    def _on_add(self) -> None:
        dlg = ReimbursementDialog(self._repo, parent=self)
        if dlg.exec():
            self.reload()
            self.data_changed.emit()

    def _section_header(self, text: str, color: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {color}; font-weight: 600; font-size: 13px; padding-top: 4px;"
        )
        return lbl

    def reload(self) -> None:
        while self._list.count() > 1:
            item = self._list.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        pending = self._repo.list_by_status(STATUS_PENDING)
        done = self._repo.list_by_status(STATUS_DONE)
        total_pending = self._repo.total_amount(STATUS_PENDING)
        total_done = self._repo.total_amount(STATUS_DONE)
        self._summary.setText(
            f"待报销 ¥{total_pending:.2f}  ·  已报销 ¥{total_done:.2f}"
        )

        pos = 0

        def insert(widget):
            nonlocal pos
            self._list.insertWidget(pos, widget)
            pos += 1

        insert(self._section_header(f"待报销 ({len(pending)})", COLORS["warning"]))
        if pending:
            for it in pending:
                insert(self._make_card(it))
        else:
            insert(self._empty_hint("暂无待报销记录"))

        insert(self._section_header(f"已报销 ({len(done)})", COLORS["success"]))
        if done:
            for it in done:
                insert(self._make_card(it))
        else:
            insert(self._empty_hint("暂无已报销记录"))

    def _make_card(self, item: Reimbursement) -> ReimbursementCard:
        card = ReimbursementCard(item, self._repo, self)
        card.changed.connect(self._on_card_changed)
        return card

    def _empty_hint(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("Faint")
        return lbl

    def _on_card_changed(self) -> None:
        self.reload()
        self.data_changed.emit()
