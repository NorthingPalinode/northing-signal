"""Public publisher indexes and structured catalogs; listings remain discovery leads."""

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin, urlsplit

from lxml import etree, html

from .models import Material, digest, public_url


def material(source, title, url, body="", *, kind="search_excerpt", date=None, identity=None,
             discovery_url=None):
    return Material(id=digest([source["id"], identity or url])[:24], source_id=source["id"],
                    source_name=source["name"], source_role=source["role"], title=title[:600],
                    url=url, text=body[:16000], content_kind=kind, published_at=date,
                    discovery_url=discovery_url)


def clean(value):
    return " ".join(str(value or "").split())


def page_tree(body):
    tree = html.fromstring(body.decode("utf-8", errors="replace"))
    for element in tree.xpath("//script|//style|//nav"):
        element.drop_tree()
    return tree


def published_date(value):
    value = clean(value)
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).isoformat()
    except ValueError:
        pass
    iso = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", value)
    if iso:
        try:
            return datetime(*(int(p) for p in iso.groups()), tzinfo=timezone.utc).isoformat()
        except ValueError:
            return None
    english = re.search(r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),?\s+(20\d{2})", value, re.I)
    if english:
        try:
            month = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(english[1][:3].lower()) + 1
            return datetime(int(english[3]), month, int(english[2]), tzinfo=timezone.utc).isoformat()
        except ValueError:
            return None
    return None


def article_date(body):
    tree = html.fromstring(body.decode("utf-8", errors="replace"))
    values = tree.xpath('//meta[@property="article:published_time" or @itemprop="datePublished"]/@content')
    return next((date for value in values if (date := published_date(value))), None)


def publisher_links(source, body, limit):
    """Never turn index headings, navigation or synthetic snippets into article evidence."""
    tree = page_tree(body)
    output = {}
    roots = tree.xpath("//main") or [tree]
    for link in roots[0].xpath(".//a[@href]"):
        try:
            url = public_url(urljoin(source["url"], link.get("href")))
            parsed = urlsplit(url)
            if parsed.hostname not in source["article_hosts"] or not re.search(source["path_pattern"], parsed.path):
                continue
            context = clean(link.text_content())
            headings = link.xpath(".//h1|.//h2|.//h3|.//h4")
            title = clean(headings[0].text_content()) if headings else context
            if title.lower() in {"learn more", "read more", "了解更多", "阅读更多"}:
                parent = link.getparent()
                headings = parent.xpath(".//h2|.//h3|.//h4") if parent is not None else []
                title = clean(headings[0].text_content()) if headings else ""
            if len(title) < 8 or title.lower() in {"all news", "all articles", "latest news", "featured"}:
                continue
            dates = link.xpath(".//time/@datetime")
            date = published_date(" ".join(dates) or context)
            for parent in list(link.iterancestors())[:3]:
                if date:
                    break
                articles = {urljoin(source["url"], href) for href in parent.xpath(".//a/@href")
                            if re.search(source["path_pattern"], urlsplit(urljoin(source["url"], href)).path)}
                if articles != {url}:
                    break
                date = published_date(parent.text_content())
            value = material(source, title, url, date=date, discovery_url=source["url"])
            if url not in output or (date and not output[url].published_at):
                output[url] = value
        except (ValueError, TypeError):
            continue
    return sorted(output.values(), key=lambda m: m.published_at or "", reverse=True)[:limit]


DATE = re.compile(r"(?<!\d)(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?!\d)")  # text may follow at once


def dated(value):
    """(normalised YYYY-MM-DD, ISO timestamp) of the first date in `value`, or None."""
    match = DATE.search(value or "")
    if not match:
        return None
    try:
        day = datetime(*(int(p) for p in match.groups()), tzinfo=timezone.utc)
    except ValueError:
        return None
    return day.strftime("%Y-%m-%d"), day.isoformat()


def day_materials(source, days, limit):
    """One material per day, newest page order kept; sections of the same day are joined."""
    joined = {}
    for key, date, excerpt in days:
        if key in joined:
            joined[key] = (date, joined[key][1] + "\n" + excerpt)
        else:
            joined[key] = (date, excerpt)
    output = []
    for key, (date, excerpt) in joined.items():
        excerpt = excerpt[:6000]
        if len(excerpt) < 100:
            continue
        output.append(material(source, source["name"] + " · " + key, source["url"], excerpt,
                               kind="publisher_excerpt", date=date, identity=key, discovery_url=source["url"]))
        if len(output) >= limit:
            break
    return output


def changelog(source, body, limit):
    """Sections headed by a date. `heading` (default h2) names the dated heading level; a
    section runs to the next heading of that level or above."""
    tree = page_tree(body)
    level = source.get("heading", "h2")
    stops = {f"h{n}" for n in range(1, int(level[1]) + 1)}
    days = []
    for heading in tree.xpath("//" + level):
        found = dated(heading.text_content())
        if not found:
            continue
        sections = [clean(heading.text_content())]
        next_node = heading.getnext()
        while next_node is not None and next_node.tag not in stops:
            sections.append(clean(next_node.text_content()))
            next_node = next_node.getnext()
        days.append((*found, "\n".join(s for s in sections if s)))
    return day_materials(source, days, limit)


def updates(source, body, limit):
    """Documentation changelogs built from one block per release: Mintlify `<div class="update"
    id="2026-08-26">` (Zhipu / Z.ai), Alibaba Cloud `<div class="rkb-update">` with the date at
    its start. `block` names the block's class (default "update"); dated by its id, else by
    the first date in its opening text."""
    tree = page_tree(body)
    name = source.get("block", "update")
    days = []
    for block in tree.xpath(f"//div[contains(concat(' ', normalize-space(@class), ' '), ' {name} ')]"):
        text = clean(block.text_content())
        found = dated(block.get("id")) or dated(text[:40])
        if found:
            days.append((*found, text))
    return day_materials(source, days, limit)


def document(source, body, limit):
    import trafilatura
    excerpt = trafilatura.extract(body.decode("utf-8", errors="replace"),
                                  include_comments=False, include_tables=True) or ""
    if len(excerpt.strip()) < 100 or not limit:
        return []
    return [material(source, source["name"], source["url"], excerpt[:6000], kind="publisher_excerpt")]


def markdown(source, body, limit):
    content = body.decode("utf-8", errors="replace").strip()
    dated = list(re.finditer(r"(?m)^#{1,4}\s+(20\d{2}-\d{2}-\d{2})\s*$", content))
    date = published_date(dated[0][1]) if dated else None
    excerpt = content[dated[0].start():dated[1].start() if len(dated) > 1 else len(content)] if dated else content
    excerpt = excerpt[:6000]
    if len(excerpt) < 100 or not limit:
        return []
    title = source["name"] + (" · " + dated[0][1] if dated else "")
    return [material(source, title, source.get("original_url", source["url"]), excerpt,
                     kind="publisher_excerpt", date=date, discovery_url=source["url"])]


def arena(source, body, limit):
    data = json.loads(body)
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise ValueError("invalid_arena_rows")
    rows = [r["row"] for r in data["rows"] if isinstance(r.get("row"), dict)
            and r["row"].get("category") == "overall"]
    if not rows or not limit:
        return []
    # Keep original fields, including dates, votes and confidence bounds. This
    # is a bounded dataset excerpt, not an independently rerun experiment.
    excerpt = json.dumps(rows[:12], ensure_ascii=False, indent=2)
    if len(excerpt) > 15000:
        raise ValueError("benchmark_excerpt_too_large")
    dates = {r.get("leaderboard_publish_date") for r in rows}
    date = published_date(next(iter(dates))) if len(dates) == 1 and None not in dates else None
    return [material(source, source["name"] + " · 公开数据节选", source["original_url"], excerpt,
                     kind="benchmark_snapshot", date=date, discovery_url=source["url"])]


def swebench(source, body, limit):
    data = json.loads(body)
    boards = data.get("leaderboards") if isinstance(data, dict) else None
    if not isinstance(boards, list):
        raise ValueError("invalid_swebench_boards")
    board = next((b for b in boards if b.get("name") == "Verified"), None)
    if not board or not limit:
        return []
    fields = {"name", "agent", "agent_org", "model_display", "model_org", "resolved", "date",
              "checked", "tags", "warning", "cost", "reasoning_effort", "site", "folder"}
    rows = sorted(board.get("results", []), key=lambda r: r.get("date") or "", reverse=True)[:8]
    excerpt = json.dumps({"name": board["name"], "results": [{k:v for k,v in row.items() if k in fields} for row in rows]}, ensure_ascii=False, indent=2)
    if not rows or len(excerpt) > 15000:
        return []
    # Submission dates belong to each result. There is no inferred publication
    # date for this changing whole-board excerpt, and checked=false stays visible.
    return [material(source, source["name"] + " · 提交结果节选", source["original_url"], excerpt,
                     kind="benchmark_snapshot", discovery_url=source["url"])]


def paper_id(value):
    return value if isinstance(value, str) and re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", value) else None


def daily_papers(source, body, limit):
    data = json.loads(body)
    if not isinstance(data, list):
        raise ValueError("invalid_paper_list")
    output = []
    for entry in data[:limit]:
        row = entry.get("paper") or {}
        key = paper_id(row.get("id"))
        if key and row.get("title"):
            abstract = clean(row.get("summary"))
            output.append(material(source, row["title"], "https://arxiv.org/abs/" + key, abstract,
                                   kind="index_abstract" if abstract else "catalog_metadata",
                                   date=row.get("publishedAt"), discovery_url="https://huggingface.co/papers/" + key))
    return output


def openreview(source, body, limit):
    data = json.loads(body)
    if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
        raise ValueError("invalid_review_list")
    output = []
    for row in data["notes"][:limit]:
        # A public endpoint response is not a grant to consume a non-public note.
        if row.get("readers") != ["everyone"]:
            continue
        key = row.get("forum") or row.get("id")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            continue
        content = row.get("content") or {}
        def field(name):
            value = content.get(name, "")
            return value.get("value", "") if isinstance(value, dict) else value
        title, abstract = clean(field("title")), clean(field("abstract"))
        if title:
            # OpenReview note creation time is not necessarily paper publication time.
            output.append(material(source, title, "https://openreview.net/forum?id=" + key, abstract,
                                   kind="index_abstract" if abstract else "catalog_metadata"))
    return output


def modelscope_models(source, body, limit):
    data = json.loads(body)
    if not isinstance(data, dict) or data.get("success") is not True:
        raise ValueError("invalid_modelscope_catalog")
    payload = data.get("data")
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("invalid_modelscope_catalog")
    output = []
    for row in rows[:limit]:
        name = row.get("id", "")
        if (row.get("private") or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name)
                or name.split("/")[0].casefold() != source["organization"].casefold()):
            continue
        metadata = json.dumps({k:v for k,v in row.items() if k in {"id", "display_name", "description", "license", "tasks", "tags", "gated"}},ensure_ascii=False)
        # Repository creation time: the model was public then or later, never earlier.
        created = published_date(row.get("created_at")) if row.get("created_at") else None
        output.append(material(source,name,"https://modelscope.cn/models/"+name,metadata,kind="catalog_metadata",
                               date=created))
    return output


async def hub_models(source, body, limit, fetch):
    data = json.loads(body)
    if not isinstance(data, list):
        raise ValueError("invalid_model_list")
    output = []
    for row in data[:limit]:
        name = row.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name) or name.split("/")[0].casefold() != source["organization"].casefold():
            continue
        info = row.get("cardData") if isinstance(row.get("cardData"), dict) else {}
        license_id = info.get("license")
        if not isinstance(license_id, str):
            license_id = next((t[8:] for t in row.get("tags", []) if isinstance(t, str) and t.startswith("license:")), None)
        excerpt = (f"模型仓库：{name}；声明许可：{license_id or '未说明'}。"
                   "日期为仓库创建时间；仓库更新时间不作为模型发布日期。")
        # The list is sorted by last modification, so an old model whose card was just edited
        # comes first. Its repository creation time keeps it from passing as a new release.
        created = published_date(row.get("createdAt")) if row.get("createdAt") else None
        value = material(source, name, "https://huggingface.co/" + name, excerpt, kind="catalog_metadata",
                         date=created)
        # Read only the publicly served model card, never weights or gated files.
        # A model-weight license is not a grant to redistribute the whole card.
        if not output:
            try:
                card = await fetch("https://huggingface.co/" + quote(name, safe="/._-") + "/raw/main/README.md", {"huggingface.co"})
                excerpt = card.decode("utf-8", errors="replace")[:6000].strip()
                if len(excerpt) >= 100:
                    value = value.model_copy(update={"text": excerpt, "content_kind": "publisher_excerpt"})
            except Exception:
                pass
        output.append(value)
    return output


# AIHOT 精选摘要 (https://aihot.news/feed.xml, 2026-11-25, owner's choice A). Each pick is
# AIHOT's own Chinese summary of someone else's post. A pick whose original we can read becomes
# an ordinary lead on that original (judged only after the page is read); a pick from X or WeChat,
# which this project cannot read, keeps AIHOT's summary as `curated_summary`: judged, but labelled
# as a second-hand summary and kept out of focus by the engine.
UNREADABLE_HOSTS = ("x.com", "twitter.com", "mp.weixin.qq.com")


def aihot_picks(source, body, limit):
    tree = etree.fromstring(body, parser=etree.XMLParser(recover=True, resolve_entities=False, no_network=True))
    known = source.get("known_hosts", {})
    output = []
    for item in tree.iter("item"):
        if len(output) >= limit:
            break
        title = clean(item.findtext("title"))
        description = item.findtext("description") or ""
        page = html.fromstring(f"<div>{description}</div>")
        links = [a.get("href") for a in page.xpath(".//a[@href]")]
        original = next((u for u in links if (urlsplit(u).hostname or "") not in {"aihot.news", "www.aihot.news"}), None)
        if not title or not original:
            continue
        try:
            original = public_url(original)
        except ValueError:
            continue
        # Keep AIHOT's summary paragraphs, not its "阅读原文" / "via AIHOT" link lines.
        summary = clean(" ".join(p.text_content() for p in page.xpath(".//p")
                                 if not p.xpath(".//a") and "via AIHOT" not in p.text_content()))
        author = re.search(r"\(([^)]+)\)\s*$", item.findtext("author") or "")
        author = clean(author.group(1)) if author else ""
        host = (urlsplit(original).hostname or "").lower()
        unreadable = any(host == h or host.endswith("." + h) for h in UNREADABLE_HOSTS)
        role = known.get(host) or ("author" if unreadable else "media")
        stamp = item.findtext("pubDate")
        try:
            date = parsedate_to_datetime(stamp).astimezone(timezone.utc).isoformat() if stamp else None
        except (TypeError, ValueError):
            date = None
        name = f"{author} · 经 AIHOT 精选" if author else "AIHOT 精选"
        value = material({**source, "name": name, "role": role}, title, original, summary,
                         kind="curated_summary" if unreadable else "search_excerpt", date=date,
                         identity=clean(item.findtext("guid")) or original,
                         discovery_url=clean(item.findtext("link")) or None)
        output.append(value)
    return output


def parse_index(source, body, limit):
    return {"publisher_index": publisher_links, "changelog": changelog, "updates": updates, "aihot": aihot_picks,
            "daily_papers": daily_papers, "openreview": openreview,
            "document": document, "markdown": markdown, "arena": arena,
            "swebench": swebench, "modelscope_models": modelscope_models}[source["kind"]](source, body, limit)
