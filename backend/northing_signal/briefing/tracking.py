"""Topic membership and unread versions, independent of HTTP and background work."""

import re
import unicodedata

from .models import TOPICS


def folded(value):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", unicodedata.normalize("NFKC", value).casefold())


def matches(follow, text, topic=None):
    # Explicit aliases separated by commas are OR alternatives, not an opaque model judgment.
    terms = [part.strip() for value in (follow["name"], follow["query"])
             for part in re.split(r"[,，;；|]", value) if part.strip()]
    if topic and TOPICS.get(topic) in terms:
        return True
    haystack = folded(text)
    return any(len(folded(term)) >= 2 and folded(term) in haystack for term in terms)


def project_follows(follows, events, materials, assessments=None):
    originals = {m.version: m for m in materials}
    result = []
    for follow in follows:
        linked = set(follow.get("material_ids", []))
        seen = set(follow.get("seen_versions", []))
        related = []
        reasons = {}
        decisions = (assessments or {}).get(follow.get("plan_hash"), {})
        versions = set()
        for event in events:
            event_versions = {row["version"] for row in event["timeline"]}
            rows = [originals[v] for v in event_versions if v in originals]
            text = " ".join([event["title"], event["summary"], *[m.title + " " + m.text for m in rows]])
            if follow.get("intent_plan"):
                verdict = decisions.get(event["version"], {})
                if not verdict.get("relevant"):
                    continue
                reasons[event["id"]] = verdict["reason"]
            elif not any(m.id in linked for m in rows) and not matches(follow, text, event["topic"]):
                continue
            if not event["qualified"]:
                continue
            versions.update(event_versions)
            date = max((m.captured_at for m in rows), default=event["captured_at"])
            related.append((date, event["id"], not event_versions.issubset(seen)))
        related.sort(reverse=True)
        pending = [m.version for m in materials if m.version not in versions and
                   ((m.id in linked and m.version not in decisions) if follow.get("intent_plan") else
                    (m.id in linked or matches(follow, m.title + " " + m.text)))]
        result.append({**{k: v for k, v in follow.items() if k not in {"material_ids", "seen_versions"}},
                       "event_ids": [row[1] for row in related],
                       "unread_ids": [row[1] for row in related if row[2]],
                       "versions": sorted(versions), "material_versions": pending, "reasons": reasons})
    return result
