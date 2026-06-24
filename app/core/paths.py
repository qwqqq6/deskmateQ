"""应用路径管理。

集中管理所有持久化位置, 使用 %LOCALAPPDATA%\\DeskMate 作为根目录,
确保数据、附件、备份都有专门的文件夹, 便于查看、修改与删除。
"""
from __future__ import annotations

import os
from pathlib import Path


def _app_root() -> Path:
    """返回应用数据根目录, 不存在则创建。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "DeskMate"


class AppPaths:
    """统一的路径访问入口。所有目录在首次访问时确保存在。"""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or _app_root()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for d in (self.root, self.data_dir, self.attachments_dir,
                  self.backup_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def data_dir(self) -> Path:
        """数据库所在目录。"""
        return self._root / "data"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "deskmate.db"

    @property
    def attachments_dir(self) -> Path:
        """报销附件 (截图/文件) 存放目录。"""
        return self._root / "attachments"

    @property
    def backup_dir(self) -> Path:
        """自动备份目录。"""
        return self._root / "backups"

    @property
    def log_dir(self) -> Path:
        return self._root / "logs"

    @property
    def config_path(self) -> Path:
        return self._root / "config.json"


# 全局单例, 供各层复用。
paths = AppPaths()
