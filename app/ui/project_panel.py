"""项目管理面板。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMenu, QMessageBox, QPushButton, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from app.repositories.models import Project
from app.repositories.project_repo import ProjectRepository
from app.repositories.todo_repo import TodoRepository
from app.ui.theme import COLORS

PROJECT_COLORS = [
    "#5c9bd1", "#4cc38a", "#e5a94e", "#e5604d",
    "#9b6cf5", "#3bc4c4", "#e5d04d", "#8a93a8",
]

_MORE_STYLE = (
    "QPushButton{{background:transparent;border:none;color:{dim};padding:0;"
    "font-size:15px;font-weight:bold;border-radius:4px;}}"
    "QPushButton:hover{{background:{surf};color:{text};}}"
).format(dim=COLORS["text_dim"], surf=COLORS["surface"], text=COLORS["text"])

_QUADRANTS = [
    (1, "紧急 · 重要",      "q1"),
    (2, "重要 · 不紧急",    "q2"),
    (3, "紧急 · 不重要",    "q3"),
    (4, "不紧急 · 不重要",  "q4"),
]


# ---------------------------------------------------------------------------
# ColorPicker
# ---------------------------------------------------------------------------
class ColorPicker(QWidget):
    color_changed = Signal(str)

    def __init__(self, initial: str = PROJECT_COLORS[0]) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._selected = initial
        self._btns: dict[str, QPushButton] = {}
        for c in PROJECT_COLORS:
            btn = QPushButton()
            btn.setFixedSize(20, 20)
            btn.setToolTip(c)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, col=c: self._select(col))
            self._btns[c] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        self._refresh()

    def _select(self, color: str) -> None:
        self._selected = color
        self._refresh()
        self.color_changed.emit(color)

    def _refresh(self) -> None:
        for c, btn in self._btns.items():
            border = "2px solid white" if c == self._selected else "1px solid #555"
            btn.setStyleSheet(f"background-color:{c};border-radius:10px;border:{border};")

    def set_color(self, color: str) -> None:
        self._selected = color
        self._refresh()

    @property
    def color(self) -> str:
        return self._selected


# ---------------------------------------------------------------------------
# ProjectDetailView  — 单项目待办详情页
# ---------------------------------------------------------------------------
class _DetailTodoRow(QWidget):
    """详情页中的单条待办: 勾选 + 标题 + 删除。"""
    changed = Signal()

    def __init__(self, todo, repo: TodoRepository, worklog_repo) -> None:
        super().__init__()
        self._todo = todo
        self._repo = repo
        self._worklog = worklog_repo
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(6)

        self._check = QCheckBox()
        self._check.setChecked(todo.done)
        self._check.toggled.connect(self._on_toggle)
        lay.addWidget(self._check)

        self._lbl = QLabel(todo.title)
        self._lbl.setWordWrap(True)
        self._refresh_style()
        lay.addWidget(self._lbl, 1)

        del_btn = QPushButton("删除")
        del_btn.setObjectName("Ghost")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(self._on_delete)
        lay.addWidget(del_btn)

    def _refresh_style(self) -> None:
        if self._todo.done:
            self._lbl.setStyleSheet(
                f"color:{COLORS['text_faint']};text-decoration:line-through;"
            )
        else:
            self._lbl.setStyleSheet(f"color:{COLORS['text']};")

    def _on_toggle(self, checked: bool) -> None:
        self._todo.done = checked
        self._repo.set_done(self._todo.id, checked)
        if checked:
            if self._worklog.get_by_source_todo(self._todo.id) is None:
                self._worklog.add(
                    self._todo.title, tag="待办完成",
                    source_todo_id=self._todo.id,
                )
        else:
            self._worklog.delete_by_source_todo(self._todo.id)
        self._refresh_style()
        self.changed.emit()

    def _on_delete(self) -> None:
        self._worklog.delete_by_source_todo(self._todo.id)
        self._repo.delete(self._todo.id)
        self.changed.emit()


class ProjectDetailView(QWidget):
    back_requested = Signal()

    def __init__(self, todo_repo: TodoRepository) -> None:
        super().__init__()
        self._todo_repo = todo_repo
        self._proj: Project | None = None

        from app.repositories.worklog_repo import WorkLogRepository
        self._worklog = WorkLogRepository()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # 标题栏
        header = QHBoxLayout()
        back_btn = QPushButton("← 返回")
        back_btn.setObjectName("Ghost")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(back_btn)
        self._title_dot = QLabel("●")
        self._title_dot.setStyleSheet("font-size:14px;")
        header.addWidget(self._title_dot)
        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("PanelTitle")
        header.addWidget(self._title_lbl, 1)
        root.addLayout(header)

        # 待办滚动区
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(0, 0, 0, 0)
        self._content_lay.setSpacing(6)
        self._content_lay.addStretch(1)
        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, 1)

        # 快速添加
        add_row = QHBoxLayout()
        add_row.setSpacing(4)
        self._input = QLineEdit()
        self._input.setPlaceholderText("添加待办…")
        self._input.returnPressed.connect(self._on_add)
        add_row.addWidget(self._input, 1)
        self._q_combo = QComboBox()
        self._q_combo.setFixedWidth(140)
        for qid, qname, _ in _QUADRANTS:
            self._q_combo.addItem(qname, qid)
        add_row.addWidget(self._q_combo)
        add_btn = QPushButton("+")
        add_btn.setObjectName("Primary")
        add_btn.setFixedWidth(32)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)

    def load(self, project: Project) -> None:
        self._proj = project
        self._title_dot.setStyleSheet(
            f"color:{project.color};font-size:14px;"
        )
        self._title_lbl.setText(project.name)
        self._refresh()

    def _refresh(self) -> None:
        # 清空旧内容
        while self._content_lay.count() > 1:
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._proj is None:
            return

        insert_pos = 0
        for qid, qname, ckey in _QUADRANTS:
            todos = self._todo_repo.list_by_quadrant(qid, self._proj.id)
            if not todos:
                continue

            # 象限标题
            sec = QLabel(f"● {qname}")
            sec.setStyleSheet(
                f"color:{COLORS[ckey]};font-size:12px;font-weight:600;"
                "margin-top:4px;"
            )
            self._content_lay.insertWidget(insert_pos, sec)
            insert_pos += 1

            for todo in todos:
                row = _DetailTodoRow(todo, self._todo_repo, self._worklog)
                row.changed.connect(self._refresh)
                self._content_lay.insertWidget(insert_pos, row)
                insert_pos += 1

    def _on_add(self) -> None:
        text = self._input.text().strip()
        if not text or self._proj is None:
            return
        qid = self._q_combo.currentData()
        self._todo_repo.add(text, quadrant=qid, project_id=self._proj.id)
        self._input.clear()
        self._refresh()


# ---------------------------------------------------------------------------
# ProjectRow
# ---------------------------------------------------------------------------
class ProjectRow(QFrame):
    changed = Signal()
    view_requested = Signal(int)   # 请求进入详情页

    def __init__(self, project: Project, proj_repo: ProjectRepository,
                 todo_repo: TodoRepository) -> None:
        super().__init__()
        self.setObjectName("Card")
        self._proj = project
        self._proj_repo = proj_repo

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        # --- 查看页 (index 0) ---
        view_w = QWidget()
        vl = QHBoxLayout(view_w)
        vl.setContentsMargins(10, 6, 10, 6)
        vl.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(16)
        self._dot.setStyleSheet(f"color:{project.color};font-size:14px;")
        vl.addWidget(self._dot)

        self._name_lbl = QLabel(project.name)
        self._name_lbl.setToolTip(project.name)
        self._name_lbl.setCursor(Qt.PointingHandCursor)
        vl.addWidget(self._name_lbl, 1)

        count = todo_repo.count_pending_by_project(project.id)
        if count > 0:
            badge = QLabel(str(count))
            badge.setStyleSheet(
                f"background:{COLORS['accent_soft']};color:{COLORS['accent']};"
                "border-radius:8px;padding:0 6px;font-size:11px;font-weight:600;"
            )
            badge.setFixedHeight(16)
            vl.addWidget(badge)

        more = QPushButton("···")
        more.setFixedSize(28, 24)
        more.setStyleSheet(_MORE_STYLE)
        more.setCursor(Qt.PointingHandCursor)
        more.clicked.connect(lambda: self._show_menu(more))
        vl.addWidget(more)

        # 点击名称进入详情
        self._name_lbl.mousePressEvent = lambda e: (
            self.view_requested.emit(self._proj.id)
            if e.button() == Qt.LeftButton else None
        )

        self._stack.addWidget(view_w)   # index 0

        # --- 编辑页 (index 1) ---
        edit_w = QWidget()
        el = QVBoxLayout(edit_w)
        el.setContentsMargins(10, 6, 10, 8)
        el.setSpacing(4)

        self._picker = ColorPicker(project.color)
        el.addWidget(self._picker)

        row2 = QHBoxLayout()
        row2.setSpacing(4)
        self._name_edit = QLineEdit(project.name)
        self._name_edit.setMaxLength(30)
        self._name_edit.returnPressed.connect(self._save_edit)
        row2.addWidget(self._name_edit, 1)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("Primary")
        save_btn.setFixedWidth(50)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_edit)
        row2.addWidget(save_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("Ghost")
        cancel_btn.setFixedWidth(50)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self._cancel_edit)
        row2.addWidget(cancel_btn)
        el.addLayout(row2)

        self._stack.addWidget(edit_w)   # index 1

    def _enter_edit(self) -> None:
        self._picker.set_color(self._proj.color)
        self._name_edit.setText(self._proj.name)
        self._stack.setCurrentIndex(1)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _cancel_edit(self) -> None:
        self._stack.setCurrentIndex(0)

    def _save_edit(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            return
        self._proj.name = name
        self._proj.color = self._picker.color
        self._name_lbl.setText(name)
        self._dot.setStyleSheet(f"color:{self._proj.color};font-size:14px;")
        self._proj_repo.update(self._proj)
        self._stack.setCurrentIndex(0)
        self.changed.emit()

    def _show_menu(self, btn: QPushButton) -> None:
        menu = QMenu(self)
        menu.addAction("查看详情", lambda: self.view_requested.emit(self._proj.id))
        menu.addAction("编辑", self._enter_edit)
        menu.addAction("归档", self._on_archive)
        menu.addSeparator()
        menu.addAction("删除", self._on_delete)
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _on_archive(self) -> None:
        self._proj_repo.archive(self._proj.id)
        self.changed.emit()

    def _on_delete(self) -> None:
        reply = QMessageBox.question(
            self, "删除项目",
            f"确认删除「{self._proj.name}」？\n该项目的所有任务将变为「无项目」。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._proj_repo.delete(self._proj.id)
            self.changed.emit()


# ---------------------------------------------------------------------------
# _ArchivedSection
# ---------------------------------------------------------------------------
class _ArchivedSection(QWidget):
    changed = Signal()

    def __init__(self, proj_repo: ProjectRepository) -> None:
        super().__init__()
        self._proj_repo = proj_repo
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._toggle = QPushButton("▶  已归档项目")
        self._toggle.setObjectName("Ghost")
        self._toggle.setCheckable(True)
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.toggled.connect(self._on_toggle)
        root.addWidget(self._toggle)

        self._body = QWidget()
        self._body.setVisible(False)
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(8, 0, 0, 0)
        self._body_lay.setSpacing(4)
        root.addWidget(self._body)

    def _on_toggle(self, checked: bool) -> None:
        self._toggle.setText(("▼" if checked else "▶") + "  已归档项目")
        self._body.setVisible(checked)
        if checked:
            self._reload()

    def _reload(self) -> None:
        while self._body_lay.count():
            item = self._body_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for proj in self._proj_repo.list_archived():
            row_w = QWidget()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{proj.color};font-size:14px;")
            dot.setFixedWidth(16)
            row.addWidget(dot)
            lbl = QLabel(proj.name)
            lbl.setStyleSheet(f"color:{COLORS['text_faint']};")
            row.addWidget(lbl, 1)
            for label, cb in [
                ("恢复", lambda _, pid=proj.id: self._restore(pid)),
                ("删除", lambda _, pid=proj.id, nm=proj.name: self._delete(pid, nm)),
            ]:
                b = QPushButton(label)
                b.setObjectName("Ghost")
                b.setFixedWidth(44)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(cb)
                row.addWidget(b)
            self._body_lay.addWidget(row_w)

    def _restore(self, pid: int) -> None:
        self._proj_repo.restore(pid)
        self._reload()
        self.changed.emit()

    def _delete(self, pid: int, name: str) -> None:
        reply = QMessageBox.question(
            self, "删除项目",
            f"确认删除「{name}」？\n该项目的所有任务将变为「无项目」。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._proj_repo.delete(pid)
            self._reload()
            self.changed.emit()

    def reload_if_open(self) -> None:
        if self._toggle.isChecked():
            self._reload()


# ---------------------------------------------------------------------------
# ProjectPanel
# ---------------------------------------------------------------------------
class ProjectPanel(QWidget):
    data_changed = Signal()

    def __init__(self, proj_repo: ProjectRepository | None = None,
                 todo_repo: TodoRepository | None = None) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._proj_repo = proj_repo or ProjectRepository()
        self._todo_repo = todo_repo or TodoRepository()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶层 stack: 0=列表, 1=详情
        self._main_stack = QStackedWidget()
        root.addWidget(self._main_stack)

        # --- 列表页 ---
        list_page = QWidget()
        list_lay = QVBoxLayout(list_page)
        list_lay.setContentsMargins(0, 0, 0, 0)
        list_lay.setSpacing(10)

        title = QLabel("项目")
        title.setObjectName("PanelTitle")
        list_lay.addWidget(title)

        add_card = QFrame()
        add_card.setObjectName("InputCard")
        add_lay = QVBoxLayout(add_card)
        add_lay.setContentsMargins(10, 8, 10, 8)
        add_lay.setSpacing(6)
        self._color_picker = ColorPicker()
        add_lay.addWidget(self._color_picker)
        add_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("新项目名称…")
        self._name_input.setMaxLength(30)
        self._name_input.returnPressed.connect(self._on_add)
        add_row.addWidget(self._name_input, 1)
        add_btn = QPushButton("添加")
        add_btn.setObjectName("Primary")
        add_btn.setFixedWidth(54)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        add_row.addWidget(add_btn)
        add_lay.addLayout(add_row)
        list_lay.addWidget(add_card)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._list_host = QWidget()
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(4)
        self._list_lay.addStretch(1)
        self._scroll.setWidget(self._list_host)
        list_lay.addWidget(self._scroll, 1)

        self._archived = _ArchivedSection(self._proj_repo)
        self._archived.changed.connect(self._on_proj_changed)
        list_lay.addWidget(self._archived)

        self._main_stack.addWidget(list_page)   # index 0

        # --- 详情页 ---
        self._detail = ProjectDetailView(self._todo_repo)
        self._detail.back_requested.connect(
            lambda: self._main_stack.setCurrentIndex(0)
        )
        self._main_stack.addWidget(self._detail)   # index 1

        self.reload()

    # --- 项目增删改 -------------------------------------------------------
    def _on_add(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            return
        if self._proj_repo.name_exists(name):
            self._name_input.setStyleSheet("border:1px solid red;")
            return
        self._name_input.setStyleSheet("")
        self._proj_repo.add(name, color=self._color_picker.color)
        self._name_input.clear()
        self.reload()
        self.data_changed.emit()

    def _open_detail(self, project_id: int) -> None:
        proj = self._proj_repo.get(project_id)
        if proj is None:
            return
        self._detail.load(proj)
        self._main_stack.setCurrentIndex(1)

    def reload(self) -> None:
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for proj in self._proj_repo.list_active():
            row = ProjectRow(proj, self._proj_repo, self._todo_repo)
            row.changed.connect(self._on_proj_changed)
            row.view_requested.connect(self._open_detail)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)
        self._archived.reload_if_open()

    def _on_proj_changed(self) -> None:
        self.reload()
        self.data_changed.emit()
