"""Stable event membership: which event a material belongs to. Pure; the store persists it.

A material is assigned once, when its judgment first places it in an event, and keeps that
event across revisions and re-judgments; only an explicit split or merge moves it. Event ids
are the frame digests the projection has always used, so ids recorded before persistence
still match.
"""

import re

from .engine import frame_key, normalize, stamp, text_key

# Fuzzy matching joins differently worded frames for one product release: "GPT-5" and
# "GPT-5 release", "vLLM v0.11.0" and "vLLM 0.11", "Qwen3-Coder" and "Qwen3 Coder". After
# normalising, subject, version numbers and product words must be equal, within a week.
# Overlap thresholds were rejected: "Gemini 3 Pro" vs "Gemini 3 Pro Image" share 2 of 3 words
# yet are different models, and a wrong merge hides news while a missed one only repeats it.
FUZZY_MAX_DAYS = 7
VERSION = re.compile(r"\d+(?:\.\d+)*")
GENERIC = {"model", "models", "release", "released", "launch", "launched", "version", "the", "new",
           "official", "announcement", "available"}


def frame_of(material, assessment):
    """What later materials are compared with; normalised at comparison time."""
    return {"subject": assessment.subject, "object": assessment.object, "topic": assessment.topic,
            "date": material.published_at or material.captured_at}


def product(frame):
    """(subject, versions, words) after normalisation, or None when too vague to match."""
    subject, text = normalize(frame.get("subject") or ""), (frame.get("object") or "").casefold()
    versions = frozenset(re.sub(r"(?:\.0)+$", "", v) for v in VERSION.findall(text))
    words = frozenset(w for w in re.findall(r"[a-z]+|[\u4e00-\u9fff]", VERSION.sub(" ", text))
                      if w not in GENERIC and not (len(w) == 1 and w.isascii()))
    return (subject, versions, words) if subject and words else None


def similarity(frame, other):
    """1.0 when two frames name the same product release close in time, else None."""
    first, second = product(frame), product(other)
    if not first or first != second or frame.get("topic") != other.get("topic"):
        return None
    start, end = stamp(frame.get("date") or ""), stamp(other.get("date") or "")
    if not start or not end or abs((start - end).total_seconds()) > FUZZY_MAX_DAYS * 86400:
        return None
    return 1.0


def resolve(event_id, aliases):
    """Follow merges to the event that holds an id's materials now."""
    seen = set()
    while event_id in aliases and event_id not in seen:
        seen.add(event_id)
        event_id = aliases[event_id]
    return event_id


def assign(occurrences, members, events, aliases, assigned_texts):
    """Place unassigned materials; returns (new member rows, new events).

    occurrences: (material, assessment) for judged AI materials, in projection order.
    members: material id -> event id. events: live event id -> frame.
    assigned_texts: text key -> event id for materials already assigned.
    Order of preference mirrors the projection: identical original text, then an identical
    frame, then a fuzzy frame match, else a new event named like the projection names it.
    """
    texts, rows, created = dict(assigned_texts), [], {}
    by_subject = {}
    for key, frame in events.items():
        by_subject.setdefault(normalize(frame.get("subject") or ""), []).append(key)
    for material, assessment in occurrences:
        if material.id in members:
            continue
        text, key = text_key(material), frame_key(assessment)
        frame = frame_of(material, assessment)
        target, method, score = None, None, None
        if text and text in texts:
            target, method = texts[text], "identical_text"
        elif key and resolve(key, aliases) in events:
            target, method = resolve(key, aliases), "exact"
        elif key:
            scored = [(similarity(frame, events[e]), e) for e in by_subject.get(normalize(frame["subject"]), ())]
            scored = [(s, e) for s, e in scored if s is not None]
            if scored:
                score, target = max(scored)
                method = "fuzzy"
        if target is None:
            target = key or material.id
            if target in events or target in aliases:
                target = material.id  # a split or merge already used the frame's name
            events[target] = created[target] = frame
            by_subject.setdefault(normalize(frame["subject"]), []).append(target)
            method = "new"
        members[material.id] = target
        rows.append((material.id, target, method, score))
        if text:
            texts.setdefault(text, target)
    return rows, created
