"""报销记录新增/编辑对话框, 含附件管理 (拖入文件 + 打开项目文件夹)。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from app.repositories.models import Reimbursement
from app.repositories.reimbursement_repo import ReimbursementRepository
from app.ui.components.drop_zone import DropZone
from app.utils.system import open_path


class ReimbursementDialog(QDialog):
    """新增或编辑一条报销记录。

    若传入 existing, 为编辑模式; 否则为新增。附件改动即时落库
    (因为附件需要 reimbursement_id, 新增模式下先创建记录草稿)。
    支持从资源管理器拖入文件, 以及一键打开该报销项的附件文件夹。
    """

    def __init__(self, repo: ReimbursementRepository,
                 existing: Reimbursement | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._editing = existing is not None
        self.setWindowTitle("编辑报销" if self._editing else "新增报销")
        self.setMinimumWidth(420)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        # 新增模式: 先建一条 pending 草稿, 以便挂附件; 取消时回滚删除
        if existing is None:
            self._item = repo.add("", 0.0, "")
            self._created_draft = True
        else:
            self._item = repo.get(existing.id)
            self._created_draft = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        lay.addWidget(self._field_label("标题"))
        self._title = QLineEdit(self._item.title)
        self._title.setPlaceholderText("例如: 出差住宿费")
        lay.addWidget(self._title)

        row = QHBoxLayout()
        row.setSpacing(12)
        amount_col = QVBoxLayout()
        amount_col.setSpacing(6)
        amount_col.addWidget(self._field_label("金额 (元)"))
        self._amount = QDoubleSpinBox()
        self._amount.setMaximum(1_000_000)
        self._amount.setDecimals(2)
        self._amount.setValue(float(self._item.amount))
        amount_col.addWidget(self._amount)
        row.addLayout(amount_col, 1)
        lay.addLayout(row)

        lay.addWidget(self._field_label("备注 / 内容"))
        self._notes = QPlainTextEdit(self._item.notes)
        self._notes.setFixedHeight(64)
        lay.addWidget(self._notes)

        # 附件区: 标题 + 打开文件夹
        att_bar = QHBoxLayout()
        att_bar.addWidget(self._field_label("附件 (截图 / 文件)"))
        att_bar.addStretch(1)
        open_dir = QPushButton("打开文件夹")
        open_dir.setObjectName("Ghost")
        open_dir.setCursor(Qt.PointingHandCursor)
        open_dir.setToolTip("打开该报销项的附件文件夹, 里面正好是这一项的全部文件")
        open_dir.clicked.connect(self._on_open_folder)
        att_bar.addWidget(open_dir)
        lay.addLayout(att_bar)

        # 拖放区
        self._drop = DropZone("拖入文件 / 截图到此处", "或点击选择")
        self._drop.files_dropped.connect(self._add_files)
        self._drop.clicked.connect(self._on_browse)
        lay.addWidget(self._drop)

        self._att_list = QListWidget()
        self._att_list.setFixedHeight(110)
        self._att_list.itemDoubleClicked.connect(self._on_open_attachment)
        lay.addWidget(self._att_list)

        del_att = QPushButton("删除选中附件")
        del_att.setObjectName("Ghost")
        del_att.setCursor(Qt.PointingHandCursor)
        del_att.clicked.connect(self._on_delete_attachment)
        lay.addWidget(del_att, alignment=Qt.AlignRight)

        # 底部按钮
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("Primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._on_save)
        btns.addWidget(save)
        lay.addLayout(btns)

        self._reload_attachments()

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("Dim")
        return lbl

    def _reload_attachments(self) -> None:
        self._att_list.clear()
        for att in self._repo.list_attachments(self._item.id):
            item = QListWidgetItem(f"📎  {att.original_name or att.filename}")
            item.setData(Qt.UserRole, att.id)
            item.setToolTip("双击打开")
            self._att_list.addItem(item)

    def _on_browse(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择附件", "",
            "支持的文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.pdf *.docx *.xlsx);;所有文件 (*.*)",
        )
        self._add_files(files)

    def _add_files(self, files: list[str]) -> None:
        added = 0
        for f in files:
            try:
                self._repo.add_attachment(self._item.id, f)
                added += 1
            except OSError:
                pass
        if added:
            self._reload_attachments()

    def _on_delete_attachment(self) -> None:
        item = self._att_list.currentItem()
        if not item:
            return
        self._repo.delete_attachment(item.data(Qt.UserRole))
        self._reload_attachments()

    def _on_open_attachment(self, item: QListWidgetItem) -> None:
        att_id = item.data(Qt.UserRole)
        for att in self._repo.list_attachments(self._item.id):
            if att.id == att_id:
                path = self._repo.attachment_path(att)
                if path.exists():
                    open_path(path)
                break

    def _on_open_folder(self) -> None:
        folder = self._repo.ensure_item_dir(self._item.id)
        open_path(folder)

    def _on_save(self) -> None:
        if not self._title.text().strip():
            self._title.setFocus()
            QMessageBox.information(self, "提示", "请先填写标题。")
            return
        self._item.title = self._title.text().strip()
        self._item.amount = self._amount.value()
        self._item.notes = self._notes.toPlainText().strip()
        self._repo.update(self._item)
        self._created_draft = False  # 已正式保存, 不再回滚
        self.accept()

    def reject(self) -> None:  # noqa: N802
        # 取消新增时, 删除草稿及其附件
        if self._created_draft:
            self._repo.delete(self._item.id)
        super().reject()
