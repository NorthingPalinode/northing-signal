"""Public discovery channels; search snippets remain distinct from publisher evidence."""

import asyncio
import json
import re
from urllib.parse import quote, urlencode, urlsplit

from .collect import fetch, text
from .models import Material, digest, public_url

SEARCH_SOURCES = {
    "web": {"name": "网页搜索", "url": "https://www.anysearch.com/", "role": "media",
            "description": "通过 AnySearch 查找官方发布、文档、评测和技术文章"},
    "arxiv": {"name": "arXiv · 预印本", "url": "https://arxiv.org/", "role": "research", "description": "研究预印本"},
    "github": {"name": "GitHub · 开源项目", "url": "https://github.com/", "role": "author", "description": "开源代码与实现"},
    "huggingface": {"name": "Hugging Face · 模型卡", "url": "https://huggingface.co/", "role": "author", "description": "模型仓库、模型卡与使用限制"},
    "openalex": {"name": "OpenAlex · 研究索引", "url": "https://openalex.org/", "role": "research", "description": "跨期刊和会议的研究索引与收录摘要"},
    "hackernews": {"name": "Hacker News · 社区线索", "url": "https://news.ycombinator.com/", "role": "community", "description": "开发者发布、实践分享与讨论线索"},
    "x": {"name": "X / Twitter", "url": "https://x.com/", "role": "community", "access": "web_index",
          "description": "公开帖子的网页索引线索；不保证实时或完整正文"},
    "douyin": {"name": "抖音", "url": "https://www.douyin.com/", "role": "community", "access": "web_index",
               "description": "公开视频和图文的网页索引线索；尚未接入站内搜索或视频字幕"},
    "xiaohongshu": {"name": "小红书", "url": "https://www.xiaohongshu.com/", "role": "community", "access": "web_index",
                    "description": "公开笔记的网页索引线索；尚未接入站内检索或登录正文"},
}

SOCIAL_SOURCES = {"x", "douyin", "xiaohongshu"}


def secret(settings, name):
    value = getattr(settings, name, None)
    return value.get_secret_value() if value else ""


async def api(url, host, *, method="GET", payload=None, key=""):
    headers = {"Authorization": "Bearer " + key} if key else {}
    return json.loads(await asyncio.wait_for(fetch(url, {host}, method=method, payload=payload, headers=headers), 35))


def source_access(channel, settings=None):
    if channel == "x" and secret(settings, "reader_x_bearer_token"):
        return "platform_api"
    return SEARCH_SOURCES[channel].get("access", "direct")


def social_post(channel, url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    domains, path = {
        "x": (("x.com", "twitter.com"), r"/(?:[A-Za-z0-9_]+|i/web)/status/[0-9]+/?"),
        "douyin": (("douyin.com",), r"/(?:video|note)/[0-9]+/?"),
        "xiaohongshu": (("xiaohongshu.com",), r"/(?:explore|discovery/item)/[0-9a-fA-F]{24}/?"),
    }[channel]
    return any(host == domain or host == "www." + domain or host == "m." + domain for domain in domains) and bool(re.fullmatch(path, parsed.path))


async def social_web(channel, query, limit, settings=None):
    scope = "(site:x.com OR site:twitter.com)" if channel == "x" else "site:" + {"douyin": "douyin.com", "xiaohongshu": "xiaohongshu.com"}[channel]
    leads = await web(scope + " " + query, limit, settings)
    return [lead.model_copy(update={"id": digest([channel + "-discovery", lead.url])[:24],
                                   "source_id": channel + "-discovery", "source_role": "community",
                                   "source_name": SEARCH_SOURCES[channel]["name"] + " · 网页索引线索",
                                   "discovery_url": lead.url}) for lead in leads if social_post(channel, lead.url)]


async def x(query, limit, settings=None):
    key = secret(settings, "reader_x_bearer_token")
    if not key:
        return await social_web("x", query, limit, settings)
    params = urlencode({"query": query, "max_results": max(10, min(limit, 100)),
                        "tweet.fields": "created_at,author_id,note_tweet", "expansions": "author_id",
                        "user.fields": "username,name"})
    body = await api("https://api.x.com/2/tweets/search/recent?" + params, "api.x.com", key=key)
    if body.get("errors") and not body.get("data"):
        raise ValueError("x_search_failed")
    users = {u["id"]: u.get("username", "i/web") for u in (body.get("includes") or {}).get("users", [])}
    output = []
    for row in body.get("data", [])[:limit]:
        tweet_id, author = str(row.get("id", "")), users.get(row.get("author_id"), "i/web")
        if not tweet_id.isdigit() or not re.fullmatch(r"[A-Za-z0-9_]+|i/web", author):
            continue
        supplied = (row.get("note_tweet") or {}).get("text") or row.get("text", "")
        if not supplied.strip():
            continue
        material = result("x", supplied[:100], "https://x.com/" + author + "/status/" + tweet_id,
                          supplied, kind="community_post", role="community", date=row.get("created_at"))
        output.append(material.model_copy(update={"source_name": "X · @" + author}))
    return output


async def douyin(query, limit, settings=None):
    return await social_web("douyin", query, limit, settings)


async def xiaohongshu(query, limit, settings=None):
    return await social_web("xiaohongshu", query, limit, settings)


def result(source, title, url, body, *, kind="search_excerpt", role="author", date=None, discovery_url=None):
    if url.startswith("http://"):
        url = "https://" + url[7:]
    url = public_url(url)
    host = urlsplit(url).hostname
    title = text(title or "", 600)
    return Material(id=digest([source + "-discovery", url])[:24], source_id=source + "-discovery",
                    source_name=SEARCH_SOURCES[source]["name"] + " · " + host, source_role=role,
                    title=title, url=url, text=text(body or "", 6000), published_at=date,
                    content_kind=kind, discovery_url=discovery_url)


async def web(query, limit, settings=None):
    body = await api("https://api.anysearch.com/v1/search", "api.anysearch.com", method="POST",
                     payload={"query": query, "max_results": limit}, key=secret(settings, "reader_web_api_key"))
    # Never consume auto-registered credentials or log error bodies. Provider content is not publisher text.
    rows = body["data"]["results"]
    if not isinstance(rows, list):
        raise ValueError("invalid_web_response")
    output = []
    for row in rows[:limit]:
        try:
            url = row.get("url", "")
            positive = re.findall(r"(?<![-\w])site:([A-Za-z0-9.-]+(?:/[^\s\"']*)?)", query)
            negative = re.findall(r"-site:([A-Za-z0-9.-]+(?:/[^\s\"']*)?)", query)
            def site_match(site):
                scope, candidate = urlsplit("https://" + site), urlsplit(url)
                return bool(candidate.hostname and scope.hostname and
                            (candidate.hostname == scope.hostname or candidate.hostname.endswith("." + scope.hostname)) and
                            (not scope.path or candidate.path.startswith(scope.path)))
            if (positive and not any(site_match(site) for site in positive)) or any(site_match(site) for site in negative):
                continue
            output.append(result("web", row.get("title"), row.get("url", ""), row.get("snippet", "")))
        except (ValueError, TypeError):
            continue
    return output


def abstract(index):
    if not isinstance(index, dict):
        return ""
    positions = {}
    for word, indexes in index.items():
        for position in indexes if isinstance(indexes, list) else []:
            if type(position) is int and 0 <= position < 1800:
                positions[position] = word
    return " ".join(positions[i] for i in sorted(positions))[:6000]


async def openalex(query, limit, settings=None):
    params = urlencode({"search": query, "per_page": limit,
                        "select": "id,title,doi,publication_date,abstract_inverted_index,primary_location,type"})
    body = await api("https://api.openalex.org/works?" + params, "api.openalex.org",
                     key=secret(settings, "reader_openalex_api_key"))
    output = []
    for row in body.get("results", [])[:limit]:
        try:
            original = (row.get("primary_location") or {}).get("landing_page_url") or row.get("doi") or row["id"]
            excerpt = abstract(row.get("abstract_inverted_index"))
            output.append(result("openalex", row.get("title"), original, excerpt,
                                 role="research", kind="index_abstract" if excerpt else "catalog_metadata",
                                 date=row.get("publication_date"), discovery_url=row["id"]))
        except (ValueError, KeyError, TypeError):
            continue
    return output


async def huggingface(query, limit, settings=None):
    params = urlencode({"search": query, "limit": limit, "full": "true", "sort": "lastModified", "direction": -1})
    rows = await api("https://huggingface.co/api/models?" + params, "huggingface.co")
    output = []
    for i, row in enumerate(rows[:limit]):
        name = row.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
            continue
        info = row.get("cardData") if isinstance(row.get("cardData"), dict) else {}
        license_id = info.get("license")
        if not isinstance(license_id, str):
            license_id = next((t[8:] for t in row.get("tags", []) if isinstance(t, str) and t.startswith("license:")), None)
        metadata = "模型仓库：" + name + "；任务类型：" + str(row.get("pipeline_tag") or "未说明") + "；声明许可：" + str(license_id or "未说明")
        material = result("huggingface", name, "https://huggingface.co/" + name, metadata,
                          kind="catalog_metadata", discovery_url="https://huggingface.co/" + name)
        output.append(material)
        if i < 2 and license_id in {"mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause"}:
            try:
                card = await asyncio.wait_for(fetch("https://huggingface.co/" + quote(name, safe="/._-") + "/raw/main/README.md", {"huggingface.co"}), 20)
                excerpt = text(card.decode("utf-8", errors="replace"), 6000)
                if len(excerpt) >= 100:
                    output[-1] = material.model_copy(update={"text": excerpt, "content_kind": "publisher_excerpt"})
            except Exception:
                pass
    return output


async def hackernews(query, limit, settings=None):
    params = urlencode({"query": query, "tags": "story", "hitsPerPage": limit})
    body = await api("https://hn.algolia.com/api/v1/search_by_date?" + params, "hn.algolia.com")
    output = []
    for row in body.get("hits", [])[:limit]:
        try:
            item_id = str(row.get("objectID", ""))
            if not item_id.isdigit():
                continue
            discussion = "https://news.ycombinator.com/item?id=" + item_id
            post = text(row.get("story_text") or "", 6000)
            original = row.get("url")
            output.append(result("hackernews", row.get("title"), discussion if post or not original else original,
                                 post, kind="community_post" if post else "search_excerpt", role="community",
                                 date=row.get("created_at") if post or not original else None, discovery_url=discussion))
        except (ValueError, TypeError):
            continue
    return output


PROVIDERS = {"web": web, "openalex": openalex, "huggingface": huggingface, "hackernews": hackernews,
             "x": x, "douyin": douyin, "xiaohongshu": xiaohongshu}
