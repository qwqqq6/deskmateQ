"""跨平台系统集成小工具: 打开文件 / 文件夹。

集中实现, 避免在多个 UI 处重复 os.startfile / open / xdg-open 分支。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_path(target: str | Path) -> bool:
    """用系统默认方式打开文件或文件夹。成功返回 True。

    - Windows: os.startfile
    - macOS:   open
    - 其它:     xdg-open
    """
    target = str(target)
    try:
        if sys.platform.startswith("win"):
            os.startfile(target)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", target], check=False)
        else:
            subprocess.run(["xdg-open", target], check=False)
        return True
    except OSError:
        return False
