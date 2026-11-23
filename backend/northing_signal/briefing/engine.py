"""Pure event projection and reader ranking; no HTTP, database, or evaluation imports."""

import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .models import POLICY_EPOCH, TOPICS, assessment_of, digest, now


def stamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def normalize(value):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.casefold())


def occurrence_key(value):
    # Common model-proposed aliases for a launch must not split an otherwise
    # identical subject/product frame. Version and all other key terms stay intact.
    value = re.sub(r"\b(?:general[ _-]+availability|generally[ _-]+available|ga|launch)\b",
                   "release", value.casefold())
    return normalize(value)


def frame_key(assessment):
    """The projection's event name for a judgment, or None when the frame is too vague.

    The model's event key is a proposal. Subject AND concrete object must also agree.
    Empty/ambiguous frames stay separate; names of companies alone never merge events.
    """
    frame = [normalize(assessment.subject), normalize(assessment.object), occurrence_key(assessment.event_key)]
    return digest(frame)[:24] if all(frame) and len(frame[1]) >= 3 else None


def text_key(material):
    """Reposts of one long original text belong to one event whatever the model called it."""
    original = normalize(material.text)
    return digest(original) if len(original) >= 120 else None


def occurrences(materials, judgments, *, as_of=None):
    """(material, assessment) for materials the projection puts into events, in its order."""
    clock = stamp(as_of) if as_of else datetime.now(timezone.utc)
    for material in sorted(materials, key=lambda m: (m.captured_at, m.id)):
        row = judgments.get(material.version)
        if not row or stamp(material.captured_at) > clock:
            continue
        assessment = assessment_of(row)
        published = stamp(material.published_at)
        if assessment.relevance == "ai" and not (published and published > clock + timedelta(hours=24)):
            yield material, assessment


def active_actions(interactions):
    retracted = {r["retracts"] for r in interactions if r["kind"] == "retract"}
    return [r for r in interactions if r["request_id"] not in retracted and r["kind"] != "retract"]


def project(materials, judgments, preferences, interactions=(), *, as_of=None, membership=None,
            briefing_at=None, new_since=None):
    """membership: material id -> stored event id. Without it, events are derived as before.

    briefing_at: when the current briefing was made (the latest completed update). "Known" marked
    after it greys the story but only leaves the focus at the next update, so a briefing does not
    reshuffle while it is read. new_since: start of that update; events first captured since are new.
    """
    settled = stamp(briefing_at) if briefing_at else None
    fresh_from = stamp(new_since) if new_since else None
    clock = stamp(as_of) if as_of else datetime.now(timezone.utc)
    groups, archive, identical = defaultdict(list), [], {}
    for material in sorted(materials, key=lambda m: (m.captured_at, m.id)):
        if stamp(material.captured_at) > clock:
            continue
        row = judgments.get(material.version)
        brief = {"id": material.id, "version": material.version, "title": material.title,
                 "source": material.source_name, "url": material.url, "published_at": material.published_at,
                 "captured_at": material.captured_at, "status": "pending"}
        brief["content_kind"] = material.content_kind
        if not row:
            archive.append(brief)
            continue
        assessment = assessment_of(row)
        future = stamp(material.published_at)
        if future and future > clock + timedelta(hours=24):
            brief.update(status="time_uncertain")
            archive.append(brief)
            continue
        brief.update(title=assessment.title or material.title, summary=assessment.summary,
                     topic=assessment.topic, status=assessment.relevance)
        archive.append(brief)
        if assessment.relevance != "ai":
            continue
        text = text_key(material)
        if membership and material.id in membership:
            group = membership[material.id]
            if text:
                identical.setdefault(text, group)
        else:
            group = frame_key(assessment) or material.id
            if text:
                group = identical.setdefault(text, group)
        groups[group].append((material, assessment, row))

    actions = active_actions(interactions)
    affinities = defaultdict(float)
    event_topics = {key: members[0][1].topic for key, members in groups.items()}
    seen_feedback = set()
    for action in actions:
        key = (action["event_id"], action["kind"])
        topic = event_topics.get(action["event_id"])
        if topic and key not in seen_feedback:
            seen_feedback.add(key)
            if action["kind"] == "useful":
                affinities[topic] += 1
            elif action["kind"] == "irrelevant":
                affinities[topic] -= 1
    events = []
    for event_id, members in groups.items():
        def priority(member):
            material, a, _ = member
            urgent = a.action in {"correction", "withdrawal"}
            date = stamp(material.published_at) or stamp(material.captured_at)
            usable = bool(a.claims) and a.evidence != "insufficient"
            worth = a.significance * 3 + a.novelty * 2 + a.usefulness >= 9 or urgent
            return (usable and worth, urgent, a.action in {"test", "update"},
                    material.source_role in {"official", "research"},
                    a.significance * 3 + a.novelty * 2 + a.usefulness, date)
        material, a, row = max(members, key=priority)
        value = a.significance * 3 + a.novelty * 2 + a.usefulness
        qualified = (bool(a.claims) and a.evidence != "insufficient"
                     and (value >= 9 or a.action in {"correction", "withdrawal"}))
        # Collection time says when we saw it, not when it happened: an undated model card or
        # changelog may describe something months old (Kimi K3, 2026-11-23). Without any
        # publication date among the reports the event earns no recency and stays out of focus.
        published = [d for m, _, _ in members if (d := stamp(m.published_at))]
        dated = bool(published)
        date = stamp(material.published_at) or (min(published) if published else stamp(material.captured_at))
        age_days = max(0, (clock - date).total_seconds() / 86400)
        version = material.version
        relevant = a.topic in preferences.topics
        recent_actions = [r for r in actions if r["event_id"] == event_id and r["version"] == version]
        known = any(r["kind"] == "known" for r in recent_actions)
        known_earlier = any(r["kind"] == "known" and (settled is None or not stamp(r.get("at"))
                                                       or stamp(r["at"]) <= settled) for r in recent_actions)
        first_captured = min(m.captured_at for m, _, _ in members)
        latest_captured = max(m.captured_at for m, _, _ in members)
        dismissed = any(r["kind"] in {"irrelevant", "thin", "duplicate"} for r in recent_actions)
        protected = a.action in {"correction", "withdrawal"} and not known_earlier
        score = value + (7 if relevant else -3) + (3 * math.exp(-age_days / 7) if dated else 0)
        score += max(-3, min(3, affinities[a.topic]))
        if preferences.depth == "technical" and a.content_type in {"research", "test", "tutorial"}:
            score += 3
        if preferences.depth == "overview" and a.content_type in {"release", "industry"}:
            score += 3
        if known_earlier:
            score -= 16
        if dismissed:
            score -= 20
        timeline = [{"version": m.version, "title": b.title or m.title, "summary": b.summary,
                     "source": m.source_name, "role": m.source_role, "url": m.url,
                     "published_at": m.published_at, "action": b.action,
                     "content_kind": m.content_kind,
                     "evidence": b.evidence, "claims": [c.model_dump() for c in b.claims],
                     "conditions": b.conditions, "limitations": b.limitations}
                    for m, b, _ in sorted(members, key=lambda row: row[0].published_at or row[0].captured_at)]
        events.append({
            "id": event_id, "version": version, "title": a.title or material.title,
            "summary": a.summary, "reason": a.reason, "topic": a.topic, "topic_label": TOPICS[a.topic],
            "subject": a.subject, "object": a.object,
            "content_type": a.content_type, "action": a.action, "evidence": a.evidence,
            "content_kind": material.content_kind,
            "claims": [c.model_dump() for c in a.claims], "conditions": a.conditions,
            "limitations": list(dict.fromkeys([*a.limitations, "依据来源公开榜单的数据节选整理，需保留方法、提交者与核验状态；未由本项目复测。" if material.content_kind == "benchmark_snapshot" else "依据研究索引收录的摘要整理，未核对论文全文。" if material.content_kind == "index_abstract" else "来源为社区发言，不代表官方或独立验证。" if material.content_kind == "community_post" else "依据已取得的原文节选整理，可展开核对。"])),
            "source": material.source_name, "source_role": material.source_role, "url": material.url,
            "source_id": material.source_id,
            "published_at": material.published_at, "captured_at": material.captured_at,
            "source_count": len({m.source_id for m, _, _ in members}), "report_count": len(members),
            "qualified": qualified, "protected": protected, "known": known, "dismissed": dismissed,
            "known_earlier": known_earlier, "first_captured_at": first_captured,
            "latest_captured_at": latest_captured, "dated": dated,
            "earliest_published_at": min(published).isoformat() if published else None,
            # New: first seen in the latest update. Updated: an older event that got a new report in it.
            "new": bool(fresh_from and stamp(first_captured) and stamp(first_captured) >= fresh_from),
            "updated": bool(fresh_from and stamp(first_captured) and stamp(first_captured) < fresh_from
                            and stamp(latest_captured) and stamp(latest_captured) >= fresh_from),
            "saved": any(r["kind"] == "saved" for r in actions if r["event_id"] == event_id),
            "relevant": relevant, "score": round(score, 2), "timeline": timeline,
            "age_days": round(age_days, 1),
            "model": row.get("model"),
            # Judged under rules an epoch older than the running ones; re-judged as budget allows.
            "policy_stale": row.get("epoch", POLICY_EPOCH) < POLICY_EPOCH,
            "reading_seconds": max(25, min(100, round((len(a.summary) + len(a.reason)) / 5))),
            "actions": [r for r in actions if r["event_id"] == event_id
                        and (r["version"] == version or r["kind"] == "saved")],
        })
    events.sort(key=lambda row: (not row["protected"], -row["score"], row["id"]))
    eligible = [e for e in events if e["qualified"] and not e["dismissed"] and not e["known_earlier"]
                and (e["relevant"] or preferences.exploration) and (e["age_days"] <= 30 or e["protected"])]
    focus, radar, spent = [], [], 0
    topic_counts = defaultdict(int)
    budget = preferences.budget_minutes * 60
    excerpts = {m.version: m.text for m in materials}
    selected = []

    def adds_information(event):
        raw = excerpts.get(event["version"], "")
        if len(raw) > 700 or event["action"] in {"test", "update", "correction", "withdrawal"}:
            return True
        numbers = set(re.findall(r"\b\d{3,}\b", raw))
        tokens = set(re.findall(r"[a-z]{3,}", raw.lower())) - {"the", "and", "for", "with", "from", "that", "this"}
        for previous in selected:
            if previous["source_id"] != event["source_id"]:
                continue
            covered = excerpts.get(previous["version"], "").lower()
            if (numbers and numbers & set(re.findall(r"\b\d{3,}\b", covered)) and len(tokens) >= 12
                    and sum(token in covered for token in tokens) / len(tokens) >= 0.75):
                event["covered_by"] = previous["id"]
                return False
        return True

    for event in eligible:
        if not event["dated"] and not event["protected"]:
            continue  # undated: may still appear below the focus, marked as collected-at
        if not adds_information(event):
            continue
        if len(focus) >= 6 or spent + event["reading_seconds"] > budget * 0.7:
            continue
        if topic_counts[event["topic"]] >= 3 and not event["protected"]:
            continue
        if not event["relevant"] and len(focus) >= 1:
            continue
        focus.append(event["id"])
        selected.append(event)
        spent += event["reading_seconds"]
        topic_counts[event["topic"]] += 1
    for event in sorted(eligible, key=lambda e: not e["dated"]):  # stable: dated first, by score
        if event["id"] in focus or len(radar) >= 8 or spent + 15 > budget or not adds_information(event):
            continue
        radar.append(event["id"])
        selected.append(event)
        spent += 15
    archive.sort(key=lambda row: row["published_at"] or row["captured_at"], reverse=True)
    return {"as_of": as_of or now(), "events": events, "focus": focus, "radar": radar,
            "archive": archive, "budget_seconds": budget, "estimated_seconds": spent,
            "counts": {"materials": len(archive), "events": len(events), "eligible": len(eligible),
                       "pending": sum(r["status"] == "pending" for r in archive),
                       "unrelated": sum(r["status"] == "unrelated" for r in archive),
                       "new": sum(e["new"] and e["qualified"] and not e["dismissed"] for e in events)}}
