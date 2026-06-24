"""设置面板: 开机自启、窗口行为、备份与恢复。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from app.core.config import Config
from app.services.autostart_service import AutostartService
from app.services.backup_service import BackupService
from app.ui.theme import COLORS

class SettingsPanel(QWidget):
    """设置与数据管理面板。"""

    # 配置变化时通知主窗口应用 (置顶/透明度/自启)
    config_changed = Signal()
    edge_dock_changed = Signal(bool)
    edge_auto_hide_changed = Signal(bool)
    toast_requested = Signal(str)
    restore_requested = Signal(str)  # 传备份路径

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._config = config
        self._autostart = AutostartService()
        self._backup = BackupService(config.backup_dir)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        head = QLabel("设置")
        head.setObjectName("PanelTitle")
        root.addWidget(head)

        root.addWidget(self._build_behavior_card())
        root.addWidget(self._build_backup_card())
        root.addStretch(1)

        self.reload_backups()

    # --- 行为设置 ----------------------------------------------------
    def _build_behavior_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(10)

        title = QLabel("常规")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)

        self._cb_autostart = QCheckBox("开机自动启动")
        self._cb_autostart.setChecked(self._autostart.is_enabled())
        self._cb_autostart.toggled.connect(self._on_autostart)
        lay.addWidget(self._cb_autostart)

        self._cb_top = QCheckBox("窗口置顶")
        self._cb_top.setChecked(self._config.always_on_top)
        self._cb_top.toggled.connect(self._on_top)
        lay.addWidget(self._cb_top)

        self._cb_edge = QCheckBox("屏幕贴边吸附")
        self._cb_edge.setChecked(self._config.edge_dock)
        self._cb_edge.setToolTip(
            "把窗口拖到屏幕边缘 (有一部分露出屏幕外) 即吸附贴边"
        )
        self._cb_edge.toggled.connect(self._on_edge_dock)
        lay.addWidget(self._cb_edge)

        # 贴边后是否自动收起 (缩进显示, 从属于上一项)
        self._cb_auto_hide = QCheckBox("    └ 贴边后自动收起隐藏")
        self._cb_auto_hide.setChecked(self._config.edge_auto_hide)
        self._cb_auto_hide.setToolTip(
            "开启: 鼠标离开后窗口滑出屏幕, 移到边缘再滑回\n"
            "关闭: 仅吸附贴边常驻, 不自动收起"
        )
        self._cb_auto_hide.setEnabled(self._config.edge_dock)
        self._cb_auto_hide.toggled.connect(self._on_edge_auto_hide)
        lay.addWidget(self._cb_auto_hide)

        # 主题模式
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("主题模式"))
        self._theme = QComboBox()
        for label, value in (("深色", "dark"), ("浅色", "light"), ("跟随系统", "system")):
            self._theme.addItem(label, value)
        idx = self._theme.findData(self._config.theme_mode)
        self._theme.setCurrentIndex(idx if idx >= 0 else 0)
        self._theme.currentIndexChanged.connect(self._on_theme)
        theme_row.addWidget(self._theme, 1)
        lay.addLayout(theme_row)

        # 透明度
        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("不透明度"))
        self._opacity = QComboBox()
        for pct in (100, 95, 90, 85, 80, 70, 60):
            self._opacity.addItem(f"{pct}%", pct / 100.0)
        # 选中当前值
        cur = round(self._config.opacity * 100)
        idx = self._opacity.findText(f"{cur}%")
        self._opacity.setCurrentIndex(idx if idx >= 0 else 0)
        self._opacity.currentIndexChanged.connect(self._on_opacity)
        op_row.addWidget(self._opacity, 1)
        lay.addLayout(op_row)

        # 备份间隔
        bk_row = QHBoxLayout()
        bk_row.addWidget(QLabel("自动备份间隔(分钟)"))
        self._interval = QSpinBox()
        self._interval.setRange(0, 1440)
        self._interval.setValue(self._config.backup_interval_min)
        self._interval.setToolTip("0 表示关闭自动备份")
        self._interval.valueChanged.connect(self._on_interval)
        bk_row.addWidget(self._interval, 1)
        lay.addLayout(bk_row)

        return card

    def _on_autostart(self, checked: bool) -> None:
        ok = self._autostart.apply(checked)
        if not ok and checked:
            self._cb_autostart.setChecked(False)
            self.toast_requested.emit("设置自启失败")
            return
        self._config.autostart = checked
        self._config.save()
        self.toast_requested.emit("已开启开机自启" if checked else "已关闭开机自启")

    def _on_top(self, checked: bool) -> None:
        self._config.always_on_top = checked
        self._config.save()
        self.config_changed.emit()

    def sync_always_on_top(self, checked: bool) -> None:
        """外部 (标题栏图钉) 改了置顶时, 同步勾选框而不触发回环。"""
        if self._cb_top.isChecked() != checked:
            self._cb_top.blockSignals(True)
            self._cb_top.setChecked(checked)
            self._cb_top.blockSignals(False)

    def _on_edge_dock(self, checked: bool) -> None:
        self._config.edge_dock = checked
        self._config.save()
        self._cb_auto_hide.setEnabled(checked)
        self.edge_dock_changed.emit(checked)

    def _on_edge_auto_hide(self, checked: bool) -> None:
        self._config.edge_auto_hide = checked
        self._config.save()
        self.edge_auto_hide_changed.emit(checked)

    def _on_opacity(self) -> None:
        self._config.opacity = self._opacity.currentData()
        self._config.save()
        self.config_changed.emit()

    def _on_theme(self) -> None:
        self._config.theme_mode = self._theme.currentData()
        self._config.save()
        self.config_changed.emit()

    def _on_interval(self, value: int) -> None:
        self._config.backup_interval_min = value
        self._config.save()
        self.config_changed.emit()

    # --- 备份与恢复 --------------------------------------------------
    def _build_backup_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("备份与恢复")
        title.setObjectName("SectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        backup_now = QPushButton("立即备份")
        backup_now.setObjectName("Primary")
        backup_now.setCursor(Qt.PointingHandCursor)
        backup_now.clicked.connect(self._on_backup_now)
        head.addWidget(backup_now)
        lay.addLayout(head)

        hint = QLabel("双击备份可恢复; 恢复前会自动创建当前数据快照。")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # 备份位置选择
        loc_row = QHBoxLayout()
        loc_row.setSpacing(6)
        loc_row.addWidget(QLabel("备份位置"))
        self._loc_label = QLabel()
        self._loc_label.setObjectName("Faint")
        self._loc_label.setWordWrap(True)
        self._update_loc_label()
        loc_row.addWidget(self._loc_label, 1)
        change_loc = QPushButton("更改…")
        change_loc.setCursor(Qt.PointingHandCursor)
        change_loc.clicked.connect(self._on_change_backup_dir)
        loc_row.addWidget(change_loc)
        reset_loc = QPushButton("默认")
        reset_loc.setObjectName("Ghost")
        reset_loc.setCursor(Qt.PointingHandCursor)
        reset_loc.setToolTip("恢复为默认备份目录")
        reset_loc.clicked.connect(self._on_reset_backup_dir)
        loc_row.addWidget(reset_loc)
        lay.addLayout(loc_row)

        self._backup_list = QListWidget()
        self._backup_list.setFixedHeight(150)
        self._backup_list.itemDoubleClicked.connect(self._on_restore)
        lay.addWidget(self._backup_list)

        btns = QHBoxLayout()
        open_dir = QPushButton("打开数据文件夹")
        open_dir.setCursor(Qt.PointingHandCursor)
        open_dir.clicked.connect(self._on_open_dir)
        btns.addWidget(open_dir)
        btns.addStretch(1)
        import_btn = QPushButton("从文件恢复…")
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.clicked.connect(self._on_restore_from_file)
        btns.addWidget(import_btn)
        lay.addLayout(btns)

        return card

    def reload_backups(self) -> None:
        self._backup_list.clear()
        for info in self._backup.list_backups():
            label = (
                f"{info.created_at.strftime('%Y-%m-%d %H:%M:%S')}   "
                f"{info.size_kb:.0f} KB"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, str(info.path))
            self._backup_list.addItem(item)

    def _on_backup_now(self) -> None:
        info = self._backup.create_backup(label="manual")
        self.reload_backups()
        self.toast_requested.emit(f"已备份: {info.name}")

    def _on_restore(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        self._confirm_restore(path)

    def _on_restore_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择备份文件", str(self._backup.backup_dir),
            "备份文件 (*.zip)",
        )
        if path:
            self._confirm_restore(path)

    def _update_loc_label(self) -> None:
        self._loc_label.setText(str(self._backup.backup_dir))

    def _on_change_backup_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择备份位置", str(self._backup.backup_dir),
        )
        if not folder:
            return
        self._config.backup_dir = folder
        self._config.save()
        self._backup = BackupService(folder)
        self._update_loc_label()
        self.reload_backups()
        self.toast_requested.emit("已更改备份位置")

    def _on_reset_backup_dir(self) -> None:
        self._config.backup_dir = None
        self._config.save()
        self._backup = BackupService()
        self._update_loc_label()
        self.reload_backups()
        self.toast_requested.emit("已恢复默认备份位置")

    def _confirm_restore(self, path: str) -> None:
        resp = QMessageBox.question(
            self, "恢复数据",
            "恢复将覆盖当前所有数据 (已自动快照当前数据)。\n"
            "恢复后需要重启应用。是否继续?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            self.restore_requested.emit(path)

    def _on_open_dir(self) -> None:
        from app.core.paths import paths
        from app.utils.system import open_path

        open_path(paths.root)
