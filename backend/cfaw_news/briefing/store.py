"""A separate SQLite file: immutable material revisions and append-only reader actions."""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .models import POLICY_EPOCH, Interaction, Material, Preferences, digest, now

CONTENT_TABLES = ("materials", "judgments")  # judgment_failures joins in migration 3
READER_TABLES = ("interactions", "preferences", "follows", "intent_assessments")


def _revision_triggers(table, key):
    return "\n".join(
        f"CREATE TRIGGER IF NOT EXISTS {table}_{event.lower()}_revision AFTER {event} ON {table} "
        f"BEGIN UPDATE meta SET value = value + 1 WHERE key = '{key}'; END;"
        for event in ("INSERT", "UPDATE", "DELETE"))


# Applied in order inside one transaction each; the file is copied before upgrading existing data.
MIGRATIONS = [
    (1, """
    CREATE TABLE IF NOT EXISTS materials (
        version TEXT PRIMARY KEY, id TEXT NOT NULL, captured_at TEXT NOT NULL,
        data TEXT NOT NULL, UNIQUE(id, version));
    CREATE TABLE IF NOT EXISTS judgments (
        version TEXT NOT NULL, policy TEXT NOT NULL, data TEXT NOT NULL,
        model TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(version, policy));
    CREATE TABLE IF NOT EXISTS source_states (
        id TEXT PRIMARY KEY, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS interactions (
        id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, data TEXT NOT NULL,
        created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS snapshots (
        id TEXT PRIMARY KEY, data TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS visits (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS follows (
        id TEXT PRIMARY KEY, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS follow_drafts (
        id TEXT PRIMARY KEY, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS intent_assessments (
        plan_hash TEXT NOT NULL, version TEXT NOT NULL, data TEXT NOT NULL,
        PRIMARY KEY(plan_hash, version));
    """),
    (2, """
    CREATE INDEX IF NOT EXISTS materials_id ON materials(id);
    CREATE INDEX IF NOT EXISTS receipts_created ON receipts(created_at);
    CREATE INDEX IF NOT EXISTS interactions_kind ON interactions(json_extract(data, '$.kind'));
    INSERT OR IGNORE INTO meta VALUES ('content_revision', 0), ('reader_revision', 0);
    """ + "\n".join(_revision_triggers(t, "content_revision") for t in CONTENT_TABLES)
        + "\n" + "\n".join(_revision_triggers(t, "reader_revision") for t in READER_TABLES)),
    # Judgments gain an epoch (rows start at 0 until the running policy adopts them), and
    # failed judgments get a backoff ledger. Rebuilding judgments drops its triggers: re-create.
    (3, """
    CREATE TABLE judgments_v3 (
        version TEXT NOT NULL, policy TEXT NOT NULL, epoch INTEGER NOT NULL DEFAULT 0,
        data TEXT NOT NULL, model TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(version, policy, epoch));
    INSERT INTO judgments_v3 (version, policy, epoch, data, model, created_at)
        SELECT version, policy, 0, data, model, created_at FROM judgments ORDER BY rowid;
    DROP TABLE judgments;
    ALTER TABLE judgments_v3 RENAME TO judgments;
    CREATE INDEX judgments_version ON judgments(version);
    CREATE TABLE judgment_failures (
        version TEXT NOT NULL, epoch INTEGER NOT NULL, data TEXT NOT NULL,
        PRIMARY KEY(version, epoch));
    """ + _revision_triggers("judgments", "content_revision")
        + "\n" + _revision_triggers("judgment_failures", "content_revision")),
]
SCHEMA_VERSION = MIGRATIONS[-1][0]
SNAPSHOT_KEEP, SNAPSHOT_DAYS = 60, 90
# A material that fails judgment waits 1 h, then 6 h; the third failure stops automatic retries.
# Quote/number mismatches tend to repeat with the same prompt, so they start at the second step.
RETRY_DELAYS = (3600, 6 * 3600)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
CONTENT_FAILURES = {"quote_not_in_original", "unsupported_number", "condition_not_in_original"}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._materials = (None, [])
        self.migrate()

    def migrate(self):
        existed = self.path.exists() and self.path.stat().st_size > 0
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
            row = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            current = row["value"] if row else 0
            if current > SCHEMA_VERSION:
                raise RuntimeError(f"数据库版本 {current} 比当前程序（{SCHEMA_VERSION}）新，请升级程序")
            if existed and current < SCHEMA_VERSION:
                backup = self.path.with_name(f"{self.path.name}.bak-v{current}")
                if not backup.exists():
                    target = sqlite3.connect(backup)
                    try:
                        db.backup(target)
                        target.execute("PRAGMA journal_mode=DELETE")  # one self-contained file
                    finally:
                        target.close()
            for version, script in MIGRATIONS:
                if version > current:
                    db.executescript("BEGIN;" + script + f"""
                        INSERT OR REPLACE INTO meta VALUES ('schema_version', {version}); COMMIT;""")

    @contextmanager
    def connection(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=15)
            try:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys=ON")
                with db:
                    yield db
            finally:
                db.close()

    def revision(self):
        """Cheap change counters maintained by triggers, so other processes' writes count too."""
        with self.connection() as db:
            rows = dict(db.execute("SELECT key, value FROM meta WHERE key LIKE '%_revision'").fetchall())
        return rows.get("content_revision", 0), rows.get("reader_revision", 0)

    @staticmethod
    def encoded(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def capture(self, material: Material):
        with self.connection() as db:
            old = db.execute("SELECT data FROM materials WHERE version=?", (material.version,)).fetchone()
            if old:
                fixed = {"origin", "source_role", "source_id", "url"}
                previous = json.loads(old["data"])
                if any(previous[k] != getattr(material, k) for k in fixed):
                    raise ValueError("immutable_material_metadata_conflict")
            return db.execute("INSERT OR IGNORE INTO materials VALUES (?, ?, ?, ?)",
                              (material.version, material.id, material.captured_at,
                               material.model_dump_json())).rowcount == 1

    def materials(self):
        """Latest revision of each material; parsed once per content revision."""
        revision = self.revision()[0]
        cached_revision, cached = self._materials
        if cached_revision != revision:
            with self.connection() as db:
                rows = db.execute("""SELECT data FROM (
                    SELECT data, ROW_NUMBER() OVER (PARTITION BY id ORDER BY rowid DESC) AS n
                    FROM materials) WHERE n=1""").fetchall()
            cached = [Material.model_validate_json(row["data"]) for row in rows]
            self._materials = (revision, cached)
        return list(cached)

    def material(self, version):
        with self.connection() as db:
            row = db.execute("SELECT data FROM materials WHERE version=?", (version,)).fetchone()
        return Material.model_validate_json(row["data"]) if row else None

    def materials_by_versions(self, versions):
        versions = list(versions)
        with self.connection() as db:
            rows = [row for start in range(0, len(versions), 500) for row in db.execute(
                f"SELECT data FROM materials WHERE version IN ({','.join('?' * len(versions[start:start + 500]))})",
                versions[start:start + 500])]
        return [Material.model_validate_json(row["data"]) for row in rows]

    def judgments(self):
        """Newest adopted judgment per material version (highest epoch, then latest written)."""
        with self.connection() as db:
            rows = db.execute("""SELECT version, data, model, epoch FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY version ORDER BY epoch DESC, rowid DESC) AS n
                FROM judgments WHERE epoch > 0) WHERE n=1""").fetchall()
        return {r["version"]: {**json.loads(r["data"]), "model": r["model"], "epoch": r["epoch"]} for r in rows}

    def judge(self, version, policy, value, model, epoch=None):
        epoch = POLICY_EPOCH if epoch is None else epoch
        with self.connection() as db:
            db.execute("""INSERT OR IGNORE INTO judgments (version, policy, epoch, data, model, created_at)
                          VALUES (?, ?, ?, ?, ?, ?)""", (version, policy, epoch, self.encoded(value), model, now()))
            db.execute("DELETE FROM judgment_failures WHERE version=? AND epoch<=?", (version, epoch))

    def adopt_policy(self, policy, epoch=None):
        """Judgments written before epochs existed count for the policy that wrote them."""
        epoch = POLICY_EPOCH if epoch is None else epoch
        with self.connection() as db:
            db.execute("UPDATE judgments SET epoch=? WHERE policy=? AND epoch=0", (epoch, policy))

    def record_failure(self, version, code, epoch=None):
        epoch = POLICY_EPOCH if epoch is None else epoch
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM judgment_failures WHERE version=? AND epoch=?",
                             (version, epoch)).fetchone()
            attempts = (json.loads(row["data"])["attempts"] if row else 0) + 1
            if code in CONTENT_FAILURES:
                attempts = max(attempts, 2)
            gave_up = attempts >= MAX_ATTEMPTS
            retry_at = None if gave_up else (
                datetime.now(timezone.utc) + timedelta(seconds=RETRY_DELAYS[attempts - 1])).isoformat()
            value = {"attempts": attempts, "code": code, "at": now(), "retry_at": retry_at, "gave_up": gave_up}
            db.execute("INSERT OR REPLACE INTO judgment_failures VALUES (?, ?, ?)",
                       (version, epoch, self.encoded(value)))
        return value

    def failures(self, epoch=None):
        epoch = POLICY_EPOCH if epoch is None else epoch
        with self.connection() as db:
            return {r["version"]: json.loads(r["data"]) for r in db.execute(
                "SELECT version, data FROM judgment_failures WHERE epoch=?", (epoch,))}

    def clear_failure(self, version):
        with self.connection() as db:
            return db.execute("DELETE FROM judgment_failures WHERE version=?", (version,)).rowcount > 0

    def source_state(self, source_id, value):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO source_states VALUES (?, ?)",
                       (source_id, self.encoded(value)))

    def source_states(self):
        with self.connection() as db:
            return {r["id"]: json.loads(r["data"]) for r in db.execute("SELECT * FROM source_states")}

    def preferences(self):
        with self.connection() as db:
            row = db.execute("SELECT data FROM preferences ORDER BY id DESC LIMIT 1").fetchone()
        return Preferences.model_validate_json(row["data"]) if row else Preferences()

    def save_preferences(self, value: Preferences):
        with self.connection() as db:
            db.execute("INSERT INTO preferences(data, created_at) VALUES (?, ?)",
                       (value.model_dump_json(), now()))

    def interact(self, value: Interaction):
        payload = value.model_dump()
        fingerprint = digest(payload)
        with self.connection() as db:
            old = db.execute("SELECT fingerprint FROM interactions WHERE id=?", (value.request_id,)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise ValueError("同一操作编号不能改变内容")
                return False
            if value.kind == "retract":
                target = db.execute("SELECT data FROM interactions WHERE id=?", (value.retracts,)).fetchone()
                old = json.loads(target["data"]) if target else None
                if (not old or old["event_id"] != value.event_id or old["version"] != value.version
                        or old["kind"] in {"retract", "shown", "opened"}):
                    raise ValueError("找不到可撤回的操作")
            db.execute("INSERT INTO interactions VALUES (?, ?, ?, ?)",
                       (value.request_id, fingerprint, self.encoded(payload), now()))
        return True

    def interactions(self, kinds=None):
        query, args = "SELECT * FROM interactions", ()
        if kinds:
            # Same expression as the interactions_kind index.
            query += f" WHERE json_extract(data, '$.kind') IN ({','.join('?' * len(kinds))})"
            args = tuple(kinds)
        with self.connection() as db:
            return [{**json.loads(r["data"]), "at": r["created_at"]}
                    for r in db.execute(query + " ORDER BY rowid", args)]

    def receipt(self, value):
        with self.connection() as db:
            db.execute("INSERT INTO receipts(data, created_at) VALUES (?, ?)", (self.encoded(value), now()))

    def reserve_request(self, value, requests_limit, tokens_limit, since=None):
        """since: start of the accounting day as a UTC ISO string (default: the UTC day)."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = ([json.loads(r["data"]) for r in db.execute(
                "SELECT data FROM receipts WHERE created_at >= ?", (since or now()[:10],))]
                if requests_limit is not None or tokens_limit is not None else [])
            if ((requests_limit is not None and len(rows) >= requests_limit)
                    or (tokens_limit is not None and
                        sum(r.get("charged_tokens", 0) for r in rows) + value["charged_tokens"] > tokens_limit)):
                raise ValueError("daily_model_budget_reached")
            cursor = db.execute("INSERT INTO receipts(data, created_at) VALUES (?, ?)",
                                (self.encoded(value), now()))
            return cursor.lastrowid

    def finish_request(self, receipt_id, value):
        with self.connection() as db:
            db.execute("UPDATE receipts SET data=? WHERE id=?", (self.encoded(value), receipt_id))

    def visit(self, request_id):
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO visits VALUES (?, ?)", (request_id, now()))

    def last_visit(self):
        with self.connection() as db:
            row = db.execute("SELECT created_at FROM visits ORDER BY rowid DESC LIMIT 1").fetchone()
            return row["created_at"] if row else None

    def snapshots(self, key=None):
        with self.connection() as db:
            if key:
                row = db.execute("SELECT data FROM snapshots WHERE id=?", (key,)).fetchone()
                return json.loads(row["data"]) if row else None
            return [{"id": r["id"], "created_at": r["created_at"]}
                    for r in db.execute("SELECT id, created_at FROM snapshots ORDER BY rowid DESC LIMIT 20")]

    def receipts_today(self, since=None):
        with self.connection() as db:
            rows = db.execute("SELECT data FROM receipts WHERE created_at >= ?", (since or now()[:10],)).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def snapshot(self, value):
        key = digest([now(), value])[:24]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_DAYS)).isoformat()
        with self.connection() as db:
            db.execute("INSERT INTO snapshots VALUES (?, ?, ?)", (key, self.encoded(value), now()))
            # Keep the newest SNAPSHOT_KEEP, and anything younger than SNAPSHOT_DAYS.
            db.execute("""DELETE FROM snapshots WHERE created_at < ? AND rowid NOT IN (
                SELECT rowid FROM snapshots ORDER BY rowid DESC LIMIT ?)""", (cutoff, SNAPSHOT_KEEP))
        return key

    def follows(self):
        with self.connection() as db:
            rows = [json.loads(row["data"]) for row in db.execute("SELECT data FROM follows ORDER BY rowid")]
        return [row for row in rows if not row.get("archived")]

    def save_follow(self, value):
        name, query = value.name.strip(), (value.query or value.name).strip()
        if len(name) < 2 or len(query) < 2:
            raise ValueError("请输入至少两个字的话题或检索词")
        key = digest(query.casefold())[:24]
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM follows WHERE id=?", (key,)).fetchone()
            previous = json.loads(row["data"]) if row else None
            count = sum(not json.loads(row["data"]).get("archived")
                        for row in db.execute("SELECT data FROM follows"))
            if count >= 12 and (not previous or previous.get("archived")):
                raise ValueError("最多关注 12 个话题，请先取消不再需要的话题")
            data = {"id": key, "created_at": now(), "last_checked": None, "last_status": "not_checked",
                    "material_ids": [], "seen_versions": [], **(previous or {}),
                    "name": name, "query": query, "active": value.active, "archived": False}
            db.execute("INSERT OR REPLACE INTO follows VALUES (?, ?)", (key, self.encoded(data)))
        return data

    def update_follow(self, key, **changes):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM follows WHERE id=?", (key,)).fetchone()
            if not row or json.loads(row["data"]).get("archived"):
                raise ValueError("这个关注话题不存在")
            data = {**json.loads(row["data"]), **changes}
            db.execute("UPDATE follows SET data=? WHERE id=?", (self.encoded(data), key))
        return data

    def create_follow_draft(self, description, plan, follow_id=None):
        previous = next((f for f in self.follows() if f["id"] == follow_id), None)
        if follow_id and not previous:
            raise ValueError("这个关注话题不存在")
        value = {"id": uuid4().hex, "description": description, "plan": plan.model_dump(),
                 "follow_id": follow_id, "base_plan_hash": previous.get("plan_hash") if previous else None,
                 "created_at": now(), "confirmed_at": None}
        with self.connection() as db:
            db.execute("INSERT INTO follow_drafts VALUES (?, ?)", (value["id"], self.encoded(value)))
        return value

    def confirm_follow(self, confirmation):
        plan = confirmation.plan.model_dump()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM follow_drafts WHERE id=?", (confirmation.draft_id,)).fetchone()
            if not row:
                raise ValueError("追踪方案草稿不存在，请重新理解需求")
            draft = json.loads(row["data"])
            plan_hash = digest([draft["description"], plan])
            if draft["confirmed_at"]:
                if draft["plan_hash"] != plan_hash or draft["active"] != confirmation.active:
                    raise ValueError("这份草稿已确认，修改需求请重新生成方案")
                row = db.execute("SELECT data FROM follows WHERE id=?", (draft["follow_id"],)).fetchone()
                value = json.loads(row["data"]) if row else None
                if not value or value.get("archived") or value.get("plan_hash") != plan_hash:
                    raise ValueError("此确认已过期，请读取当前追踪方案")
                return value, False
            rows = [json.loads(r["data"]) for r in db.execute("SELECT data FROM follows")]
            previous = next((r for r in rows if r["id"] == draft["follow_id"] and not r.get("archived")), None)
            if draft["follow_id"] and not previous:
                raise ValueError("原关注话题已取消，不能替换方案")
            if previous and draft.get("base_plan_hash") != previous.get("plan_hash"):
                raise ValueError("追踪方案已发生变化，请重新理解并确认")
            if not previous and sum(not r.get("archived") for r in rows) >= 12:
                raise ValueError("最多关注 12 个话题，请先取消不再需要的话题")
            key = previous["id"] if previous else uuid4().hex[:24]
            value = {"id": key, "created_at": now(), "material_ids": [], **(previous or {}),
                     "name": plan["title"], "query": plan["searches"][0]["query"] if plan["searches"] else plan["title"],
                     "description": draft["description"], "intent_plan": plan, "plan_hash": plan_hash,
                     "confirmed_at": now(), "draft_id": draft["id"], "active": confirmation.active,
                     "archived": False, "last_checked": None, "last_status": "not_checked",
                     "seen_versions": [], "search_cursor": 0}
            draft.update(confirmed_at=value["confirmed_at"], follow_id=key, plan=plan,
                         plan_hash=plan_hash, active=confirmation.active)
            db.execute("INSERT OR REPLACE INTO follows VALUES (?, ?)", (key, self.encoded(value)))
            db.execute("UPDATE follow_drafts SET data=? WHERE id=?", (self.encoded(draft), draft["id"]))
        return value, True

    def intent_assessments(self, plan_hash):
        with self.connection() as db:
            return {r["version"]: json.loads(r["data"]) for r in db.execute(
                "SELECT version,data FROM intent_assessments WHERE plan_hash=?", (plan_hash,))}

    def assess_intent(self, plan_hash, values):
        with self.connection() as db:
            db.executemany("INSERT OR IGNORE INTO intent_assessments VALUES (?, ?, ?)",
                           [(plan_hash, version, self.encoded(value)) for version, value in values.items()])
