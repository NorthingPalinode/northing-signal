"""Weekly report: a Markdown digest of one date range, built only from projected events.

Pure: no HTTP, database or model calls. Nothing here is newly judged; the report reuses each
event's existing summary, reason, evidence type and source link.
"""

from datetime import timedelta

from .engine import stamp
from .models import TOPICS

ROLE_STATEMENT = {"official", "research"}
TOP_COUNT = 5


def evidence_label(event):
    """Same wording as the reader (frontend/src/reader/logic.ts `evidence`)."""
    kind, value, role = event.get("content_kind"), event.get("evidence"), event.get("source_role")
    if kind == "benchmark_snapshot":
        return "公开榜单数据"
    if kind == "index_abstract":
        return "索引摘要"
    if kind == "community_post":
        return "社区发言"
    if role == "community" and kind == "publisher_excerpt":
        return "社区线索原文"
    if kind == "publisher_excerpt" and value == "source_attributed":
        return "原文陈述"
    return {"reported_test": "文中报告测试", "opinion": "作者观点", "insufficient": "材料待补充"}.get(
        value, "原文陈述" if role in ROLE_STATEMENT else "报道转述")


def event_time(event):
    return stamp(event.get("published_at")) or stamp(event.get("captured_at"))


def report_range(kind, clock, zone=None):
    """[start, end) in the reader's timezone: the last 7 days, or last Monday–Sunday."""
    local = clock.astimezone(zone)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == "last_week":
        end = midnight - timedelta(days=local.weekday())
        return end - timedelta(days=7), end
    return midnight - timedelta(days=6), midnight + timedelta(days=1)


def _day(value):
    return f"{value.month}月{value.day}日"


def _line(event, zone):
    when = event_time(event)
    meta = " · ".join(filter(None, [
        event.get("source", "") + (f" 等 {event['source_count']} 个来源" if event.get("source_count", 1) > 1 else ""),
        _day(when.astimezone(zone)) if when else "时间未确认",
        evidence_label(event)]))
    return meta


def weekly_report(events, follows, start, end, *, generated_at, zone=None):
    """events: projected events (with actions); follows: projected follows. start/end: aware datetimes."""
    in_range = [e for e in events if e.get("qualified") and not e.get("dismissed")
                and (when := event_time(e)) and start <= when < end]
    in_range.sort(key=lambda e: event_time(e), reverse=True)
    top = sorted(in_range, key=lambda e: (not e.get("protected"), -e.get("score", 0), e["id"]))[:TOP_COUNT]
    saved = [e for e in events
             if any(a["kind"] == "saved" and (at := stamp(a.get("at"))) and start <= at < end
                    for a in e.get("actions", []))]
    last_day = end - timedelta(days=1)
    title = f"Northing Signal 周报 · {start.date().isoformat()} 至 {last_day.date().isoformat()}"
    sources = {e.get("source") for e in in_range}
    lines = [f"# {title}", ""]
    lines.append(f"> 共 {len(in_range)} 项有依据的进展，来自 {len(sources)} 个来源。"
                 f"本机生成于 {generated_at.astimezone(zone).strftime('%Y-%m-%d %H:%M')}。")
    lines.append("> 依据类型标明来源陈述、文中报告的测试与作者观点；均不等于本项目独立验证。")
    lines.append("")
    if not in_range:
        lines += ["这段时间没有整理好的进展。", ""]
    else:
        lines += [f"## 本周最重要的 {len(top)} 件事", ""]
        for index, event in enumerate(top, 1):
            lines.append(f"{index}. **{event['title']}**")
            if event.get("reason"):
                lines.append(f"   {event['reason']}")
            lines.append(f"   （{_line(event, zone)}）[原文]({event['url']})")
        lines.append("")
        lines += ["## 按方向", ""]
        for topic, label in TOPICS.items():
            group = [e for e in in_range if e.get("topic") == topic]
            if not group:
                continue
            lines += [f"### {label}（{len(group)}）", ""]
            for event in group:
                lines.append(f"- **{event['title']}**（{_line(event, zone)}）[原文]({event['url']})")
                if event.get("summary"):
                    lines.append(f"  {event['summary']}")
            lines.append("")
    if saved:
        lines += ["## 本周收藏", ""]
        lines += [f"- [{e['title']}]({e['url']})（{_line(e, zone)}）" for e in saved]
        lines.append("")
    ids = {e["id"] for e in in_range}
    tracked = [(f["name"], sum(i in ids for i in f.get("event_ids", []))) for f in follows]
    tracked = [(name, count) for name, count in tracked if count]
    if tracked:
        lines += ["## 话题追踪", ""]
        lines += [f"- {name}：{count} 项相关进展" for name, count in tracked]
        lines.append("")
    filename = f"northing-signal-weekly-{start.date().isoformat()}.md"
    return {"title": title, "filename": filename, "markdown": "\n".join(lines).rstrip() + "\n",
            "count": len(in_range), "start": start.isoformat(), "end": end.isoformat()}
