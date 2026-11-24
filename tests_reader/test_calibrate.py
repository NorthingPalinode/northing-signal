"""Calibration on the owner's labels (2026-11-24, adapted from AIHOT's SelectBench)."""

import json

from northing_signal.briefing.calibrate import (
    HARD_BAND,
    calibrate,
    label_row,
    metrics,
    read_labels,
    sample,
    split_of,
)
from northing_signal.briefing.engine import project
from northing_signal.briefing.models import Preferences
from northing_signal.briefing.store import Store
from northing_signal.briefing.understand import POLICY_HASH
from test_reader import assessment, material


def scored(key, significance, novelty, usefulness, role="media"):
    item = material(id=key, url=f"https://example.org/{key}", source_id=role + "-source", source_role=role,
                    text=f"{key} is available. Free for research.")
    judged = assessment(significance=significance, novelty=novelty, usefulness=usefulness,
                        subject=key, object=key + " 1", event_key=key).model_dump()
    return item, judged


def test_samples_lean_on_hard_cases_and_alternate_source_groups():
    items, judgments = [], {}
    for index in range(40):
        role = "official" if index % 2 else "media"
        level = index % 5  # values 0, 6, 12, 18, 24 ... mixed hard and easy
        item, judged = scored(f"m{index}", level, level, level, role)
        items.append(item)
        judgments[item.version] = judged
    picked = sample(items, judgments, 10, seed=1)
    assert len(picked) == 10 and len({m.version for m in picked}) == 10
    values = [judgments[m.version]["significance"] * 6 for m in picked]
    assert sum(v in HARD_BAND for v in values) == 6  # 60 % near the threshold
    assert {m.source_role for m in picked} == {"official", "media"}
    # Already labeled materials are not asked again; the split is stable per material.
    again = sample(items, judgments, 10, labeled={m.version for m in picked}, seed=1)
    assert not {m.version for m in again} & {m.version for m in picked}
    assert all(split_of(m.version) == split_of(m.version) for m in picked)
    assert {split_of(m.version) for m in items} == {"development", "holdout"}


def test_metrics_and_sweep_find_the_threshold_your_labels_prefer():
    rows, judgments = [], {}
    # Scores (3*significance + 2*novelty + usefulness): reads 24 and 15; skips 9, 6 and 1.
    # The current threshold 9 lets the 9 through; anything from 10 to 15 separates them.
    for key, level, decision in [("a", (4, 4, 4), "read"), ("b", (3, 2, 2), "read"), ("c", (2, 1, 1), "skip"),
                                 ("d", (1, 1, 1), "skip"), ("e", (0, 0, 1), "skip"), ("f", (3, 1, 1), "either")]:
        item, judged = scored(key, *level)
        judgments[item.version] = judged
        rows.append(label_row(item, decision))
    rows.append({**label_row(scored("g", 4, 4, 4)[0], "read")})  # labeled but never judged
    result = metrics(rows, judgments, {"other": 9})
    assert (result["tp"], result["fp"], result["fn"]) == (2, 1, 0)
    assert result["coverage"] == 0.833 and result["precision"] == 0.667 and result["recall"] == 1.0
    assert any(e["type"] == "not_judged" for e in result["errors"])
    report = calibrate(rows, judgments, {"official": 9, "other": 9})
    assert report["either_excluded"] == 1
    # A tie keeps the threshold nearest the current one: 10, not 15.
    assert report["suggested"]["other"]["threshold"] == 10 and report["suggested"]["other"]["f1"] == 1.0
    assert "official" not in report["suggested"]  # no labels there: no advice


def test_thresholds_from_calibration_change_what_the_briefing_selects():
    official, judged_official = scored("lab", 2, 1, 1, role="official")      # value 9
    media, judged_media = scored("blog", 2, 1, 1, role="media")              # value 9
    judgments = {official.version: judged_official, media.version: judged_media}
    clock = "2026-11-01T02:00:00+00:00"
    default = {e["source_id"]: e["qualified"] for e in project([official, media], judgments, Preferences(),
                                                              as_of=clock)["events"]}
    assert default == {"official-source": True, "media-source": True}
    strict = {e["source_id"]: e["qualified"] for e in project(
        [official, media], judgments, Preferences(), as_of=clock, thresholds={"official": 8, "other": 12})["events"]}
    assert strict == {"official-source": True, "media-source": False}


def test_labeling_saves_each_answer_and_resumes(tmp_path, monkeypatch):
    from northing_signal.briefing.__main__ import label
    store = Store(tmp_path / "reader.db")
    for index in range(4):
        item, judged = scored(f"m{index}", 2, 2, 2)
        store.capture(item)
        store.judge(item.version, POLICY_HASH, judged, "fixture")
    gold = tmp_path / "gold.jsonl"
    answers = iter(["x", "y", "k", "n", "q"])  # an invalid key is asked again; k skips; q stops
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    label(store, gold, 4)
    rows = read_labels(gold)
    assert [r["decision"] for r in rows] == ["read", "skip"] and all(r["labeled_by"] == "human" for r in rows)
    queue = json.loads((tmp_path / "gold-queue.json").read_text("utf-8"))
    assert len(queue) == 4
    # Next time it continues with the same queue, without asking the answered ones again.
    answers = iter(["e", "e"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    label(store, gold, 4)
    assert len(read_labels(gold)) == 4
