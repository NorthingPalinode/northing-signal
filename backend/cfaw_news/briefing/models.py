"""Small versioned product contracts, also used by the API and tests."""

import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TOPICS = {
    "models": "模型与多模态", "agents": "Agent 与开发", "research": "研究与评测",
    "engineering": "部署与成本", "products": "产品与应用", "industry": "产业与政策",
}
POLICY = "content-v1"
# Raise only when a change should invalidate earlier judgments (e.g. new scoring rules).
# Rewording the prompt alone keeps them; older epochs stay visible, marked, until re-judged.
POLICY_EPOCH = 1
JUDGMENT_META = ("model", "epoch")


def now():
    return datetime.now(timezone.utc).isoformat()


def day_start(timezone_name=""):
    """Start of today in the reader's timezone (system local when empty), as a UTC ISO string."""
    zone = ZoneInfo(timezone_name) if timezone_name else None
    local = datetime.now(timezone.utc).astimezone(zone)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()


def assessment_of(judgment):
    """A stored judgment row without its storage metadata."""
    return Assessment.model_validate({k: v for k, v in judgment.items() if k not in JUDGMENT_META})


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def public_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443)):
        raise ValueError("需要不含凭据的 HTTPS 原文地址")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("仅接受公共来源地址")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("仅接受公共来源地址")
    except ValueError as error:
        if str(error) == "仅接受公共来源地址":
            raise
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "asuniq"}]
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path, urlencode(query), ""))


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Material(Contract):
    id: str
    source_id: str
    source_name: str
    source_role: Literal["official", "research", "media", "author", "community"]
    title: str = Field(min_length=1, max_length=600)
    url: str
    text: str = Field(max_length=16000)
    published_at: str | None = None
    captured_at: str = Field(default_factory=now)
    content_kind: Literal["feed_excerpt", "release_notes", "publisher_excerpt", "search_excerpt", "index_abstract", "catalog_metadata", "community_post", "benchmark_snapshot"] = "feed_excerpt"
    discovery_url: str | None = None
    origin: Literal["real", "synthetic"] = "real"

    @field_validator("url", "discovery_url")
    @classmethod
    def validate_url(cls, value):
        return public_url(value) if value is not None else None

    @property
    def version(self):
        # Keyed by field values, so model_copy(update=...) never inherits a stale digest.
        return material_version(self.id, self.title, self.text, self.published_at, self.content_kind)


@lru_cache(maxsize=65536)
def material_version(key, title, text, published_at, content_kind):
    return digest([key, title, text, published_at, content_kind])


class Claim(Contract):
    statement: str = Field(min_length=1, max_length=350)
    quote: str = Field(min_length=1, max_length=700)
    kind: Literal["announcement", "reported_result", "method", "opinion", "correction"]


class Assessment(Contract):
    relevance: Literal["ai", "unrelated", "uncertain"]
    topic: Literal["models", "agents", "research", "engineering", "products", "industry"]
    content_type: Literal["release", "research", "test", "tutorial", "analysis", "industry", "other"]
    title: str = Field(max_length=160)
    summary: str = Field(max_length=700)
    reason: str = Field(max_length=250)
    subject: str = Field(max_length=120)
    object: str = Field(max_length=160)
    action: Literal["release", "update", "test", "correction", "withdrawal", "explain", "other"]
    event_key: str = Field(max_length=180)
    significance: int = Field(ge=0, le=4)
    novelty: int = Field(ge=0, le=4)
    usefulness: int = Field(ge=0, le=4)
    evidence: Literal["source_attributed", "reported_test", "opinion", "insufficient"]
    claims: list[Claim] = Field(default_factory=list, max_length=4)
    limitations: list[str] = Field(default_factory=list, max_length=5)
    conditions: list[str] = Field(default_factory=list, max_length=5)


class Preferences(Contract):
    topics: list[str] = Field(default_factory=lambda: list(TOPICS), max_length=6)
    depth: Literal["balanced", "technical", "overview"] = "balanced"
    budget_minutes: Literal[3, 7, 15] = 7
    exploration: bool = True
    # Update the briefing at 00:00 and 12:00 (reader timezone) while the service runs.
    auto_refresh: bool = True

    @field_validator("topics")
    @classmethod
    def valid_topics(cls, value):
        if not value or len(set(value)) != len(value) or any(t not in TOPICS for t in value):
            raise ValueError("至少保留一个 AI 方向，且不能重复")
        return value


class Interaction(Contract):
    request_id: str = Field(min_length=8, max_length=100)
    event_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    kind: Literal["shown", "opened", "useful", "irrelevant", "thin", "duplicate", "known", "saved", "retract"]
    retracts: str | None = None


class RefreshRequest(Contract):
    limit_per_source: int = Field(default=10, ge=1, le=20)
    analyze_limit: int = Field(default=24, ge=0, le=120)


class SplitRequest(Contract):
    version: str = Field(min_length=1, max_length=100)


class MergeRequest(Contract):
    into: str = Field(min_length=1, max_length=100)


class CancelRequest(Contract):
    id: str | None = Field(default=None, max_length=64)


class VisitRequest(Contract):
    request_id: str = Field(min_length=8, max_length=100)


SearchSource = Literal["web", "arxiv", "github", "huggingface", "openalex", "hackernews", "x", "douyin", "xiaohongshu"]


class DiscoveryRequest(Contract):
    query: str = Field(default="AI agents", min_length=2, max_length=80)
    channels: list[SearchSource] = Field(default_factory=lambda: ["web", "arxiv", "github"], min_length=1, max_length=9)


class FollowInput(Contract):
    name: str = Field(min_length=2, max_length=60)
    query: str = Field(default="", max_length=80)
    active: bool = True

    @field_validator("name", "query", mode="before")
    @classmethod
    def clean_text(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


class FollowState(Contract):
    active: bool


PlanText = Annotated[str, Field(min_length=1, max_length=220)]


class SearchDirection(Contract):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source: SearchSource
    query: str = Field(min_length=2, max_length=100)
    purpose: PlanText


class TrackingPlan(Contract):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=2, max_length=60)
    intent_summary: str = Field(min_length=10, max_length=600)
    focus: list[PlanText] = Field(min_length=1, max_length=6)
    exclude: list[PlanText] = Field(default_factory=list, max_length=6)
    entities: list[PlanText] = Field(default_factory=list, max_length=8)
    topics: list[Literal["models", "agents", "research", "engineering", "products", "industry"]] = Field(default_factory=list, max_length=6)
    searches: list[SearchDirection] = Field(default_factory=list, max_length=4)
    include_feeds: bool = True
    interval_minutes: Literal[30, 120, 1440, 10080] = 30
    relevance_criteria: str = Field(min_length=10, max_length=600)
    assumptions: list[PlanText] = Field(default_factory=list, max_length=4)
    limitations: list[PlanText] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def bounded_sources(self):
        if not self.include_feeds and not self.searches:
            raise ValueError("追踪方案至少需要一种信息来源")
        if len({(s.source, s.query.casefold()) for s in self.searches}) != len(self.searches):
            raise ValueError("请合并重复的检索方向")
        return self


class InterpretFollow(Contract):
    description: str = Field(min_length=10, max_length=2000)
    follow_id: str | None = Field(default=None, max_length=64)

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value):
        return value.strip() if isinstance(value, str) else value


class ConfirmFollow(Contract):
    draft_id: str = Field(min_length=16, max_length=64)
    plan: TrackingPlan
    active: bool = True
