"""周报生成服务: 把当周工作日志汇总成可一键复制的文本。"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.repositories.worklog_repo import WorkLogRepository
from app.utils.dates import parse_iso, week_bounds


class WeeklyReportService:
    def __init__(self, repo: WorkLogRepository | None = None) -> None:
        self._repo = repo or WorkLogRepository()

    def generate(self, ref: datetime | None = None) -> str:
        """生成当周 (ref 所在周) 的周报文本, 按天分组。"""
        start, end = week_bounds(ref)
        logs = self._repo.in_week(ref)

        title = (
            f"周报 ({start.strftime('%Y-%m-%d')} ~ "
            f"{(end).strftime('%Y-%m-%d')})"
        )
        if not logs:
            return f"{title}\n\n本周暂无工作记录。"

        by_day: dict[str, list] = defaultdict(list)
        for log in logs:
            dt = parse_iso(log.logged_at) or start
            by_day[dt.strftime("%Y-%m-%d %A")].append(log)

        lines = [title, ""]
        weekday_cn = {
            "Monday": "周一", "Tuesday": "周二", "Wednesday": "周三",
            "Thursday": "周四", "Friday": "周五", "Saturday": "周六",
            "Sunday": "周日",
        }
        for day in sorted(by_day.keys()):
            date_part, _, wd = day.partition(" ")
            lines.append(f"【{date_part} {weekday_cn.get(wd, wd)}】")
            for log in by_day[day]:
                tag = f"[{log.tag}] " if log.tag else ""
                lines.append(f"  - {tag}{log.content}")
            lines.append("")

        lines.append(f"本周共记录 {len(logs)} 项工作。")
        return "\n".join(lines).rstrip() + "\n"
