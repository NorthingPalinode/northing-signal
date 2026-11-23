"""Calibrate the selection rule on the owner's own labels (adapted from AIHOT's SelectBench).

Workflow: `label` samples judged materials (hard cases near the threshold first) and asks the
reader, one at a time, whether each is worth reading; `calibrate` scores those labels against
the stored judgments, sweeps the threshold and lists the mistakes. Neither calls a model: it
measures the judgments already made. Labels stay local in .local/reader-quality/.

Labels are human ("labeled_by": "human"). The older AI-authored reference set (`evaluate`) is a
different thing and is never mixed in.
"""

import json
import random
from datetime import datetime, timezone

from .engine import SELECT_THRESHOLD as DEFAULT_THRESHOLD
from .engine import threshold_group as group
from .models import assessment_of, digest
from .understand import has_material

SCORE_RANGE = range(0, 25)  # significance*3 + novelty*2 + usefulness, each 0..4
HARD_BAND = range(6, 13)    # around the default threshold: the cases that decide it
HARD_SHARE = 0.6
HOLDOUT_SHARE = 3           # of 10: a stable 30 % kept back for a final check
DECISIONS = {"y": "read", "n": "skip", "e": "either"}


def value_of(judgment):
    a = assessment_of(judgment)
    return a.significance * 3 + a.novelty * 2 + a.usefulness


def selected(judgment, threshold):
    """The engine's selection rule for one judgment at `threshold` (see engine.project)."""
    a = assessment_of(judgment)
    if a.relevance != "ai" or not a.claims or a.evidence == "insufficient":
        return False
    return value_of(judgment) >= threshold or a.action in {"correction", "withdrawal"}


def split_of(version):
    return "holdout" if int(digest(version)[:8], 16) % 10 < HOLDOUT_SHARE else "development"


def sample(materials, judgments, n, labeled=(), seed=7):
    """Up to n judged materials to label: HARD_SHARE near the threshold, the rest spread out,
    alternating between official and other sources so both thresholds get evidence."""
    rng = random.Random(seed)
    labeled = set(labeled)
    pool = [m for m in materials if m.version in judgments and m.version not in labeled
            and has_material(m) and assessment_of(judgments[m.version]).relevance in {"ai", "uncertain"}]
    rng.shuffle(pool)
    hard = [m for m in pool if value_of(judgments[m.version]) in HARD_BAND]
    easy = [m for m in pool if value_of(judgments[m.version]) not in HARD_BAND]

    def balanced(rows, count):
        by_group = {"official": [], "other": []}
        for row in rows:
            by_group[group(row.source_role)].append(row)
        picked = []
        while len(picked) < count and any(by_group.values()):
            for key in ("official", "other"):
                if by_group[key] and len(picked) < count:
                    picked.append(by_group[key].pop())
        return picked

    picked = balanced(hard, round(n * HARD_SHARE))
    picked += balanced(easy, n - len(picked))
    if len(picked) < n:  # one band ran short: fill from what is left
        chosen = {m.version for m in picked}
        picked += [m for m in hard + easy if m.version not in chosen][:n - len(picked)]
    rng.shuffle(picked)
    return picked


def label_row(material, decision, note=""):
    return {"version": material.version, "title": material.title, "source": material.source_name,
            "source_id": material.source_id, "group": group(material.source_role),
            "split": split_of(material.version), "decision": decision, "note": note,
            "labeled_by": "human", "labeled_at": datetime.now(timezone.utc).isoformat()}


def read_labels(path):
    rows = {}
    if path.exists():
        for line in path.read_text("utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["version"]] = row  # a later answer replaces an earlier one
    return list(rows.values())


def metrics(rows, judgments, thresholds):
    """thresholds: group -> minimum score. Counts like AIHOT's report: coverage, accuracy on the
    answered cases, complete accuracy (unjudged cases count as wrong), precision, recall, F1."""
    decisive = [r for r in rows if r["decision"] in {"read", "skip"}]
    answered = correct = tp = fp = fn = 0
    errors = []
    for row in decisive:
        judgment = judgments.get(row["version"])
        expected = row["decision"] == "read"
        if not judgment:
            errors.append({**_brief(row), "type": "not_judged"})
            continue
        answered += 1
        predicted = selected(judgment, thresholds.get(row["group"], DEFAULT_THRESHOLD))
        correct += predicted == expected
        tp += predicted and expected
        fp += predicted and not expected
        fn += expected and not predicted
        if predicted != expected:
            errors.append({**_brief(row), "type": "false_positive" if predicted else "false_negative",
                           "score": value_of(judgment), "reason": assessment_of(judgment).reason})
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    return {"decisive": len(decisive), "answered": answered,
            "coverage": _round(answered / len(decisive) if decisive else None),
            "accuracy": _round(correct / answered if answered else None),
            "complete_accuracy": _round(correct / len(decisive) if decisive else None),
            "precision": _round(precision), "recall": _round(recall), "f1": _round(f1),
            "tp": tp, "fp": fp, "fn": fn, "errors": errors}


def calibrate(rows, judgments, current, split="all"):
    """Current result, a threshold sweep per group and the best threshold for each group."""
    rows = [r for r in rows if split == "all" or r["split"] == split]
    report = {"split": split, "labels": len(rows),
              "either_excluded": sum(r["decision"] == "either" for r in rows),
              "current": {"thresholds": current, **metrics(rows, judgments, current)},
              "sweep": {}, "suggested": {}}
    for name in ("official", "other"):
        subset = [r for r in rows if r["group"] == name]
        curve = []
        for threshold in SCORE_RANGE:
            result = metrics(subset, judgments, {name: threshold})
            curve.append({"threshold": threshold, **{k: result[k] for k in (
                "precision", "recall", "f1", "accuracy", "complete_accuracy", "tp", "fp", "fn")}})
        report["sweep"][name] = curve
        scored = [c for c in curve if c["f1"] is not None]
        if scored:
            # Best F1; a tie keeps the threshold nearest the current one (do not move without cause).
            best = max(scored, key=lambda c: (c["f1"], -abs(c["threshold"] - current.get(name, DEFAULT_THRESHOLD))))
            report["suggested"][name] = {"threshold": best["threshold"], "f1": best["f1"],
                                         "labels": sum(r["decision"] in {"read", "skip"} for r in subset)}
    report["limitations"] = [
        "Measures stored judgments on the owner's own labels; small samples move a lot.",
        "Tune on the development split; check the holdout split once at the end.",
        "Changing the prompt needs new judgments before these numbers say anything about it."]
    return report


def _brief(row):
    return {"title": row["title"], "source": row["source"], "group": row["group"], "decision": row["decision"]}


def _round(value):
    return None if value is None else round(value, 3)
