"""四象限 TodoList 面板。

按艾森豪威尔矩阵把待办分为四个象限, 每个象限是一张卡片,
内含可勾选、可编辑、可删除的条目, 支持快速添加。
条目可在四个象限之间拖拽移动。
"""
from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.repositories.models import Todo
from app.repositories.todo_repo import TodoRepository
from app.ui.theme import COLORS

QUADRANTS = [
    (1, "紧急 · 重要", "q1"),
    (2, "重要 · 不紧急", "q2"),
    (3, "紧急 · 不重要", "q3"),
    (4, "不紧急 · 不重要", "q4"),
]

# 拖拽待办时携带的 MIME 类型, 内容为 todo id 的字符串
TODO_MIME = "application/x-deskmateq-todo-id"

class TodoItemRow(QWidget):
    """单条待办: 复选框 + 标题 + 删除按钮。

    勾选完成时自动写一条工作日志 (来源标记为该待办), 取消完成时回删该日志。
    """

    changed = Signal()

    def __init__(self, todo: Todo, repo: TodoRepository,
                 worklog_repo: "WorkLogRepository | None" = None) -> None:
        super().__init__()
        self._todo = todo
        self._repo = repo
        if worklog_repo is None:
            from app.repositories.worklog_repo import WorkLogRepository
            worklog_repo = WorkLogRepository()
        self._worklog = worklog_repo
        self._editing = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(6)
        self._lay = lay

        self._check = QCheckBox()
        self._check.setChecked(todo.done)
        self._check.toggled.connect(self._on_toggle)
        lay.addWidget(self._check)

        self._label = QLabel(todo.title)
        self._label.setWordWrap(True)
        self._apply_label_style()
        lay.addWidget(self._label, 1)

        self._editor: QLineEdit | None = None

        self._del = QPushButton("删除")
        self._del.setObjectName("Ghost")
        self._del.setCursor(Qt.PointingHandCursor)
        self._del.clicked.connect(self._on_delete)
        self._del.setToolTip("删除该待办")
        lay.addWidget(self._del)

        # 拖拽起点 (用于区分点击与拖动)
        self._drag_start = None

    # --- 拖拽: 把待办拖到其它象限 ------------------------------------
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and not self._editing:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if (self._drag_start is None or self._editing
                or not (event.buttons() & Qt.LeftButton)):
            return
        if (event.position().toPoint() - self._drag_start).manhattanLength() < 12:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(TODO_MIME, str(self._todo.id).encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def _apply_label_style(self) -> None:
        if self._todo.done:
            self._label.setStyleSheet(
                f"color: {COLORS['text_faint']}; text-decoration: line-through;"
            )
        else:
            self._label.setStyleSheet(f"color: {COLORS['text']};")

    def _on_toggle(self, checked: bool) -> None:
        self._todo.done = checked
        self._repo.set_done(self._todo.id, checked)
        # 勾选完成 -> 自动写日志; 取消完成 -> 回删自动日志
        if checked:
            if self._worklog.get_by_source_todo(self._todo.id) is None:
                self._worklog.add(
                    self._todo.title, tag="待办完成",
                    source_todo_id=self._todo.id,
                )
        else:
            self._worklog.delete_by_source_todo(self._todo.id)
        self._apply_label_style()
        self.changed.emit()

    def _on_delete(self) -> None:
        # 删除待办时连带清理它自动生成的日志
        self._worklog.delete_by_source_todo(self._todo.id)
        self._repo.delete(self._todo.id)
        self.changed.emit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._enter_edit()

    def _enter_edit(self) -> None:
        if self._editing:
            return
        self._editing = True
        self._label.hide()
        self._editor = QLineEdit(self._todo.title)
        # 在 label 的位置插入输入框 (索引 1: check 之后)
        self._lay.insertWidget(1, self._editor, 1)
        self._editor.setFocus()
        self._editor.selectAll()
        self._editor.returnPressed.connect(self._save_edit)
        self._editor.editingFinished.connect(self._save_edit)

    def _save_edit(self) -> None:
        if not self._editing or not self._editor:
            return
        text = self._editor.text().strip()
        self._editing = False  # 防止 editingFinished 重入
        if text and text != self._todo.title:
            self._todo.title = text
            self._repo.update(self._todo)
            self._label.setText(text)
            changed = True
        else:
            changed = False
        self._editor.deleteLater()
        self._editor = None
        self._label.show()
        if changed:
            self.changed.emit()


class QuadrantCard(QFrame):
    """单个象限卡片。"""

    changed = Signal()
    todo_moved = Signal(int, int)  # (todo_id, target_quadrant)

    def __init__(self, quadrant: int, title: str, color_key: str,
                 repo: TodoRepository,
                 worklog_repo: "WorkLogRepository | None" = None) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setAcceptDrops(True)
        self._quadrant = quadrant
        self._repo = repo
        self._worklog = worklog_repo

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(6)

        header = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {COLORS[color_key]}; font-size: 12px;")
        header.addWidget(dot)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("SectionTitle")
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._count = QLabel("0")
        self._count.setObjectName("Faint")
        header.addWidget(self._count)
        outer.addLayout(header)

        # 条目滚动区
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_host = QWidget()
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(2)
        self._list_lay.addStretch(1)
        self._scroll.setWidget(self._list_host)
        outer.addWidget(self._scroll, 1)

        # 快速添加
        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("添加待办…")
        self._input.returnPressed.connect(self._on_add)
        add_row.addWidget(self._input, 1)
        add_btn = QPushButton("+")
        add_btn.setObjectName("Primary")
        add_btn.setFixedWidth(34)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        add_row.addWidget(add_btn)
        outer.addLayout(add_row)

        self.reload()

    # --- 拖放: 接收从其它象限拖来的待办 ------------------------------
    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasFormat(TODO_MIME):
            event.acceptProposedAction()
            self.setProperty("dropHover", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):  # noqa: N802
        self.setProperty("dropHover", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):  # noqa: N802
        self.setProperty("dropHover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        data = event.mimeData().data(TODO_MIME)
        if not data:
            return
        try:
            todo_id = int(bytes(data).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        event.acceptProposedAction()
        self.todo_moved.emit(todo_id, self._quadrant)

    def _on_add(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._repo.add(text, quadrant=self._quadrant)
        self._input.clear()
        self.reload()
        self.changed.emit()

    def reload(self) -> None:
        # 清空现有行 (保留末尾 stretch)
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        todos = self._repo.list_by_quadrant(self._quadrant)
        pending = sum(1 for t in todos if not t.done)
        self._count.setText(str(pending))
        for todo in todos:
            row = TodoItemRow(todo, self._repo, self._worklog)
            row.changed.connect(self._on_row_changed)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)

    def _on_row_changed(self) -> None:
        self.reload()
        self.changed.emit()


class TodoPanel(QWidget):
    """四象限主面板。"""

    data_changed = Signal()

    def __init__(self, repo: TodoRepository | None = None,
                 worklog_repo=None) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._repo = repo or TodoRepository()
        if worklog_repo is None:
            from app.repositories.worklog_repo import WorkLogRepository
            worklog_repo = WorkLogRepository()
        self._worklog = worklog_repo

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("四象限待办")
        title.setObjectName("PanelTitle")
        head.addWidget(title)
        head.addStretch(1)
        hint = QLabel("双击编辑 · 拖拽可移动象限")
        hint.setObjectName("Faint")
        head.addWidget(hint)
        root.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(10)
        self._cards: list[QuadrantCard] = []
        for idx, (q, title, ckey) in enumerate(QUADRANTS):
            card = QuadrantCard(q, title, ckey, self._repo, self._worklog)
            card.changed.connect(self.data_changed.emit)
            card.todo_moved.connect(self._on_todo_moved)
            self._cards.append(card)
            grid.addWidget(card, idx // 2, idx % 2)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid, 1)

    def _on_todo_moved(self, todo_id: int, target_quadrant: int) -> None:
        todo = self._repo.get(todo_id)
        if todo is None or todo.quadrant == target_quadrant:
            return
        self._repo.move_quadrant(todo_id, target_quadrant)
        self.reload()
        self.data_changed.emit()

    def reload(self) -> None:
        for card in self._cards:
            card.reload()
