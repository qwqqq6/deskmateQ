"""主窗口: 无边框桌面小部件外壳。

负责: 自定义标题栏 (拖动/最小化/关闭到托盘)、侧边导航切换面板、
窗口几何与外观持久化、定时自动备份、恢复后重启提示、系统托盘。
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu,
    QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from app.core.config import Config
from app.services.backup_service import BackupService
from app.ui.components.toast import Toast
from app.ui.edge_dock import EdgeDock
from app.ui.project_panel import ProjectPanel
from app.ui.reimbursement_panel import ReimbursementPanel
from app.ui.settings_panel import SettingsPanel
from app.ui.theme import COLORS, build_qss
from app.ui.todo_panel import TodoPanel
from app.ui.worklog_panel import WorkLogPanel

_NAV = [
    ("project", "项目", "◈", "  ◈   项目"),
    ("todo", "四象限待办", "▦", "  ▦   四象限"),
    ("worklog", "工作日志", "✎", "  ✎   工作日志"),
    ("reimb", "报销记录", "¥", "  ¥   报销记录"),
    ("settings", "设置", "⚙", "  ⚙   设置"),
]


def _make_icon() -> QIcon:
    """生成一个简单的圆角强调色图标, 避免依赖外部资源文件。"""
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(COLORS["accent"]))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(6, 6, 52, 52, 14, 14)
    p.setPen(QColor("white"))
    f = p.font()
    f.setPointSize(26)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignCenter, "D")
    p.end()
    return QIcon(pix)


class TitleBar(QWidget):
    """自定义标题栏: 拖动 + 最小化 + 关闭。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.setObjectName("TitleBar")
        self.setFixedHeight(40)
        self._window = window
        self._drag_pos: QPoint | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 8, 0)
        lay.setSpacing(6)

        title = QLabel("DeskMateQ")
        title.setObjectName("AppTitle")
        lay.addWidget(title)
        lay.addStretch(1)

        # 置顶切换 (图钉)
        self._pin = QPushButton()
        self._pin.setObjectName("WinBtn")
        self._pin.setCheckable(True)
        self._pin.setFixedSize(28, 28)
        self._pin.setCursor(Qt.PointingHandCursor)
        self._pin.setChecked(window._config.always_on_top)
        self._update_pin_visual()
        self._pin.clicked.connect(self._on_pin_clicked)
        lay.addWidget(self._pin)

        mini = QPushButton("—")
        mini.setObjectName("WinBtn")
        mini.setFixedSize(28, 28)
        mini.setCursor(Qt.PointingHandCursor)
        mini.clicked.connect(window.showMinimized)
        lay.addWidget(mini)

        close = QPushButton("✕")
        close.setObjectName("CloseBtn")
        close.setFixedSize(28, 28)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(window.hide_to_tray)
        lay.addWidget(close)

    def _on_pin_clicked(self) -> None:
        self._window.set_always_on_top(self._pin.isChecked())
        self._update_pin_visual()

    def _update_pin_visual(self) -> None:
        on = self._pin.isChecked()
        self._pin.setText("📌" if on else "📍")
        self._pin.setToolTip("已置顶 (点击取消)" if on else "点击置顶窗口")

    def sync_pin(self, checked: bool) -> None:
        self._pin.setChecked(checked)
        self._update_pin_visual()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint()
                - self._window.frameGeometry().topLeft()
            )
            self._window.on_drag_start()
            event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_pos = None
        self._window._persist_geometry()
        self._window.on_drag_finish()


class MainWindow(QWidget):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._backup = BackupService(config.backup_dir)

        self.setWindowTitle("DeskMateQ")
        self.setWindowIcon(_make_icon())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._apply_window_flags()

        # 根容器 (圆角描边)
        self._root = QFrame()
        self._root.setObjectName("RootFrame")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._root)

        root_lay = QVBoxLayout(self._root)
        root_lay.setContentsMargins(10, 6, 10, 10)
        root_lay.setSpacing(6)

        self._title_bar = TitleBar(self)
        root_lay.addWidget(self._title_bar)

        # 主体: 侧边导航 + 内容堆栈
        body = QHBoxLayout()
        body.setSpacing(10)
        nav_bar = QFrame()
        nav_bar.setObjectName("NavBar")
        nav_bar.setLayout(self._build_nav())
        body.addWidget(nav_bar)
        self._stack = QStackedWidget()
        body.addWidget(self._stack, 1)
        root_lay.addLayout(body, 1)

        self._build_panels()
        self._toast = Toast(self._root)

        self._apply_appearance()
        self._restore_geometry()
        self._select_panel(self._config.active_panel)

        # 贴边自动隐藏控制器
        self._edge_dock = EdgeDock(self)
        self._edge_dock.set_auto_hide(self._config.edge_auto_hide)
        self._setup_tray()
        self._setup_autobackup()
        self._edge_dock.set_enabled(self._config.edge_dock)

    # --- 窗口外观 / 标志 --------------------------------------------
    def _apply_window_flags(self) -> None:
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self._config.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _apply_appearance(self) -> None:
        self.setStyleSheet(build_qss(self._config.accent, self._config.theme_mode))
        self.setWindowOpacity(max(0.4, min(1.0, self._config.opacity)))

    def set_always_on_top(self, on: bool) -> None:
        """切换窗口置顶, 并持久化。供标题栏图钉与设置面板共用。"""
        if self._config.always_on_top == on:
            return
        self._config.always_on_top = on
        self._config.save()
        was_visible = self.isVisible()
        self._apply_window_flags()
        if was_visible:
            self.show()
        if hasattr(self, "_settings"):
            self._settings.sync_always_on_top(on)

    def set_edge_dock(self, on: bool) -> None:
        """开关贴边自动隐藏。"""
        self._config.edge_dock = on
        self._config.save()
        if hasattr(self, "_edge_dock"):
            self._edge_dock.set_enabled(on)

    def set_edge_auto_hide(self, on: bool) -> None:
        """开关贴边后的自动隐藏 (收起)。"""
        self._config.edge_auto_hide = on
        self._config.save()
        if hasattr(self, "_edge_dock"):
            self._edge_dock.set_auto_hide(on)

    # --- 拖动回调 (供标题栏调用, 联动贴边逻辑) -----------------------
    def on_drag_start(self) -> None:
        if hasattr(self, "_edge_dock"):
            self._edge_dock.suspend(True)

    def on_drag_finish(self) -> None:
        if hasattr(self, "_edge_dock"):
            self._edge_dock.suspend(False)
            self._edge_dock.on_drag_finished()

    # --- 导航 --------------------------------------------------------
    def _build_nav(self) -> QVBoxLayout:
        nav = QVBoxLayout()
        nav.setSpacing(4)
        nav.setContentsMargins(6, 8, 6, 8)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}
        for key, tip, _icon, label in _NAV:
            btn = QPushButton(label)
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedWidth(116)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, k=key: self._select_panel(k))
            self._nav_group.addButton(btn)
            self._nav_buttons[key] = btn
            nav.addWidget(btn)
        nav.addStretch(1)
        return nav

    def _build_panels(self) -> None:
        self._project = ProjectPanel()
        self._todo = TodoPanel()
        self._worklog = WorkLogPanel()
        self._reimb = ReimbursementPanel()
        self._settings = SettingsPanel(self._config)

        # 项目增删改时刷新四象限筛选栏
        self._project.data_changed.connect(self._todo.notify_projects_changed)

        self._worklog.toast_requested.connect(self.show_toast)
        self._settings.toast_requested.connect(self.show_toast)
        self._settings.config_changed.connect(self._on_config_changed)
        self._settings.edge_dock_changed.connect(self.set_edge_dock)
        self._settings.edge_auto_hide_changed.connect(self.set_edge_auto_hide)
        self._settings.restore_requested.connect(self._on_restore)

        self._panel_index = {
            "project": self._stack.addWidget(self._project),
            "todo": self._stack.addWidget(self._todo),
            "worklog": self._stack.addWidget(self._worklog),
            "reimb": self._stack.addWidget(self._reimb),
            "settings": self._stack.addWidget(self._settings),
        }

    def _select_panel(self, key: str) -> None:
        if key not in self._panel_index:
            key = "todo"
        self._stack.setCurrentIndex(self._panel_index[key])
        if key in self._nav_buttons:
            self._nav_buttons[key].setChecked(True)
        self._config.active_panel = key
        self._config.save()
        # 进入面板时刷新数据
        if key == "project":
            self._project.reload()
        elif key == "todo":
            self._todo.reload()
        elif key == "worklog":
            self._worklog.reload()
        elif key == "reimb":
            self._reimb.reload()
        elif key == "settings":
            self._settings.reload_backups()

    # --- 配置变化 ----------------------------------------------------
    def _on_config_changed(self) -> None:
        was_visible = self.isVisible()
        self._apply_window_flags()
        self._apply_appearance()
        # 备份目录可能已更改, 重建备份服务供自动备份/退出备份使用
        self._backup = BackupService(self._config.backup_dir)
        self._setup_autobackup()
        # 同步标题栏图钉状态 (置顶可能在设置面板被改动)
        if hasattr(self, "_title_bar"):
            self._title_bar.sync_pin(self._config.always_on_top)
        # 重新加载当前面板, 使内联着色 (强调色/象限色) 跟随新主题刷新
        self._refresh_current_panel()
        if was_visible:
            self.show()

    def _refresh_current_panel(self) -> None:
        panel = self._stack.currentWidget()
        if panel is not None and hasattr(panel, "reload"):
            panel.reload()

    def show_toast(self, msg: str) -> None:
        self._toast.show_message(msg)

    # --- 几何持久化 --------------------------------------------------
    def _restore_geometry(self) -> None:
        c = self._config
        self.resize(c.window_width, c.window_height)
        if c.window_x is not None and c.window_y is not None:
            self.move(c.window_x, c.window_y)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(
                screen.right() - c.window_width - 30,
                screen.top() + 60,
            )

    def _persist_geometry(self) -> None:
        # 贴边收起态下窗口在屏幕外, 不持久化避免下次启动看不到
        if getattr(self, "_edge_dock", None) is not None and self._edge_dock._collapsed:
            return
        self._config.window_x = self.x()
        self._config.window_y = self.y()
        self._config.window_width = self.width()
        self._config.window_height = self.height()
        self._config.save()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_toast"):
            self._toast._reposition()

    # --- 系统托盘 ----------------------------------------------------
    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(_make_icon(), self)
        self._tray.setToolTip("DeskMateQ")
        menu = QMenu()
        show_act = QAction("显示窗口", self)
        show_act.triggered.connect(self.show_from_tray)
        menu.addAction(show_act)
        backup_act = QAction("立即备份", self)
        backup_act.triggered.connect(self._manual_backup)
        menu.addAction(backup_act)
        menu.addSeparator()
        quit_act = QAction("退出", self)
        quit_act.triggered.connect(self._real_quit)
        menu.addAction(quit_act)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_from_tray()

    def hide_to_tray(self) -> None:
        self._persist_geometry()
        self.hide()
        self._tray.showMessage(
            "DeskMateQ", "已最小化到系统托盘, 数据已自动保存。",
            QSystemTrayIcon.Information, 1500,
        )

    def show_from_tray(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        # 从托盘恢复时, 若处于贴边收起态则展开
        if getattr(self, "_edge_dock", None) is not None and self._edge_dock.enabled:
            self._edge_dock._expand()
        self._select_panel(self._config.active_panel)

    def _manual_backup(self) -> None:
        info = self._backup.create_backup(label="tray")
        self._tray.showMessage(
            "DeskMateQ", f"已备份: {info.name}",
            QSystemTrayIcon.Information, 1500,
        )

    def _real_quit(self) -> None:
        self._persist_geometry()
        self._backup.create_backup(label="exit")
        self._tray.hide()
        QApplication.quit()

    # --- 自动备份 ----------------------------------------------------
    def _setup_autobackup(self) -> None:
        if not hasattr(self, "_backup_timer"):
            self._backup_timer = QTimer(self)
            self._backup_timer.timeout.connect(self._auto_backup_tick)
        self._backup_timer.stop()
        interval = self._config.backup_interval_min
        if interval > 0:
            self._backup_timer.start(interval * 60 * 1000)

    def _auto_backup_tick(self) -> None:
        self._backup.create_backup(label="auto")

    # --- 恢复 --------------------------------------------------------
    def _on_restore(self, path: str) -> None:
        try:
            self._backup.restore(path)
        except Exception as exc:  # noqa: BLE001
            self.show_toast(f"恢复失败: {exc}")
            return
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            self, "恢复完成",
            "数据已恢复, 应用将重启以加载新数据。",
        )
        self._restart_app()

    def _restart_app(self) -> None:
        import os

        self._tray.hide()
        self._persist_geometry()
        python = sys.executable
        if getattr(sys, "frozen", False):
            os.execl(python, python, *sys.argv[1:])
        else:
            from pathlib import Path
            main_py = str(Path(__file__).resolve().parents[2] / "main.py")
            os.execl(python, python, main_py)

    def closeEvent(self, event):  # noqa: N802
        event.ignore()
        self.hide_to_tray()
