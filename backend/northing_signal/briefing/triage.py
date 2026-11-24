"""Which unjudged materials the model reads first (2026-11-24).

An update judges only so many materials, and newest-first let a stream of fresh model cards and
paper listings push the day's biggest story out of that budget every time: Jensen Huang back as
Nvidia CEO, about ten reports from four outlets, was collected and never read. Order instead by
what is known for free:

1. still news (published within the late window of the previous update), before old finds;
2. how many other outlets report the same thing (titles sharing names), most first;
3. articles before model-card catalogs and paper listings (many entries, each rarely news);
4. newest first.

No outlet takes more than PER_SOURCE of the leading places; its other items follow the rest.
Already judged materials only count as other outlets' reports; they take no place in the order.
Pure: no model, network or database.
"""

from datetime import timedelta

from .engine import LATE_HOURS, stamp
from .relate import tokens
from .understand import is_model_card

# Title words that say nothing about which story it is (relate.COMMON is already removed).
STOP = {"as", "to", "of", "in", "on", "is", "it", "its", "at", "by", "an", "be", "or", "from", "after", "how", "why",
        "what", "this", "that", "into", "over", "are", "was", "has", "have", "will", "can", "now", "about", "more",
        "says", "say", "said", "first", "out", "up", "you", "your", "our", "we", "his", "her", "their", "not", "but",
        "inc", "co", "vs", "via", "all", "one", "two", "back", "news", "week", "today", "report", "reportedly"}
LINK_SHARED = 2      # names two titles must share ...
LINK_OVERLAP = 0.3   # ... covering this part of the shorter title
BUZZ_CAP = 5         # beyond five other outlets, more do not reorder
PER_SOURCE = 6
LISTINGS = {"arxiv-recent", "hf-daily-papers"}


def title_words(material):
    return tokens(material.title) - STOP


def when(material):
    return stamp(material.published_at) or stamp(material.captured_at)


def outlets(materials, clock, hours=LATE_HOURS * 2):
    """{version: number of other sources with a similar title} among recent materials."""
    recent = [(m, title_words(m), listing(m)) for m in materials
              if (at := when(m)) and clock - at <= timedelta(hours=hours)]
    linked = {}
    for index, (first, a, first_listed) in enumerate(recent):
        if len(a) < LINK_SHARED:
            continue
        for second, b, second_listed in recent[index + 1:]:
            if first.source_id == second.source_id or len(b) < LINK_SHARED:
                continue
            if first_listed and second_listed:
                continue  # papers and model cards share jargon; coverage means an article about it
            shared = len(a & b)
            if shared >= LINK_SHARED and shared / min(len(a), len(b)) >= LINK_OVERLAP:
                linked.setdefault(first.version, set()).add(second.source_id)
                linked.setdefault(second.version, set()).add(first.source_id)
    return {version: len(sources) for version, sources in linked.items()}


def listing(material):
    return is_model_card(material) or material.source_id in LISTINGS


def triage(materials, clock, refreshed=(), hours=LATE_HOURS, done=frozenset()):
    """Materials to judge, in order (the done ones last, as they came).

    refreshed: completion times of updates; done: versions already judged.
    """
    times = sorted(t for t in (stamp(v) if isinstance(v, str) else v for v in refreshed) if t)
    before = [t for t in times if t <= clock]
    since = (before[-1] if before else clock) - timedelta(hours=hours)
    buzz = outlets(materials, clock)

    def key(material):
        published = stamp(material.published_at)
        moment = when(material)
        return (not (published and published >= since), -min(buzz.get(material.version, 0), BUZZ_CAP),
                listing(material), -(moment.timestamp() if moment else 0), material.version)
    ordered = sorted((m for m in materials if m.version not in done), key=key)
    leading, later, taken = [], [], {}
    for material in ordered:
        count = taken.get(material.source_id, 0)
        (leading if count < PER_SOURCE else later).append(material)
        taken[material.source_id] = count + 1
    return leading + later + [m for m in materials if m.version in done]
