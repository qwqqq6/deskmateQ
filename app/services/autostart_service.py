"""开机自启服务 (Windows)。

通过写入注册表 HKCU\\...\\Run 实现当前用户登录自启, 无需管理员权限。
非 Windows 平台下各方法安全降级为 no-op。
"""
from __future__ import annotations

import sys
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "DeskMate"

_IS_WINDOWS = sys.platform.startswith("win")


def _launch_command() -> str:
    """构造启动命令。优先使用打包后的 exe, 否则用 pythonw + main.py。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包场景
        return f'"{sys.executable}"'
    # 开发场景: 用 pythonw 避免弹出控制台窗口
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else exe
    main_py = Path(__file__).resolve().parents[2] / "main.py"
    return f'"{runner}" "{main_py}"'


class AutostartService:
    """管理开机自启注册表项。"""

    def is_enabled(self) -> bool:
        if not _IS_WINDOWS:
            return False
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, _VALUE_NAME)
                return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def enable(self) -> bool:
        if not _IS_WINDOWS:
            return False
        import winreg

        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.SetValueEx(
                    key, _VALUE_NAME, 0, winreg.REG_SZ, _launch_command()
                )
            return True
        except OSError:
            return False

    def disable(self) -> bool:
        if not _IS_WINDOWS:
            return False
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, _VALUE_NAME)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False

    def apply(self, enabled: bool) -> bool:
        return self.enable() if enabled else self.disable()
