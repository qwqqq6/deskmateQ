"""四象限 TodoList 面板（支持项目筛选）。"""
from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.repositories.models import Todo
from app.repositories.project_repo import ProjectRepository
from app.repositories.todo_repo import TodoRepository, _FILTER_ALL
from app.ui.theme import COLORS

QUADRANTS = [
    (1, "紧急 · 重要", "q1"),
    (2, "重要 · 不紧急", "q2"),
    (3, "紧急 · 不重要", "q3"),
    (4, "不紧急 · 不重要", "q4"),
]
TODO_MIME = "application/x-deskmateq-todo-id"

# UI 层筛选哨兵: "all" 表示不过滤, None 表示无项目, int 表示具体项目 id
_UI_ALL = "all"


def _to_repo_filter(ui_filter):
    """UI 筛选值 → repo 的 project_filter 参数。"""
    return _FILTER_ALL if ui_filter == _UI_ALL else ui_filter


class _FilterBar(QWidget):
    """项目筛选 pill 栏。无 active 项目时自动隐藏。"""
    filter_changed = Signal(object)  # "all" | None | int

    def __init__(self) -> None:
        super().__init__()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(34)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._inner = QWidget()
        self._lay = QHBoxLayout(self._inner)
        self._lay.setContentsMargins(0, 2, 0, 2)
        self._lay.setSpacing(4)
        self._lay.addStretch(1)
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)
        self._current = _UI_ALL

    def reload(self, projects) -> None:
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        pills = [(_UI_ALL, "全部", None), (None, "无项目", None)]
        pills += [(p.id, p.name, p.color) for p in projects]

        for fval, label, color in pills:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setChecked(fval == self._current)
            if color:
                dot = f'<span style="color:{color}">● </span>'
                btn.setText(f"● {label}")
                btn.setStyleSheet(
                    f"QPushButton{{color:{COLORS['text_dim']};"
                    f"border:1px solid {COLORS['border_soft']};"
                    f"border-radius:12px;padding:2px 10px;background:transparent;}}"
                    f"QPushButton:checked{{background:{color}22;border:1px solid {color};"
                    f"color:{color};font-weight:600;}}"
                    f"QPushButton:hover{{background:{COLORS['surface']};}}"
                )
            btn.clicked.connect(lambda _, v=fval: self._select(v))
            self._lay.insertWidget(self._lay.count() - 1, btn)

        self.setVisible(bool(projects))

    def _select(self, value) -> None:
        self._current = value
        # 刷新选中态
        for i in range(self._lay.count() - 1):
            w = self._lay.itemAt(i).widget()
            if isinstance(w, QPushButton):
                fvals = [_UI_ALL, None] + []  # rebuilt below
        # 重新 reload 以更新 checked 状态
        self.filter_changed.emit(value)

    def set_current(self, value) -> None:
        self._current = value

    @property
    def current(self):
        return self._current


class TodoItemRow(QWidget):
    """单条待办: 项目色条 + 复选框 + 标题 + 删除。"""
    changed = Signal()

    def __init__(self, todo: Todo, repo: TodoRepository,
                 worklog_repo=None,
                 project_color: str | None = None,
                 project_name: str | None = None) -> None:
        super().__init__()
        self._todo = todo
        self._repo = repo
        self._project_name = project_name
        if worklog_repo is None:
            from app.repositories.worklog_repo import WorkLogRepository
            worklog_repo = WorkLogRepository()
        self._worklog = worklog_repo
        self._editing = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(4)
        self._lay = lay

        # 项目色条 (3px 竖向色块)
        if project_color:
            bar = QFrame()
            bar.setFixedSize(3, 18)
            bar.setStyleSheet(
                f"background:{project_color};border-radius:2px;"
            )
            lay.addWidget(bar)

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
        lay.addWidget(self._del)

        self._drag_start = None

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
        mime.setData(TODO_MIME, str(self._todo.id).encode())
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def _apply_label_style(self) -> None:
        if self._todo.done:
            self._label.setStyleSheet(
                f"color:{COLORS['text_faint']};text-decoration:line-through;"
            )
        else:
            self._label.setStyleSheet(f"color:{COLORS['text']};")

    def _on_toggle(self, checked: bool) -> None:
        self._todo.done = checked
        self._repo.set_done(self._todo.id, checked)
        if checked:
            if self._worklog.get_by_source_todo(self._todo.id) is None:
                content = (
                    f"[{self._project_name}] {self._todo.title}"
                    if self._project_name else self._todo.title
                )
                self._worklog.add(content, tag="待办完成", source_todo_id=self._todo.id)
        else:
            self._worklog.delete_by_source_todo(self._todo.id)
        self._apply_label_style()
        self.changed.emit()

    def _on_delete(self) -> None:
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
        self._lay.insertWidget(self._lay.count() - 1, self._editor, 1)
        self._editor.setFocus()
        self._editor.selectAll()
        self._editor.returnPressed.connect(self._save_edit)
        self._editor.editingFinished.connect(self._save_edit)

    def _save_edit(self) -> None:
        if not self._editing or not self._editor:
            return
        text = self._editor.text().strip()
        self._editing = False
        changed = False
        if text and text != self._todo.title:
            self._todo.title = text
            self._repo.update(self._todo)
            self._label.setText(text)
            changed = True
        self._editor.deleteLater()
        self._editor = None
        self._label.show()
        if changed:
            self.changed.emit()


class QuadrantCard(QFrame):
    """单个象限卡片（含项目筛选与项目选择器）。"""
    changed = Signal()
    todo_moved = Signal(int, int)

    def __init__(self, quadrant: int, title: str, color_key: str,
                 repo: TodoRepository,
                 worklog_repo=None,
                 project_repo: ProjectRepository | None = None) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setAcceptDrops(True)
        self._quadrant = quadrant
        self._repo = repo
        self._worklog = worklog_repo
        self._project_repo = project_repo
        self._ui_filter = _UI_ALL  # "all" | None | int

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(6)

        header = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{COLORS[color_key]};font-size:12px;")
        header.addWidget(dot)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("SectionTitle")
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._count = QLabel("0")
        self._count.setObjectName("Faint")
        header.addWidget(self._count)
        outer.addLayout(header)

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

        # 快速添加行
        add_row = QHBoxLayout()
        add_row.setSpacing(4)
        self._input = QLineEdit()
        self._input.setPlaceholderText("添加待办…")
        self._input.returnPressed.connect(self._on_add)
        add_row.addWidget(self._input, 1)
        # 项目下拉 (有项目时才显示)
        self._proj_combo = QComboBox()
        self._proj_combo.setFixedWidth(80)
        self._proj_combo.setToolTip("选择所属项目")
        add_row.addWidget(self._proj_combo)
        add_btn = QPushButton("+")
        add_btn.setObjectName("Primary")
        add_btn.setFixedWidth(34)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        add_row.addWidget(add_btn)
        outer.addLayout(add_row)

        self.reload()

    # --- 拖放 -----------------------------------------------------------
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
            todo_id = int(bytes(data).decode())
        except (ValueError, UnicodeDecodeError):
            return
        event.acceptProposedAction()
        self.todo_moved.emit(todo_id, self._quadrant)

    # --- 项目筛选 -------------------------------------------------------
    def set_filter(self, ui_filter) -> None:
        self._ui_filter = ui_filter
        self._sync_combo_preselect()
        self.reload()

    def reload_projects(self, projects) -> None:
        """外部通知项目列表变化时刷新下拉。"""
        self._refresh_combo(projects)
        self.reload()

    def _refresh_combo(self, projects=None) -> None:
        if projects is None and self._project_repo:
            projects = self._project_repo.list_active()
        else:
            projects = projects or []
        self._proj_combo.clear()
        self._proj_combo.addItem("无项目", None)
        for p in projects:
            self._proj_combo.addItem(p.name, p.id)
        self._proj_combo.setVisible(self._proj_combo.count() > 1)
        self._sync_combo_preselect()

    def _sync_combo_preselect(self) -> None:
        """将筛选状态同步到下拉预选项。"""
        if isinstance(self._ui_filter, int):
            for i in range(self._proj_combo.count()):
                if self._proj_combo.itemData(i) == self._ui_filter:
                    self._proj_combo.setCurrentIndex(i)
                    return
        # "all" 或 None 时默认选「无项目」
        self._proj_combo.setCurrentIndex(0)

    # --- 添加 -----------------------------------------------------------
    def _on_add(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        project_id = self._proj_combo.currentData()
        self._repo.add(text, quadrant=self._quadrant, project_id=project_id)
        self._input.clear()
        self.reload()
        self.changed.emit()

    # --- 刷新列表 -------------------------------------------------------
    def reload(self) -> None:
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 项目 id → (color, name) 映射
        proj_map: dict[int, tuple[str, str]] = {}
        if self._project_repo:
            for p in self._project_repo.list_active():
                proj_map[p.id] = (p.color, p.name)

        todos = self._repo.list_by_quadrant(
            self._quadrant, _to_repo_filter(self._ui_filter)
        )
        pending = sum(1 for t in todos if not t.done)
        self._count.setText(str(pending))

        for todo in todos:
            color, name = proj_map.get(todo.project_id, (None, None))
            row = TodoItemRow(
                todo, self._repo, self._worklog,
                project_color=color, project_name=name,
            )
            row.changed.connect(self._on_row_changed)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)

        # 首次 reload 时初始化下拉 (只初始化一次)
        if self._proj_combo.count() == 0:
            self._refresh_combo()

    def _on_row_changed(self) -> None:
        self.reload()
        self.changed.emit()


class TodoPanel(QWidget):
    """四象限主面板。"""
    data_changed = Signal()

    def __init__(self, repo: TodoRepository | None = None,
                 worklog_repo=None,
                 project_repo: ProjectRepository | None = None) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._repo = repo or TodoRepository()
        self._project_repo = project_repo or ProjectRepository()
        if worklog_repo is None:
            from app.repositories.worklog_repo import WorkLogRepository
            worklog_repo = WorkLogRepository()
        self._worklog = worklog_repo

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("四象限待办")
        title.setObjectName("PanelTitle")
        head.addWidget(title)
        head.addStretch(1)
        hint = QLabel("双击编辑 · 拖拽可移动象限")
        hint.setObjectName("Faint")
        head.addWidget(hint)
        root.addLayout(head)

        # 筛选栏
        self._filter_bar = _FilterBar()
        self._filter_bar.filter_changed.connect(self._on_filter_changed)
        root.addWidget(self._filter_bar)

        grid = QGridLayout()
        grid.setSpacing(10)
        self._cards: list[QuadrantCard] = []
        for idx, (q, t, ckey) in enumerate(QUADRANTS):
            card = QuadrantCard(q, t, ckey, self._repo, self._worklog, self._project_repo)
            card.changed.connect(self.data_changed.emit)
            card.todo_moved.connect(self._on_todo_moved)
            self._cards.append(card)
            grid.addWidget(card, idx // 2, idx % 2)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid, 1)

        self._reload_filter_bar()

    def _reload_filter_bar(self) -> None:
        projects = self._project_repo.list_active()
        self._filter_bar.reload(projects)
        for card in self._cards:
            card.reload_projects(projects)

    def _on_filter_changed(self, ui_filter) -> None:
        self._filter_bar.set_current(ui_filter)
        # 重建筛选栏以更新 checked 状态
        self._reload_filter_bar()
        self._filter_bar.set_current(ui_filter)
        for card in self._cards:
            card.set_filter(ui_filter)

    def notify_projects_changed(self) -> None:
        """ProjectPanel 增删改项目后通知本面板刷新筛选栏。"""
        self._reload_filter_bar()

    def _on_todo_moved(self, todo_id: int, target_quadrant: int) -> None:
        todo = self._repo.get(todo_id)
        if todo is None or todo.quadrant == target_quadrant:
            return
        self._repo.move_quadrant(todo_id, target_quadrant)
        self.reload()
        self.data_changed.emit()

    def reload(self) -> None:
        self._reload_filter_bar()
        for card in self._cards:
            card.reload()
