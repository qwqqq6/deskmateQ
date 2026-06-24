"""DeskMate 应用入口。

职责: 单实例保护、初始化 QApplication、加载配置、应用自启偏好、
创建并显示主窗口。退出时已由窗口层处理数据备份。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保以脚本方式运行时能找到 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QSharedMemory, Qt
from PySide6.QtWidgets import QApplication

from app import __app_name__
from app.core.config import Config
from app.services.autostart_service import AutostartService
from app.ui.main_window import MainWindow


def _single_instance_guard() -> QSharedMemory | None:
    """利用共享内存保证仅运行一个实例。返回句柄需保活。"""
    shm = QSharedMemory("DeskMate_SingleInstance_Key")
    if shm.attach():
        # 已有实例在运行
        return None
    if not shm.create(1):
        return None
    return shm


def main() -> int:
    QApplication.setApplicationName(__app_name__)
    QApplication.setOrganizationName("DeskMate")
    # 高 DPI 适配
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    # 关闭最后窗口不退出 (常驻托盘)
    app.setQuitOnLastWindowClosed(False)

    guard = _single_instance_guard()
    if guard is None:
        # 已在运行, 直接退出
        return 0

    config = Config.load()

    # 同步自启偏好与系统实际状态: 以配置为准
    autostart = AutostartService()
    if config.autostart and not autostart.is_enabled():
        autostart.enable()

    window = MainWindow(config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
