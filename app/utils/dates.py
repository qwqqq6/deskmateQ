"""时间处理工具: 统一使用本地时间的 ISO8601 字符串存储。"""
from __future__ import annotations

from datetime import datetime, timedelta


def now_iso() -> str:
    """当前本地时间, 秒级 ISO8601。"""
    return datetime.now().replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def week_bounds(ref: datetime | None = None) -> tuple[datetime, datetime]:
    """返回 ref 所在自然周 (周一 00:00 至下周一 00:00) 的左闭右开区间。"""
    ref = ref or datetime.now()
    start = (ref - timedelta(days=ref.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, start + timedelta(days=7)


def fmt_human(value: str | None, with_time: bool = True) -> str:
    dt = parse_iso(value)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")
