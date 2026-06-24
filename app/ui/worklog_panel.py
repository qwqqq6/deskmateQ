"""工作日志面板。

顶部输入框随手记录 (自动记录时间), 下方时间线展示历史记录,
一键生成并复制当周周报。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.repositories.models import WorkLog
from app.repositories.worklog_repo import WorkLogRepository
from app.services.report_service import WeeklyReportService
from app.ui.theme import COLORS
from app.utils.dates import fmt_human

class LogCard(QFrame):
    """单条日志卡片: 时间 + 标签 + 内容 + 操作。

    编辑采用卡片内就地编辑 (inline): 点击 ✎ 把内容区替换为多行输入框,
    避免在无边框置顶主窗口下弹窗被遮挡的问题。
    """

    changed = Signal()

    def __init__(self, log: WorkLog, repo: WorkLogRepository) -> None:
        super().__init__()
        self.setObjectName("Card")
        self._log = log
        self._repo = repo
        self._editing = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        self._lay = lay

        top = QHBoxLayout()
        time_lbl = QLabel(fmt_human(log.logged_at))
        time_lbl.setObjectName("Faint")
        top.addWidget(time_lbl)
        if log.tag:
            tag = QLabel(log.tag)
            tag.setStyleSheet(
                f"color: {COLORS['accent']}; font-size: 12px; font-weight: 600;"
            )
            top.addWidget(tag)
        top.addStretch(1)

        self._content = QLabel(log.content)
        self._content.setWordWrap(True)
        lay.addWidget(self._content)

        # 操作行: 明确的文字按钮, 避免符号图标在部分字体下不显示/难找
        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addStretch(1)
        self._edit_btn = QPushButton("编辑")
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.clicked.connect(self._enter_edit)
        actions.addWidget(self._edit_btn)
        del_btn = QPushButton("删除")
        del_btn.setObjectName("Ghost")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(self._on_delete)
        actions.addWidget(del_btn)
        lay.addLayout(actions)

        # 内联编辑控件 (惰性显示)
        self._editor: QPlainTextEdit | None = None
        self._edit_actions: QWidget | None = None

    def _enter_edit(self) -> None:
        if self._editing:
            return
        self._editing = True
        self._content.hide()
        self._edit_btn.setEnabled(False)

        self._editor = QPlainTextEdit(self._log.content)
        self._editor.setMinimumHeight(64)
        self._lay.addWidget(self._editor)
        self._editor.setFocus()

        actions = QWidget()
        arow = QHBoxLayout(actions)
        arow.setContentsMargins(0, 0, 0, 0)
        arow.setSpacing(6)
        arow.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self._cancel_edit)
        arow.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("Primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save_edit)
        arow.addWidget(save)
        self._edit_actions = actions
        self._lay.addWidget(actions)

    def _save_edit(self) -> None:
        if not self._editor:
            return
        text = self._editor.toPlainText().strip()
        if text:
            self._log.content = text
            self._repo.update(self._log)
            self._content.setText(text)
            self.changed.emit()
        self._exit_edit()

    def _cancel_edit(self) -> None:
        self._exit_edit()

    def _exit_edit(self) -> None:
        if self._editor:
            self._editor.deleteLater()
            self._editor = None
        if self._edit_actions:
            self._edit_actions.deleteLater()
            self._edit_actions = None
        self._content.show()
        self._edit_btn.setEnabled(True)
        self._editing = False

    def _on_delete(self) -> None:
        self._repo.delete(self._log.id)
        self.changed.emit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        # 双击卡片任意处也可进入编辑
        self._enter_edit()


class WorkLogPanel(QWidget):
    data_changed = Signal()

    def __init__(self, repo: WorkLogRepository | None = None) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._repo = repo or WorkLogRepository()
        self._report = WeeklyReportService(self._repo)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # 标题
        head = QLabel("工作日志")
        head.setObjectName("PanelTitle")
        root.addWidget(head)

        # 输入区
        input_card = QFrame()
        input_card.setObjectName("InputCard")
        ic = QVBoxLayout(input_card)
        ic.setContentsMargins(12, 10, 12, 12)
        ic.setSpacing(8)

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("记录刚完成的工作… (Ctrl+Enter 保存)")
        self._editor.setFixedHeight(60)
        ic.addWidget(self._editor)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._tag = QLineEdit()
        self._tag.setPlaceholderText("标签 (可选)")
        self._tag.setFixedWidth(110)
        row.addWidget(self._tag)
        row.addStretch(1)
        add_btn = QPushButton("记录")
        add_btn.setObjectName("Primary")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        row.addWidget(add_btn)
        ic.addLayout(row)
        root.addWidget(input_card)

        # 周报操作栏
        bar = QHBoxLayout()
        title = QLabel("工作时间线")
        title.setObjectName("SectionTitle")
        bar.addWidget(title)
        bar.addStretch(1)
        report_btn = QPushButton("复制本周周报")
        report_btn.setCursor(Qt.PointingHandCursor)
        report_btn.clicked.connect(self._on_copy_report)
        bar.addWidget(report_btn)
        root.addLayout(bar)

        # 时间线
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
        # Ctrl+Enter 提交
        self._editor.installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802
        from PySide6.QtCore import QEvent
        if obj is self._editor and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and (
                event.modifiers() & Qt.ControlModifier
            ):
                self._on_add()
                return True
        return super().eventFilter(obj, event)

    def _on_add(self) -> None:
        content = self._editor.toPlainText().strip()
        if not content:
            return
        self._repo.add(content, tag=self._tag.text().strip())
        self._editor.clear()
        self._tag.clear()
        self.reload()
        self.data_changed.emit()

    def _on_copy_report(self) -> None:
        text = self._report.generate()
        QGuiApplication.clipboard().setText(text)
        self._notify("本周周报已复制到剪贴板")

    def _notify(self, msg: str) -> None:
        # 由主窗口连接显示 toast
        self.toast_requested.emit(msg)

    toast_requested = Signal(str)

    def reload(self) -> None:
        while self._list.count() > 1:
            item = self._list.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        logs = self._repo.recent()
        if not logs:
            empty = QLabel("还没有工作记录, 在上方随手记一条吧。")
            empty.setObjectName("Faint")
            empty.setAlignment(Qt.AlignCenter)
            self._list.insertWidget(0, empty)
            return
        for log in logs:
            card = LogCard(log, self._repo)
            card.changed.connect(self._on_card_changed)
            self._list.insertWidget(self._list.count() - 1, card)

    def _on_card_changed(self) -> None:
        self.reload()
        self.data_changed.emit()
