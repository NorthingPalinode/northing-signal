"""Open source and community: GitHub's own rankings (2026-11-24, docs/plans/LENSES_PLAN.md stage 3).

Trending (daily, weekly) is a public web page without an official API; each row gives the
stars gained in that period. Star totals and new projects come from the official search API,
one query per topic (the API refuses OR between topics), merged. Only AI projects are kept.
Nothing is judged by a model and nothing becomes a material: each update stores the lists in
the source's state, so a failed fetch keeps showing the last list with its time.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from lxml import html

KINDS = {"github_trending", "github_search"}
AI = re.compile(
    r"(?i)(?<![a-z])(ai|llms?|gpts?|agents?|agentic|rag|mcp|claude|openai|gemini|qwen|deepseek|llama|"
    r"diffusion|transformers?|models?|inference|embeddings?|chatbots?|copilot|machine[- ]learning|"
    r"deep[- ]learning|neural|vlms?|multimodal|fine-?tun\w*|lora|prompts?|speech|tts|asr|whisper|"
    r"skills?|vibe[- ]coding)(?![a-z])|人工智能|大模型|智能体|模型")
COLLECTION = re.compile(
    r"(?i)(?<![a-z])(awesome|curated|collections?|lists?|resources|roadmaps?|tutorials?|courses?|"
    r"interviews?|cheat-?sheets?|books?)(?![a-z])|教程|合集|面试|学习路线")
DOUBTFUL_STARS, DOUBTFUL_FORK_SHARE = 1000, 0.03


def number(text):
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def clean(value):
    return " ".join(str(value or "").split())


def trending(body):
    """Rows of github.com/trending: repository, description, language, stars, forks, gained."""
    tree = html.fromstring(body.decode("utf-8", errors="replace"))
    rows = []
    for article in tree.xpath('//article[contains(concat(" ", normalize-space(@class), " "), " Box-row ")]'):
        links = article.xpath(".//h2//a/@href")
        if not links:
            continue
        name = links[0].strip("/")
        if name.count("/") != 1:
            continue
        gained = re.search(r"([\d,]+)\s+stars?\s+(?:today|this week|this month)", article.text_content())
        rows.append({
            "name": name, "url": "https://github.com/" + name,
            "description": clean(article.xpath("string(.//p)"))[:300],
            "language": clean(article.xpath('string(.//span[@itemprop="programmingLanguage"])')),
            "stars": number(article.xpath('string(.//a[contains(@href, "/stargazers")])')),
            "forks": number(article.xpath('string(.//a[contains(@href, "/forks")])')),
            "gained": number(gained.group(1)) if gained else None, "topics": [],
        })
    return rows


def search_rows(body):
    items = json.loads(body).get("items", [])
    return [{"name": i["full_name"], "url": i["html_url"], "description": clean(i.get("description"))[:300],
             "language": i.get("language") or "", "stars": i.get("stargazers_count", 0),
             "forks": i.get("forks_count", 0), "created_at": i.get("created_at"),
             "topics": i.get("topics", [])[:8], "gained": None} for i in items]


def search_query(source, clock):
    """`{days_ago:30}` in the query becomes the date 30 days before `clock`."""
    def date(match):
        return (clock - timedelta(days=int(match.group(1)))).strftime("%Y-%m-%d")
    return re.sub(r"\{days_ago:(\d+)\}", date, source.get("query", ""))


def is_ai(row):
    return bool(AI.search(" ".join([row["name"].replace("-", " ").replace("_", " "), row["description"],
                                    " ".join(row.get("topics", []))])))


def flags(row):
    """Labels, not verdicts: a list or tutorial collection; stars far ahead of forks."""
    found = []
    if COLLECTION.search(row["name"].split("/")[-1].replace("-", " ") + " " + row["description"]):
        found.append("collection")
    if row["stars"] >= DOUBTFUL_STARS and row["forks"] < row["stars"] * DOUBTFUL_FORK_SHARE:
        found.append("few_forks")
    return found


def rank(rows, limit):
    """AI projects only, first occurrence of each, in the source's order, with flags."""
    seen, kept = set(), []
    for row in rows:
        if row["name"] in seen or not is_ai(row):
            continue
        seen.add(row["name"])
        kept.append({**row, "flags": flags(row)})
        if len(kept) >= limit:
            break
    return kept


async def read_ranking(source, fetch, token="", clock=None):
    limit = source.get("max_items", 15)
    if source["kind"] == "github_trending":
        return rank(trending(await fetch(source["url"], set(source["hosts"]))), limit)
    clock = clock or datetime.now(timezone.utc)
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    rows = []
    for topic in source.get("topics", []):
        query = f"topic:{topic} {search_query(source, clock)}".strip()
        url = f"{source['url']}?q={quote(query)}&sort=stars&order=desc&per_page={min(50, limit * 2)}"
        rows += search_rows(await fetch(url, set(source["hosts"]), headers=headers))
    rows.sort(key=lambda r: -r["stars"])
    return rank(rows, limit)
