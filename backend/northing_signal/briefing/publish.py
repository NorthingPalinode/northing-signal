"""Public digest: a static, non-personal edition of the briefing as HTML pages and an RSS feed.

Built from a neutral projection (default preferences, no reader actions), so saved items,
feedback, follows and reading history never reach a public page. Nothing is newly judged:
each entry reuses the event's existing title, summary, reason, evidence type and source links.
Original excerpts and quotes are not published; readers follow the source links.

Output directory layout (self-contained, suitable for GitHub Pages or any static host):
    index.html              latest edition plus links to earlier ones
    feed.xml                RSS 2.0, one item per edition
    editions/<id>.json      the edition data (the record later pages are rebuilt from)
    editions/<id>.html      the edition page
"""

import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from .engine import stamp
from .models import TOPICS
from .report import event_time, evidence_label

SITE_TITLE = "Northing Signal 日报"
TAGLINE = "AI 发布、测试与更正，每天两次。每条附原始出处与依据类型。"
DISCLAIMER = ("摘要由 AI 依据当时取得的原文节选整理，可能有误，请以原文为准。"
              "依据类型区分来源陈述、文中报告的测试与作者观点，均不等于本项目独立验证。")
FIRST_WINDOW = timedelta(hours=48)  # the first edition looks back this far
MAX_AGE_DAYS = 7                    # older stories newly collected are not "news" (corrections excepted)
# Editorial rules adapted from AIHOT's daily report, no model calls. 15 items in all (the owner's
# edition size, 2026-11-23): a main list with a headline and highlights, then one-line quick items.
MAIN_LIMIT, QUICK_LIMIT = 10, 5
EDITION_LIMIT = MAIN_LIMIT + QUICK_LIMIT
HIGHLIGHTS = 3          # after the headline
SOURCE_CAP = 2          # one outlet at most this often in the main list
REPEAT_EDITIONS = 7     # stories featured this recently return to the main list only on real news
FOLLOWUP_SOURCES = 4    # ... meaning: this many outlets, or the party itself acting again
PARTY_ACTIONS = {"release", "update", "test", "correction", "withdrawal"}
TOP_COUNT = 1 + HIGHLIGHTS
ARCHIVE_LINKS = 30
FEED_ITEMS = 30


def safe_url(value):
    value = (value or "").strip()
    return value if urlsplit(value).scheme in {"http", "https"} else ""


def compose(events, since, clock, recent_ids=frozenset()):
    """[(event, section, follow-up)] for one edition, main list first.

    A story featured in the last editions goes back into the main list only when its own party
    acts again (an official report of a release, update, test or correction since `since`) or
    FOLLOWUP_SOURCES outlets carry it; otherwise it is a quick item. Rank: the neutral score,
    heat and an official original, follow-ups lower. One outlet at most SOURCE_CAP main items.
    """
    ranked = []
    for event in public_events(events, since, clock):
        fresh = [t for t in event.get("timeline", [])
                 if (captured := stamp(t.get("captured_at"))) and since < captured <= clock]
        repeat = event["id"] in recent_ids
        strong = (event.get("protected") or event.get("source_count", 1) >= FOLLOWUP_SOURCES
                  or any(t.get("role") == "official" and t.get("action") in PARTY_ACTIONS for t in fresh))
        official = any(t.get("role") == "official" for t in event.get("timeline", []))
        weight = event.get("score", 0) + 2 * event.get("heat", 0) + (2 if official else 0) - (3 if repeat else 0)
        ranked.append((weight, event, repeat, strong))
    ranked.sort(key=lambda r: (not r[1].get("protected"), -r[0], r[1]["id"]))
    main, quick, per_source = [], [], {}
    for _, event, repeat, strong in ranked:
        source = event.get("source", "")
        if len(main) < MAIN_LIMIT and (strong or not repeat) and per_source.get(source, 0) < SOURCE_CAP:
            main.append((event, "main", repeat))
            per_source[source] = per_source.get(source, 0) + 1
        elif len(quick) < QUICK_LIMIT:
            quick.append((event, "quick", repeat))
    return main + quick


def public_events(events, since, clock):
    """Qualified events that got a report in (since, clock], recently published, best first."""
    chosen = []
    for event in events:
        latest = stamp(event.get("latest_captured_at") or event.get("captured_at"))
        if not event.get("qualified") or not latest or not since < latest <= clock:
            continue
        if not event.get("timely", True) and not event.get("protected"):
            continue  # found late or undated: archived, not news
        when = stamp(event.get("published_at")) or stamp(event.get("earliest_published_at")) or event_time(event)
        if when and clock - when > timedelta(days=MAX_AGE_DAYS) and not event.get("protected"):
            continue
        chosen.append(event)
    chosen.sort(key=lambda e: (not e.get("protected"), -e.get("score", 0), e["id"]))
    return chosen


def public_entry(event, since, section="main", followup=False):
    """Only the fields a public page shows; no reader state, excerpts or quotes."""
    first = stamp(event.get("first_captured_at"))
    sources, seen = [], set()
    for row in reversed(event.get("timeline", [])):
        url = safe_url(row.get("url"))
        if url and url not in seen:
            seen.add(url)
            sources.append({"source": row.get("source", ""), "url": url,
                            "published_at": row.get("published_at")})
    when = event_time(event)
    return {
        "id": event["id"], "version": event["version"], "title": event["title"],
        "summary": event.get("summary", ""), "reason": event.get("reason", ""),
        "topic": event.get("topic"), "topic_label": event.get("topic_label") or TOPICS.get(event.get("topic"), ""),
        "evidence": evidence_label(event), "source": event.get("source", ""), "url": safe_url(event.get("url")),
        "published_at": when.isoformat() if when else None,
        "source_count": event.get("source_count", 1),
        "status": "correction" if event.get("action") in {"correction", "withdrawal"}
        else "followup" if followup else "updated" if first and first <= since else "new",
        "section": section, "heat": event.get("heat", 0),
        "limitations": list(event.get("limitations", []))[:3], "sources": sources[:6],
    }


def load_editions(out_dir):
    editions = []
    for path in (out_dir / "editions").glob("*.json"):
        try:
            editions.append(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError):
            continue
    editions.sort(key=lambda e: e["generated_at"])
    return editions


def make_edition(events, earlier, clock, zone=None):
    """earlier: the editions already published, oldest first."""
    previous = earlier[-1] if earlier else None
    since = stamp(previous["generated_at"]) if previous else clock - FIRST_WINDOW
    recent_ids = {e["id"] for edition in earlier[-REPEAT_EDITIONS:] for e in edition["events"]}
    entries = [public_entry(event, since, section, followup)
               for event, section, followup in compose(events, since, clock, recent_ids)]
    return {"id": clock.astimezone(zone).strftime("%Y-%m-%d-%H%M"), "generated_at": clock.isoformat(),
            "since": since.isoformat(), "events": entries,
            "counts": {"events": len(entries), "sources": len({e["source"] for e in entries})}}


def publish(events, out_dir, *, clock=None, zone=None, base_url=""):
    """Write a new edition when there is news since the last one, then rebuild index and feed.

    Returns {"edition": id or None, "count": n, "path": index path}.
    """
    clock = clock or datetime.now(timezone.utc)
    out_dir = Path(out_dir)
    (out_dir / "editions").mkdir(parents=True, exist_ok=True)
    editions = load_editions(out_dir)
    edition = make_edition(events, editions, clock, zone)
    if edition["events"]:
        (out_dir / "editions" / f"{edition['id']}.json").write_text(
            json.dumps(edition, ensure_ascii=False, indent=1), "utf-8")
        editions = [e for e in editions if e["id"] != edition["id"]] + [edition]
    base = safe_url(base_url)
    base = base if not base or base.endswith("/") else base + "/"
    for item in editions:
        (out_dir / "editions" / f"{item['id']}.html").write_text(
            render_page(item, editions, zone, prefix="../"), "utf-8")
    latest = editions[-1] if editions else None
    (out_dir / "index.html").write_text(render_page(latest, editions, zone, prefix=""), "utf-8")
    (out_dir / "feed.xml").write_text(render_feed(editions, zone, base), "utf-8")
    (out_dir / ".nojekyll").write_text("", "utf-8")
    return {"edition": edition["id"] if edition["events"] else None, "count": len(edition["events"]),
            "path": str(out_dir / "index.html")}


# ---- rendering ---------------------------------------------------------------------------------

def _local(value, zone):
    when = stamp(value) if isinstance(value, str) else value
    return when.astimezone(zone) if when else None


def _edition_name(edition, zone):
    local = _local(edition["generated_at"], zone)
    return f"{local.year}年{local.month}月{local.day}日 {local:%H:%M} 版"


def _offset(edition, zone):
    text = _local(edition["generated_at"], zone).strftime("%z")
    return f"UTC{text[:3]}:{text[3:]}" if text else "UTC"


def _date(value, zone):
    local = _local(value, zone)
    return f"{local.month}月{local.day}日" if local else "时间未确认"


BADGES = {"new": ("新", "new"), "updated": ("有更新", "updated"), "followup": ("跟进", "updated"),
          "correction": ("更正", "correction")}


def _meta(entry, zone):
    source = escape(entry["source"]) + (f" 等 {entry['source_count']} 个来源" if entry["source_count"] > 1 else "")
    return " · ".join([source, _date(entry["published_at"], zone), escape(entry["evidence"]),
                       escape(entry["topic_label"])])


def _article(entry, zone, rank=None):
    badge_text, badge_class = BADGES.get(entry["status"], BADGES["new"])
    title = escape(entry["title"])
    heading = f'<a href="{escape(entry["url"])}" rel="noopener">{title}</a>' if entry["url"] else title
    parts = [f'<article id="e-{escape(entry["id"])}" class="story">',
             f'<h3>{f"<span class=rank>{rank}</span>" if rank else ""}{heading}'
             f' <span class="badge {badge_class}">{badge_text}</span></h3>',
             f'<p class="meta">{_meta(entry, zone)}</p>']
    if entry["summary"]:
        parts.append(f'<p>{escape(entry["summary"])}</p>')
    if entry["reason"]:
        parts.append(f'<p class="reason"><b>为什么值得读</b>{escape(entry["reason"])}</p>')
    details = []
    if entry["limitations"]:
        details.append("<p><b>边界</b></p><ul>" + "".join(f"<li>{escape(x)}</li>" for x in entry["limitations"]) + "</ul>")
    if entry["sources"]:
        details.append("<p><b>报道来源</b></p><ul>" + "".join(
            f'<li><a href="{escape(s["url"])}" rel="noopener">{escape(s["source"] or s["url"])}</a>'
            f' <span class="muted">{_date(s["published_at"], zone)}</span></li>' for s in entry["sources"]) + "</ul>")
    if details:
        parts.append(f'<details><summary>依据与来源</summary>{"".join(details)}</details>')
    parts.append("</article>")
    return "".join(parts)


STYLE = """
:root{--bg:#fbfaf7;--fg:#1d1c1a;--muted:#6b6860;--line:#e4e0d6;--card:#fff;--accent:#2f5d50;
--new:#2f5d50;--upd:#7a5a12;--cor:#9b2c2c}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--muted:#a29f96;--line:#2c2b28;
--card:#1c1b19;--accent:#8cc5b2;--new:#8cc5b2;--upd:#e0b85c;--cor:#ef8a8a;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 16px 64px}a{color:inherit;text-decoration-color:var(--line);
text-underline-offset:3px}a:hover{color:var(--accent);text-decoration-color:currentColor}
header h1{margin:0;font-size:28px;letter-spacing:.02em}header p{margin:4px 0;color:var(--muted)}
.edition{display:flex;flex-wrap:wrap;gap:8px 16px;margin-top:12px;font-size:14px;color:var(--muted)}
h2{margin:40px 0 12px;font-size:15px;letter-spacing:.08em;color:var(--muted);font-weight:600;
border-bottom:1px solid var(--line);padding-bottom:8px}
.story{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:12px 0}
.story h3{margin:0;font-size:18px;line-height:1.5}.story p{margin:8px 0}
.rank{display:inline-block;min-width:1.6em;color:var(--accent);font-variant-numeric:tabular-nums}
.meta,.muted{color:var(--muted);font-size:13px}.reason{font-size:15px}.reason b{margin-right:8px;font-size:13px;
color:var(--muted)}.badge{font-size:12px;font-weight:500;border:1px solid currentColor;border-radius:999px;
padding:0 8px;vertical-align:2px;white-space:nowrap}.badge.new{color:var(--new)}.badge.updated{color:var(--upd)}
.badge.correction{color:var(--cor)}details{margin-top:8px;font-size:14px}summary{cursor:pointer;color:var(--muted)}
details ul{margin:4px 0 8px;padding-left:20px}details p{margin:8px 0 0}
.empty{color:var(--muted);padding:32px 0}footer{margin-top:48px;font-size:13px;color:var(--muted)}
footer ul{padding-left:20px}
.quick{list-style:none;padding:0;margin:0}.quick li{padding:10px 0;border-bottom:1px solid var(--line)}
.quick li:last-child{border-bottom:0}
"""


def _quick(entry, zone):
    badge = '<span class="badge updated">跟进</span> ' if entry["status"] == "followup" else ""
    title = escape(entry["title"])
    link = f'<a href="{escape(entry["url"])}" rel="noopener">{title}</a>' if entry["url"] else title
    return f'<li>{badge}{link} <span class="muted">{_meta(entry, zone)}</span></li>'


def render_page(edition, editions, zone, *, prefix):
    title = SITE_TITLE if not edition else f"{SITE_TITLE} · {_edition_name(edition, zone)}"
    body = [f'<header><h1><a href="{prefix}index.html">{SITE_TITLE}</a></h1><p>{TAGLINE}</p>']
    if edition:
        body.append(f'<div class="edition"><span>{_edition_name(edition, zone)}（{_offset(edition, zone)}）</span>'
                    f'<span>{edition["counts"]["events"]} 项进展 · {edition["counts"]["sources"]} 个来源</span>'
                    f'<a href="{prefix}feed.xml">RSS 订阅</a></div>')
    body.append("</header>")
    entries = edition["events"] if edition else []
    if not entries:
        body.append('<p class="empty">还没有发布内容。</p>')
    else:
        # Editions before the editorial rules have no section: all of them are the main list.
        main = [e for e in entries if e.get("section", "main") == "main"]
        quick = [e for e in entries if e.get("section") == "quick"]
        if main:
            body.append("<h2>头条</h2>")
            body.append(_article(main[0], zone, rank=1))
        if main[1:TOP_COUNT]:
            body.append("<h2>今日看点</h2>")
            body += [_article(e, zone, rank=i) for i, e in enumerate(main[1:TOP_COUNT], 2)]
        rest = main[TOP_COUNT:]
        for topic, label in TOPICS.items():
            group = [e for e in rest if e["topic"] == topic]
            if group:
                body.append(f"<h2>{escape(label)}（{len(group)}）</h2>")
                body += [_article(e, zone) for e in group]
        if quick:
            body.append(f"<h2>快讯（{len(quick)}）</h2><ul class=\"quick\">")
            body += [_quick(e, zone) for e in quick]
            body.append("</ul>")
    others = [e for e in reversed(editions) if not edition or e["id"] != edition["id"]][:ARCHIVE_LINKS]
    footer = [f"<footer><p>{DISCLAIMER}</p>"]
    if others:
        footer.append("<p>往期</p><ul>" + "".join(
            f'<li><a href="{prefix}editions/{escape(e["id"])}.html">{_edition_name(e, zone)}</a>'
            f'（{e["counts"]["events"]} 项）</li>' for e in others) + "</ul>")
    footer.append("<p>由 Northing Signal 生成。</p></footer>")
    return ("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{escape(title)}</title><meta name=\"description\" content=\"{escape(TAGLINE)}\">"
            f"<link rel=\"alternate\" type=\"application/rss+xml\" title=\"{SITE_TITLE}\" href=\"{prefix}feed.xml\">"
            f"<style>{STYLE}</style></head><body><main>{''.join(body)}{''.join(footer)}</main></body></html>\n")


def render_feed(editions, zone, base):
    items = []
    for edition in reversed(editions[-FEED_ITEMS:]):
        link = f"{base}editions/{edition['id']}.html"
        lines = "".join(
            f'<li><a href="{escape(e["url"] or link)}">{escape(e["title"])}</a>'
            f'<br>{escape(e["summary"])}<br><small>{_meta(e, zone)}</small></li>' for e in edition["events"])
        description = f"<ol>{lines}</ol><p><small>{escape(DISCLAIMER)}</small></p>"
        top = "；".join(e["title"] for e in edition["events"][:TOP_COUNT])
        items.append(
            "<item>"
            f"<title>{escape(_edition_name(edition, zone))} · {edition['counts']['events']} 项进展</title>"
            f"<link>{escape(link)}</link><guid isPermaLink=\"false\">northing-signal-{escape(edition['id'])}</guid>"
            f"<pubDate>{format_datetime(stamp(edition['generated_at']))}</pubDate>"
            f"<description>{escape(description)}</description>"
            f"<category>{escape(top)}</category>"
            "</item>")
    self_link = f'<atom:link href="{escape(base)}feed.xml" rel="self" type="application/rss+xml"/>' if base else ""
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
            f"<title>{SITE_TITLE}</title><link>{escape(base or 'index.html')}</link>"
            f"<description>{escape(TAGLINE)}</description><language>zh-CN</language>{self_link}"
            f"{''.join(items)}</channel></rss>\n")
