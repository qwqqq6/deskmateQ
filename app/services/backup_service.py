"""备份与恢复服务。

策略: 将整个 DeskMate 数据目录 (数据库 + 附件) 打包成时间戳命名的
zip 存到 backups 目录。支持自动按间隔备份、保留上限轮转、从任意
备份恢复。恢复前会对当前数据做一次安全快照。
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.core.database import db
from app.core.paths import paths


@dataclass
class BackupInfo:
    path: Path
    name: str
    created_at: datetime
    size: int

    @property
    def size_kb(self) -> float:
        return self.size / 1024.0


class BackupService:
    """负责数据备份/恢复。无 UI 依赖, 可被定时器或菜单调用。

    备份目录优先取配置中的自定义路径 (backup_dir), 未设置时回退到
    默认的 %LOCALAPPDATA%\\DeskMate\\backups。
    """

    PREFIX = "deskmate_backup_"

    def __init__(self, backup_dir: Path | str | None = None) -> None:
        self._backup_dir = self._resolve_dir(backup_dir)

    @staticmethod
    def _resolve_dir(backup_dir: Path | str | None) -> Path:
        if backup_dir is None:
            from app.core.config import Config

            cfg = Config.load()
            backup_dir = cfg.backup_dir
        if backup_dir:
            d = Path(backup_dir)
        else:
            d = paths.backup_dir
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def backup_dir(self) -> Path:
        return self._backup_dir

    # --- 备份 --------------------------------------------------------
    def create_backup(self, label: str = "") -> BackupInfo:
        """生成一个 zip 备份。label 仅用于文件名可读性。"""
        # 确保 WAL 落盘, 备份得到完整数据库
        db.checkpoint()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(c for c in label if c.isalnum() or c in "-_")
        name = f"{self.PREFIX}{ts}{('_' + safe_label) if safe_label else ''}.zip"
        dest = self._backup_dir / name

        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            # 数据库文件
            if paths.db_path.exists():
                zf.write(paths.db_path, arcname=f"data/{paths.db_path.name}")
            # 附件 (递归, 保留按报销项分的子目录结构)
            att_root = paths.attachments_dir
            for f in att_root.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(att_root).as_posix()
                    zf.write(f, arcname=f"attachments/{rel}")
            # 配置
            if paths.config_path.exists():
                zf.write(paths.config_path, arcname="config.json")

        self._rotate()
        return self._to_info(dest)

    # 超过该天数的备份视为"旧备份", 旧备份只保留一份
    OLD_AFTER_DAYS = 7

    def _rotate(self, keep: int | None = None) -> None:
        from app.core.config import Config

        keep = keep if keep is not None else Config.load().backup_keep
        backups = self.list_backups()  # 已按时间倒序
        now = datetime.now()
        cutoff = now - timedelta(days=self.OLD_AFTER_DAYS)

        recent = [b for b in backups if b.created_at >= cutoff]
        old = [b for b in backups if b.created_at < cutoff]

        to_delete: list[BackupInfo] = []
        # 近 7 天内的备份: 按数量上限轮转, 删除超出的较旧者
        if keep > 0:
            to_delete.extend(recent[keep:])
        # 7 天前的旧备份: 只保留最新一份, 其余删除
        if old:
            to_delete.extend(old[1:])

        for b in to_delete:
            try:
                b.path.unlink(missing_ok=True)
            except OSError:
                pass

    def list_backups(self) -> list[BackupInfo]:
        items = [
            self._to_info(p)
            for p in self._backup_dir.glob(f"{self.PREFIX}*.zip")
            if p.is_file()
        ]
        items.sort(key=lambda b: b.created_at, reverse=True)
        return items

    # --- 恢复 --------------------------------------------------------
    def restore(self, backup_path: str | Path) -> None:
        """从备份恢复。会先对当前数据做安全快照, 再覆盖。

        恢复后需要重启数据库连接, 调用方 (UI) 负责提示重启应用。
        """
        backup_path = Path(backup_path)
        if not backup_path.exists():
            raise FileNotFoundError(backup_path)

        # 安全快照, 防止误操作
        self.create_backup(label="prerestore")

        # 关闭连接后再覆盖文件
        db.checkpoint()

        with zipfile.ZipFile(backup_path, "r") as zf:
            names = zf.namelist()
            # 清空现有附件 (含子目录), 避免残留
            for f in sorted(paths.attachments_dir.rglob("*"), reverse=True):
                try:
                    if f.is_file():
                        f.unlink(missing_ok=True)
                    elif f.is_dir():
                        f.rmdir()
                except OSError:
                    pass
            for member in names:
                target = self._resolve_member(member)
                if target is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as out:
                    out.write(src.read())

    @staticmethod
    def _resolve_member(member: str) -> Path | None:
        """将 zip 内路径映射到真实目标, 防止路径穿越。"""
        if member.endswith("/"):
            return None
        if member.startswith("data/"):
            return paths.data_dir / Path(member).name
        if member.startswith("attachments/"):
            rel = member[len("attachments/"):]
            return BackupService._safe_under(paths.attachments_dir, rel)
        if member == "config.json":
            return paths.config_path
        return None

    @staticmethod
    def _safe_under(base: Path, rel: str) -> Path | None:
        """把相对路径 rel 解析到 base 下, 拒绝越界路径。"""
        target = (base / rel).resolve()
        try:
            target.relative_to(base.resolve())
        except ValueError:
            return None
        return target

    @staticmethod
    def _to_info(p: Path) -> BackupInfo:
        stat = p.stat()
        return BackupInfo(
            path=p,
            name=p.name,
            created_at=datetime.fromtimestamp(stat.st_mtime),
            size=stat.st_size,
        )
