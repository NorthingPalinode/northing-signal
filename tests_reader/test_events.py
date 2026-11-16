"""Persistent event membership: matching rules, stable ids, migration, split and merge."""

import sqlite3

import pytest
from northing_signal.briefing.events import similarity
from northing_signal.briefing.models import Interaction
from northing_signal.briefing.service import ContentService
from northing_signal.briefing.store import Store
from northing_signal.briefing.understand import POLICY_HASH
from test_reader import assessment, material, settings

DAY = "2026-11-0{}T08:00:00+00:00"

# Synthetic frame pairs modelled on public product naming (not collected materials):
# (subject, object A, object B, days apart, same occurrence?)
PAIRS = [
    ("Anthropic", "Claude Opus 4.5", "Claude Opus 4.5 model", 0, True),
    ("OpenAI", "GPT-5", "GPT-5 release", 1, True),
    ("Google", "Gemini 3 Pro", "Gemini 3 Pro model", 0, True),
    ("Meta", "Llama 4 Scout", "Llama 4 Scout models", 2, True),
    ("DeepSeek", "DeepSeek-V3.2", "DeepSeek V3.2", 0, True),
    ("Mistral AI", "Mistral Large 3", "Mistral Large 3 model", 1, True),
    ("vLLM", "vLLM v0.11.0", "vLLM 0.11 release", 0, True),
    ("Alibaba", "Qwen3-Coder", "Qwen3 Coder", 0, True),
    ("Hugging Face", "Transformers v5", "Transformers 5.0", 3, True),
    ("Moonshot AI", "Kimi K2 Thinking", "Kimi K2 Thinking model", 0, True),
    ("xAI", "Grok 4", "Grok-4", 0, True),
    ("Ollama", "Ollama 0.12", "Ollama v0.12", 1, True),
    ("Anthropic", "Claude Code", "the new Claude Code", 0, True),
    ("OpenAI", "GPT-5", "GPT-5 mini", 0, False),
    ("OpenAI", "GPT-5", "GPT-5.1", 0, False),
    ("Anthropic", "Claude Opus 4.5", "Claude Sonnet 4.5", 0, False),
    ("Meta", "Llama 4 Scout", "Llama 4 Maverick", 0, False),
    ("Google", "Gemini 3 Pro", "Gemini 3 Flash", 0, False),
    ("Google", "Gemini 3 Pro", "Gemini 3 Pro Image", 0, False),
    ("Alibaba", "Qwen3", "Qwen3-VL", 0, False),
    ("DeepSeek", "DeepSeek-V3.2", "DeepSeek-R2", 0, False),
    ("Mistral AI", "Mistral Large 3", "Mistral Medium 3", 0, False),
    ("xAI", "Grok 4", "Grok 4 model", 8, False),  # a week later is a new occurrence
    ("vLLM", "vLLM 0.11", "vLLM 0.12", 0, False),
    ("Moonshot AI", "Kimi K2", "Kimi K2 Thinking", 0, False),
    ("OpenAI", "Codex", "Codex CLI", 0, False),
]


@pytest.mark.parametrize(("subject", "first", "second", "days", "same"), PAIRS)
def test_fuzzy_matching_joins_rewordings_and_keeps_products_apart(subject, first, second, days, same):
    one = {"subject": subject, "object": first, "topic": "models", "date": DAY.format(1)}
    two = {"subject": subject, "object": second, "topic": "models", "date": f"2026-11-{1 + days:02d}T08:00:00+00:00"}
    assert (similarity(one, two) is not None) == same
    assert (similarity(two, one) is not None) == same


def test_subject_and_topic_must_agree():
    base = {"subject": "Anthropic", "object": "Claude Code", "topic": "agents", "date": DAY.format(1)}
    assert similarity(base, {**base, "subject": "OpenAI"}) is None
    assert similarity(base, {**base, "topic": "products"}) is None
    assert similarity({**base, "subject": ""}, base) is None


def judged(store, item, **changes):
    store.capture(item)
    store.judge(item.version, POLICY_HASH, assessment(**changes).model_dump(), "fixture")
    return item


def ids(view):
    return {t["version"]: e["id"] for e in view["events"] for t in e["timeline"]}


def test_reworded_frames_join_and_ids_survive_re_judgment(tmp_path):
    store = Store(tmp_path / "reader.db")
    service = ContentService(store, settings())
    first = judged(store, material(id="a", url="https://example.org/a"), object="GPT-5", subject="OpenAI",
                   event_key="gpt-5")
    event_id = ids(service.view())[first.version]
    second = judged(store, material(id="b", url="https://example.org/b", text="GPT-5 is out today."),
                    object="GPT-5 release", subject="OpenAI", event_key="openai-gpt-5-launch",
                    claims=[dict(statement="GPT-5 已发布。", quote="GPT-5 is out today.", kind="announcement")])
    other = judged(store, material(id="c", url="https://example.org/c", text="GPT-5 mini is out."),
                   object="GPT-5 mini", subject="OpenAI", event_key="gpt-5-mini",
                   claims=[dict(statement="GPT-5 mini 已发布。", quote="GPT-5 mini is out.", kind="announcement")])
    found = ids(service.view())
    assert found[second.version] == event_id and found[other.version] != event_id
    with store.connection() as db:
        methods = dict(db.execute("SELECT material_id, method FROM event_members").fetchall())
    assert methods == {"a": "migrated", "b": "fuzzy", "c": "new"}  # "a" predates the first start
    # A revision judged with a different frame stays in its event: ids and feedback keep working.
    revised = judged(store, material(id="a", url="https://example.org/a", text="Atlas 2 is available. Free for research. Updated."),
                     object="Something else entirely", subject="OpenAI", event_key="other")
    assert ids(service.view())[revised.version] == event_id


def test_old_saved_revision_stays_actionable(tmp_path):
    """Regression for the 404 found in phase 3: opening a saved older revision of an event."""
    store = Store(tmp_path / "reader.db")
    service = ContentService(store, settings())
    old = judged(store, material())
    event = service.view()["events"][0]
    service.record_interaction(Interaction(request_id="saved-0001", event_id=event["id"],
                                           version=old.version, kind="saved"))
    newer = judged(store, material(text="Atlas 2 is available. Free for research. API access now."))
    view = service.view()
    assert view["events"][0]["version"] == newer.version and view["saved_events"][0]["version"] == old.version
    assert service.record_interaction(Interaction(request_id="opened-0001", event_id=event["id"],
                                                  version=old.version, kind="opened"))


def test_existing_grouping_and_actions_are_adopted_unchanged(tmp_path):
    store = Store(tmp_path / "reader.db")
    items = [judged(store, material(id=f"m{i}", url=f"https://example.org/{i}", text=f"Atlas {i % 2} is available. Free."),
                    object=f"Atlas {i % 2}", event_key=f"atlas-{i % 2}",
                    claims=[dict(statement="已发布", quote=f"Atlas {i % 2} is available.", kind="announcement")])
             for i in range(4)]
    # Before persistence: the projection's own grouping and an action recorded against it.
    from northing_signal.briefing.engine import project
    from northing_signal.briefing.models import Preferences
    before = project(items, store.judgments(), Preferences())["events"]
    store.interact(Interaction(request_id="known-0001", event_id=before[0]["id"], version=before[0]["version"],
                               kind="known"))
    view = ContentService(store, settings()).view()
    assert {e["id"] for e in view["events"]} == {e["id"] for e in before}
    assert next(e for e in view["events"] if e["id"] == before[0]["id"])["known"]
    with store.connection() as db:
        assert [tuple(r) for r in db.execute("SELECT DISTINCT method FROM event_members")] == [("migrated",)]
        assert tuple(db.execute("SELECT value FROM meta WHERE key='events_backfilled'").fetchone()) == (1,)


def test_split_and_merge_move_materials_and_reader_actions_follow(tmp_path):
    from fastapi.testclient import TestClient
    from northing_signal.briefing.app import create_app
    store = Store(tmp_path / "reader.db")
    a = judged(store, material(id="a", url="https://example.org/a"))
    b = judged(store, material(id="b", url="https://example.org/b", source_id="media", source_role="media",
                               text="Atlas 2 is available. Free for research. Repost."))
    c = judged(store, material(id="c", url="https://example.org/c", text="Orion 7 is available. Free."),
               subject="Orion", object="Orion 7", event_key="orion-7",
               claims=[dict(statement="Orion 7 已发布。", quote="Orion 7 is available.", kind="announcement")])
    with TestClient(create_app(settings(), store)) as client:
        view = client.get("/api/reader").json()
        atlas, orion = ids(view)[a.version], ids(view)[c.version]
        assert ids(view)[b.version] == atlas
        assert client.post("/api/reader/interactions", json={
            "request_id": "saved-0001", "event_id": atlas, "version": b.version, "kind": "saved"}).status_code == 200
        # Split the repost out: it becomes its own event and keeps its saved state.
        view = client.post(f"/api/reader/events/{atlas}/split", json={"version": b.version}).json()
        split = ids(view)[b.version]
        assert split != atlas and ids(view)[a.version] == atlas
        assert next(e for e in view["events"] if e["id"] == split)["saved"]
        assert client.post(f"/api/reader/events/{atlas}/split", json={"version": a.version}).status_code == 409
        assert client.post(f"/api/reader/events/{orion}/split", json={"version": a.version}).status_code == 404
        # Merge Orion into Atlas: the old id keeps working for reader actions.
        view = client.post(f"/api/reader/events/{orion}/merge", json={"into": atlas}).json()
        assert ids(view)[c.version] == atlas and orion not in {e["id"] for e in view["events"]}
        assert client.post("/api/reader/interactions", json={
            "request_id": "opened-0001", "event_id": orion, "version": c.version, "kind": "opened"}).status_code == 200
        assert client.post(f"/api/reader/events/{atlas}/merge", json={"into": orion}).status_code == 409
        assert client.post("/api/reader/events/missing/merge", json={"into": atlas}).status_code == 404
        # Unsaving after the split still finds the original action.
        assert client.post("/api/reader/interactions", json={
            "request_id": "retract-0001", "event_id": split, "version": b.version, "kind": "retract",
            "retracts": "saved-0001"}).status_code == 200
        assert not next(e for e in client.get("/api/reader").json()["events"] if e["id"] == split)["saved"]
    with sqlite3.connect(store.path) as db:
        kinds = [row[0] for row in db.execute("SELECT json_extract(data, '$.kind') FROM event_changes ORDER BY id")]
    assert kinds == ["split", "merge"]
    # A new report of the split-out story does not get pulled back automatically.
    service = ContentService(Store(store.path), settings())
    assert ids(service.view())[b.version] == split
