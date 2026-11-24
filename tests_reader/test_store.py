import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from northing_signal.briefing import service as service_module
from northing_signal.briefing import store as store_module
from northing_signal.briefing.models import Interaction, Preferences
from northing_signal.briefing.service import ContentService
from northing_signal.briefing.store import SCHEMA_VERSION, Store
from northing_signal.briefing.understand import POLICY_HASH
from test_reader import assessment, material, settings

# The schema written by 0.3.0 before versioned migrations existed.
LEGACY_DDL = store_module.MIGRATIONS[0][1]


def legacy_database(path):
    with sqlite3.connect(path) as db:
        db.executescript("PRAGMA journal_mode=WAL;" + LEGACY_DDL)
        item = material()
        db.execute("INSERT INTO materials VALUES (?, ?, ?, ?)",
                   (item.version, item.id, item.captured_at, item.model_dump_json()))
        db.execute("INSERT INTO judgments VALUES (?, ?, ?, ?, ?)",
                   (item.version, POLICY_HASH, assessment().model_dump_json(), "fixture", item.captured_at))
        # Written by an earlier prompt: kept, but never shown as a current judgment.
        db.execute("INSERT INTO judgments VALUES (?, ?, ?, ?, ?)",
                   (item.version, "older-prompt", assessment(title="旧规则标题").model_dump_json(), "fixture",
                    item.captured_at))
        db.execute("INSERT INTO follows VALUES ('f1', '{\"id\": \"f1\", \"active\": false}')")
    return item


# Columns every schema version has; later migrations may add more.
COLUMNS = {"judgments": "version, policy, data, model, created_at", "follows": "id, data"}


def dump(path, tables):
    with sqlite3.connect(path) as db:
        return {t: db.execute(f"SELECT {COLUMNS.get(t, '*')} FROM {t} ORDER BY rowid").fetchall() for t in tables}


def test_existing_database_is_backed_up_and_upgraded_without_changing_rows(tmp_path):
    path = tmp_path / "reader.db"
    item = legacy_database(path)
    tables = ["materials", "judgments", "follows"]
    before = dump(path, tables)
    store = Store(path)
    assert dump(path, tables) == before
    assert dump(tmp_path / "reader.db.bak-v0", tables) == before
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == SCHEMA_VERSION
    assert [m.version for m in store.materials()] == [item.version]
    # Old rows wait for the running policy to adopt them; other prompts' rows stay hidden.
    assert store.judgments() == {}
    store.adopt_policy(POLICY_HASH)
    judgment = store.judgments()[item.version]
    assert judgment["epoch"] == 1 and judgment["title"] == assessment().title
    # Reopening an up-to-date database neither migrates again nor writes another backup.
    Store(path)
    assert sorted(p.name for p in tmp_path.iterdir() if ".bak-" in p.name) == ["reader.db.bak-v0"]


def test_new_database_needs_no_backup_and_newer_schema_is_refused(tmp_path):
    path = tmp_path / "reader.db"
    Store(path)
    assert not list(tmp_path.glob("*.bak-*"))
    with sqlite3.connect(path) as db:
        db.execute("UPDATE meta SET value=? WHERE key='schema_version'", (SCHEMA_VERSION + 1,))
    with pytest.raises(RuntimeError):
        Store(path)


def test_revisions_follow_writes_from_any_store_instance(tmp_path):
    first = Store(tmp_path / "reader.db")
    second = Store(first.path)  # e.g. the CLI writing while the server runs
    content, reader = first.revision()
    second.capture(material())
    assert first.revision() == (content + 1, reader)
    assert [m.id for m in first.materials()] == ["release"]
    second.save_preferences(Preferences(topics=["research"]))
    assert first.revision() == (content + 1, reader + 1)
    second.capture(material())  # identical revision: ignored, nothing changed
    assert first.revision() == (content + 1, reader + 1)


def test_projection_is_reused_until_stored_data_changes(tmp_path, monkeypatch):
    store = Store(tmp_path / "reader.db")
    item = material()
    store.capture(item)
    store.judge(item.version, POLICY_HASH, assessment().model_dump(), "fixture")
    service = ContentService(store, settings())
    calls = []
    original = service_module.project
    monkeypatch.setattr(service_module, "project", lambda *a, **k: calls.append(1) or original(*a, **k))
    first = service.view()  # also adopts the existing grouping once (event backfill)
    started = len(calls)
    assert started and service.view()["events"] == first["events"]
    assert len(calls) == started
    event = first["events"][0]
    store.interact(Interaction(request_id="useful-0001", event_id=event["id"],
                               version=event["version"], kind="useful"))
    assert service.view()["events"][0]["actions"][0]["kind"] == "useful"
    per_projection = len(calls) - started
    assert per_projection
    # Recency ranking must not freeze on an idle database.
    monkeypatch.setattr(service_module, "PROJECTION_MAX_AGE", 0)
    service.view()
    assert len(calls) == started + 2 * per_projection


def test_interaction_check_follows_the_material_event(tmp_path):
    store = Store(tmp_path / "reader.db")
    old = material(text="Atlas 2 is available. Free for research.")
    store.capture(old)
    store.judge(old.version, POLICY_HASH, assessment().model_dump(), "fixture")
    service = ContentService(store, settings())
    event = service.view()["events"][0]

    def act(request_id, version, kind="shown", event_id=event["id"], **extra):
        return service.record_interaction(Interaction(request_id=request_id, event_id=event_id,
                                                      version=version, kind=kind, **extra))

    assert act("shown-0001", old.version)
    assert act("saved-0001", old.version, "saved")
    with pytest.raises(LookupError):
        act("shown-0002", "missing-version")
    with pytest.raises(LookupError):
        act("shown-0003", old.version, event_id="missing-event")
    # A revised, not yet judged material hides the old version from the briefing; the saved copy stays actionable.
    store.capture(material(text="Atlas 2 is available. Free for research. Now with an API."))
    assert service.view()["saved_events"][0]["version"] == old.version
    assert act("opened-0001", old.version, "opened")
    assert act("retract-0001", old.version, "retract", retracts="saved-0001")
    # The material keeps its event, so its older revision stays addressable after unsaving.
    assert act("opened-0002", old.version, "opened")
    with pytest.raises(LookupError):
        act("opened-0003", old.version, event_id="another-event")


def test_snapshots_keep_recent_briefings_and_only_their_events(tmp_path):
    store = Store(tmp_path / "reader.db")
    for index in range(3):
        item = material(id=f"m{index}", url=f"https://example.org/{index}")
        store.capture(item)
        store.judge(item.version, POLICY_HASH, assessment(subject=f"S{index}", object=f"Object {index}",
                                                          event_key=f"e{index}").model_dump(), "fixture")
    service = ContentService(store, settings())
    value = service.snapshot_view()
    shown = set(value["focus"]) | set(value["radar"])
    assert shown and {e["id"] for e in value["events"]} == shown
    assert value["archive"] == [] and value["run"] is None and value["preferences"]

    old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    for index in range(store_module.SNAPSHOT_KEEP + 10):
        store.snapshot({"index": index})
    with store.connection() as db:
        db.execute("UPDATE snapshots SET created_at=?", (old,))
    store.snapshot(value)
    assert len(store.snapshots()) == 20  # the list endpoint still shows the latest 20
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == store_module.SNAPSHOT_KEEP
    # Recent snapshots are never pruned, however many there are.
    for index in range(store_module.SNAPSHOT_KEEP + 5):
        store.snapshot({"recent": index})
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == store_module.SNAPSHOT_KEEP + 6  # 65 new + the briefing above


def test_material_version_follows_copied_fields():
    item = material()
    revised = item.model_copy(update={"text": item.text + " Updated."})
    assert revised.version != item.version
    assert material().version == item.version
