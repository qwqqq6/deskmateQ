"""应用配置: 以 JSON 持久化用户偏好与运行参数。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from app.core.paths import paths


@dataclass
class Config:
    """用户可配置项。新增字段需保持向后兼容 (提供默认值)。"""

    # 窗口几何, None 表示首次启动时居中
    window_x: int | None = None
    window_y: int | None = None
    window_width: int = 440
    window_height: int = 660

    # 是否开机自启
    autostart: bool = False
    # 窗口是否置顶
    always_on_top: bool = True
    # 窗口透明度 0.4 - 1.0
    opacity: float = 1.0

    # 自动备份间隔 (分钟), 0 表示关闭
    backup_interval_min: int = 60
    # 最多保留的备份数量
    backup_keep: int = 20
    # 自定义备份目录 (None 表示用默认 %LOCALAPPDATA%\DeskMate\backups)
    backup_dir: str | None = None

    # 当前激活的面板
    active_panel: str = "todo"

    # 主题色 (强调色)
    accent: str = "#6C8EF5"
    # 主题模式: dark / light / system
    theme_mode: str = "dark"

    # 贴边隐藏: 开启后窗口吸附到屏幕边缘, 鼠标离开自动收起, 移到边缘自动弹出
    edge_dock: bool = False
    # 贴边后是否自动隐藏 (收起); 关闭则只吸附常驻不收起
    edge_auto_hide: bool = True

    _path: Path = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or paths.config_path
        cfg = cls()
        cfg._path = path
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                known = {f.name for f in fields(cls) if not f.name.startswith("_")}
                for k, v in raw.items():
                    if k in known:
                        setattr(cfg, k, v)
            except (json.JSONDecodeError, OSError):
                # 配置损坏时回退到默认值, 不阻断启动
                pass
        return cfg

    def save(self) -> None:
        if self._path is None:
            self._path = paths.config_path
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
