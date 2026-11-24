"""Accounts (2026-11-23): one token per reader, shared content, personal data."""

from fastapi.testclient import TestClient
from northing_signal.briefing.app import create_app
from northing_signal.briefing.models import Interaction, Preferences
from northing_signal.briefing.store import LOCAL_USER, Store
from northing_signal.briefing.understand import POLICY_HASH
from test_reader import assessment, material, settings

SITE = "http://testserver"


def app_with_story(tmp_path, **changes):
    store = Store(tmp_path / "reader.db")
    item = material()
    store.capture(item)
    store.judge(item.version, POLICY_HASH, assessment().model_dump(), "fixture")
    app = create_app(settings(reader_auth="token", **changes), store)
    return app, store


def register(client):
    response = client.post("/api/auth/register", headers={"origin": SITE})
    assert response.status_code == 201, response.text
    return response.json()


def as_(token):
    return {"authorization": f"Bearer {token}", "origin": SITE}


def test_a_new_token_signs_in_and_only_its_holder_gets_in(tmp_path):
    app, store = app_with_story(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/auth/session").json() == {"auth": "token", "signup": True, "user": None}
        assert client.get("/api/reader").status_code == 401
        created = register(client)
        token = created["token"]
        assert token.startswith("nst_") and len(token) > 40
        assert created["user"]["role"] == "user"
        # The cookie set on creation signs the visitor in at once.
        assert client.get("/api/reader").json()["account"]["id"] == created["user"]["id"]
        # Only the hash is stored.
        assert token not in (tmp_path / "reader.db").read_bytes().decode("utf-8", "ignore")
        client.cookies.clear()  # another browser
        assert client.get("/api/reader").status_code == 401
        assert client.post("/api/auth/login", json={"token": "nst_wrong"}, headers={"origin": SITE}).status_code == 401
        assert client.post("/api/auth/login", json={"token": token}, headers={"origin": SITE}).status_code == 200
        assert client.get("/api/reader").json()["account"]["id"] == created["user"]["id"]
        client.post("/api/auth/logout", headers={"origin": SITE})
        client.cookies.clear()  # the browser drops the expired cookie
        assert client.get("/api/reader").status_code == 401
        # A bearer header works too (scripts, other clients).
        assert client.get("/api/reader", headers=as_(token)).status_code == 200


def test_each_token_has_its_own_reading_data(tmp_path):
    app, store = app_with_story(tmp_path)
    (first, a), (second, b) = store.create_user(), store.create_user()
    one, two = first["id"], second["id"]
    with TestClient(app) as client:
        event = client.get("/api/reader", headers=as_(a)).json()["events"][0]
        saved = dict(request_id="saved-0001", event_id=event["id"], version=event["version"], kind="saved")
        assert client.post("/api/reader/interactions", json=saved, headers=as_(a)).json() == {"created": True}
        # The same request id from another reader is that reader's own action, not a conflict.
        assert client.post("/api/reader/interactions", json={**saved, "kind": "irrelevant"},
                           headers=as_(b)).json() == {"created": True}
        mine, theirs = client.get("/api/reader", headers=as_(a)).json(), client.get("/api/reader", headers=as_(b)).json()
        assert mine["events"][0]["saved"] and not mine["events"][0]["dismissed"]
        assert theirs["events"][0]["dismissed"] and not theirs["events"][0]["saved"]
        assert [e["id"] for e in mine["saved_events"]] == [event["id"]] and theirs["saved_events"] == []
        prefs = Preferences(topics=["research"]).model_dump()
        client.put("/api/reader/preferences", json=prefs, headers=as_(a))
        assert client.get("/api/reader", headers=as_(a)).json()["preferences"]["topics"] == ["research"]
        assert client.get("/api/reader", headers=as_(b)).json()["preferences"]["topics"] == Preferences().topics
        client.post("/api/reader/visits", json={"request_id": "visit-0001"}, headers=as_(a))
        assert client.get("/api/reader", headers=as_(a)).json()["last_visit"]
        assert not client.get("/api/reader", headers=as_(b)).json()["last_visit"]
    # Follows and briefing history are per reader as well.
    store.save_follow(type("F", (), {"name": "Atlas", "query": "Atlas", "active": False})(), user=one)
    assert [f["name"] for f in store.follows(one)] == ["Atlas"] and store.follows(two) == []
    key = store.snapshot({"focus": [], "radar": []}, one)
    assert store.snapshots(key, one) and store.snapshots(key, two) is None
    assert len(store.snapshots(user=one)) == 1 and store.snapshots(user=two) == []


def test_shared_corrections_are_for_admins(tmp_path):
    app, store = app_with_story(tmp_path)
    _, admin = store.create_user("admin")
    _, reader = store.create_user()
    with TestClient(app) as client:
        event = client.get("/api/reader", headers=as_(reader)).json()["events"][0]
        body = {"version": event["version"]}
        assert client.post(f"/api/reader/events/{event['id']}/split", json=body,
                           headers=as_(reader)).status_code == 403
        assert client.post("/api/reader/materials/x/retry", headers=as_(reader)).status_code == 403
        # The admin passes the check (the one-report event cannot be split: a 409, not a 403).
        assert client.post(f"/api/reader/events/{event['id']}/split", json=body,
                           headers=as_(admin)).status_code == 409
        assert client.get("/api/reader", headers=as_(admin)).json()["account"]["limits"]["requests_per_day"] is None


def test_ordinary_readers_have_daily_request_and_topic_limits(tmp_path):
    app, store = app_with_story(tmp_path, reader_user_requests_per_day=2, reader_user_follow_limit=1)
    started = []
    app.state.content.start_discovery = lambda body, user: started.append(user) or {"id": "run", "user_id": user}
    with TestClient(app) as client:
        user = register(client)["user"]["id"]
        search = {"query": "Atlas", "channels": ["web"]}
        assert client.post("/api/reader/discover", json=search, headers={"origin": SITE}).status_code == 202
        assert client.post("/api/reader/discover", json=search, headers={"origin": SITE}).status_code == 202
        refused = client.post("/api/reader/discover", json=search, headers={"origin": SITE})
        assert refused.status_code == 429 and "2 次" in refused.json()["detail"]
        assert started == [user, user]
        assert client.get("/api/reader").json()["account"]["limits"]["requests_today"] == 2
        store.save_follow(type("F", (), {"name": "Atlas", "query": "Atlas", "active": False})(), user=user)
        full = client.post("/api/reader/follows/interpret", json={"description": "关注 Nova 模型的发布与测试"},
                           headers={"origin": SITE})
        assert full.status_code == 409 and "最多关注 1 个" in full.json()["detail"]


def test_other_readers_runs_show_as_busy_without_their_query(tmp_path):
    app, store = app_with_story(tmp_path)
    service = app.state.content
    run = service.new_run("discovery", "discovering", query="我的私人检索", channels=["web"], user_id="someone")
    assert service.visible_run(run, "someone")["query"] == "我的私人检索"
    shown = service.visible_run(run, "another")
    assert shown["kind"] == "other" and "query" not in shown and "channels" not in shown
    refresh = service.new_run("refresh", "collecting", user_id="someone")
    assert service.visible_run(refresh, "another")["kind"] == "refresh"
    assert "user_id" not in service.visible_run(refresh, "another")


def test_changes_from_other_sites_are_refused(tmp_path):
    app, _ = app_with_story(tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/auth/register", headers={"origin": "https://evil.example"}).status_code == 403
        assert client.post("/api/auth/register", headers={"origin": SITE}).status_code == 201


def test_signup_can_be_closed_and_is_rate_limited(tmp_path):
    app, _ = app_with_story(tmp_path, reader_signup=False)
    with TestClient(app) as client:
        assert client.get("/api/auth/session").json()["signup"] is False
        assert client.post("/api/auth/register", headers={"origin": SITE}).status_code == 403
    app, _ = app_with_story(tmp_path / "limited", reader_signups_per_hour=2)
    with TestClient(app) as client:
        assert [client.post("/api/auth/register", headers={"origin": SITE}).status_code
                for _ in range(3)] == [201, 201, 429]


def test_the_owner_claims_the_data_written_before_accounts(tmp_path):
    store = Store(tmp_path / "reader.db")
    item = material()
    store.capture(item)
    store.judge(item.version, POLICY_HASH, assessment().model_dump(), "fixture")
    store.interact(Interaction(request_id="saved-0001", event_id="e", version=item.version, kind="saved"))
    user, token = store.create_user("admin", claim=LOCAL_USER)
    assert user["id"] == LOCAL_USER and user["role"] == "admin" and user["has_token"]
    app = create_app(settings(reader_auth="token"), store)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"token": token}, headers={"origin": SITE})
        view = client.get("/api/reader").json()
        assert view["account"]["id"] == LOCAL_USER and view["events"][0]["saved"]
    # A fresh claim replaces the token: the old one stops working.
    _, newer = store.create_user("admin", claim=LOCAL_USER)
    assert store.user_by_token(token) is None and store.user_by_token(newer)["id"] == LOCAL_USER


def test_personal_install_without_accounts_still_works(tmp_path):
    store = Store(tmp_path / "reader.db")
    with TestClient(create_app(settings(), store)) as client:  # reader_auth="off"
        session = client.get("/api/auth/session").json()
        assert session["auth"] == "off" and session["user"]["id"] == LOCAL_USER
        assert client.get("/api/reader").status_code == 200


def test_an_update_saves_each_active_readers_own_briefing(tmp_path, monkeypatch):
    import asyncio

    from northing_signal.briefing.models import RefreshRequest

    async def nothing(*args, **kwargs):
        return []
    monkeypatch.setattr("northing_signal.briefing.service.collect", nothing)
    monkeypatch.setattr("northing_signal.briefing.service.enrich", nothing)
    app, store = app_with_story(tmp_path)
    (first, _), (second, _), (idle, _) = store.create_user(), store.create_user(), store.create_user()
    store.touch_user(first["id"])
    store.touch_user(second["id"])
    store.save_preferences(Preferences(topics=["research"], exploration=False), second["id"])
    service = app.state.content

    async def scenario():
        run = service.start(RefreshRequest(), user=first["id"])
        await service.task
        return run
    run = asyncio.run(scenario())
    assert run["state"] == "completed"
    mine, theirs = store.snapshots(user=first["id"]), store.snapshots(user=second["id"])
    assert len(mine) == 1 and len(theirs) == 1 and store.snapshots(user=idle["id"]) == []
    assert run["snapshot_id"] == mine[0]["id"]
    # Each snapshot is that reader's own ranking: a models story is not in a research-only briefing.
    assert mine[0]["count"] == 1 and theirs[0]["count"] == 0


def test_operators_may_choose_tokens_but_never_share_one(tmp_path):
    import pytest
    store = Store(tmp_path / "reader.db")
    admin, token = store.create_user("admin", claim=LOCAL_USER, token="rootGiotto")
    assert token == "rootGiotto" and store.user_by_token("rootGiotto")["id"] == LOCAL_USER
    reader, _ = store.create_user(token="user1")
    assert store.user_by_token("user1")["id"] == reader["id"] and store.user_by_token("user1")["role"] == "user"
    with pytest.raises(ValueError, match="已属于账号"):
        store.create_user(token="user1")
    with pytest.raises(ValueError, match="空格"):
        store.create_user(token="user 2")
    # Claiming again with the same chosen token is a no-op, not a conflict.
    assert store.create_user("admin", claim=LOCAL_USER, token="rootGiotto")[1] == "rootGiotto"
    assert store.user_by_token("") is None and store.user_by_token("nobody") is None


def test_site_defaults_to_new_york_and_each_reader_may_switch_to_beijing(tmp_path):
    """2026-11-24: the owner is in the US with business in China."""
    from northing_signal.briefing.settings import ReaderSettings
    assert ReaderSettings.model_fields["reader_timezone"].default == "America/New_York"
    app, store = app_with_story(tmp_path, reader_timezone="America/New_York")
    (_, a), (_, b) = store.create_user(), store.create_user()
    with TestClient(app) as client:
        zone = client.get("/api/reader", headers=as_(a)).json()["timezone"]
        assert zone["zone"] == zone["site"] == "America/New_York"
        assert [o["id"] for o in zone["options"]] == ["America/New_York", "Asia/Shanghai"]
        prefs = client.get("/api/reader", headers=as_(a)).json()["preferences"]
        saved = client.put("/api/reader/preferences", json={**prefs, "timezone": "Asia/Shanghai"}, headers=as_(a))
        assert saved.status_code == 200 and saved.json()["timezone"]["zone"] == "Asia/Shanghai"
        # Only this reader's view changes; the site schedule stays on New York time.
        other = client.get("/api/reader", headers=as_(b)).json()
        assert other["timezone"]["zone"] == "America/New_York"
        assert other["schedule"]["next"] == saved.json()["schedule"]["next"]
        refused = client.put("/api/reader/preferences", json={**prefs, "timezone": "Mars/Olympus"}, headers=as_(a))
        assert refused.status_code == 422
