"""A separate SQLite file: immutable material revisions and append-only reader actions."""

import hashlib
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .models import POLICY_EPOCH, Interaction, Material, Preferences, digest, now

LOCAL_USER = "local"  # owner of rows written before accounts existed, and of auth-off installs
TOKEN_PREFIX = "nst_"
CONTENT_TABLES = ("materials", "judgments")  # judgment_failures joins in migration 3
READER_TABLES = ("interactions", "preferences", "follows", "intent_assessments")
EVENT_TABLES = ("events", "event_members", "event_aliases")  # count as content: they regroup the briefing


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
    # Persistent event membership. Rows are filled from the projection's own grouping on the
    # first start (meta.events_backfilled), so existing event ids and reader actions keep matching.
    (4, """
    CREATE TABLE events (id TEXT PRIMARY KEY, data TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE event_members (
        material_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, method TEXT NOT NULL,
        score REAL, created_at TEXT NOT NULL);
    CREATE INDEX event_members_event ON event_members(event_id);
    CREATE TABLE event_aliases (old_id TEXT PRIMARY KEY, new_id TEXT NOT NULL);
    CREATE TABLE event_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, created_at TEXT NOT NULL);
    """ + "\n".join(_revision_triggers(t, "content_revision") for t in EVENT_TABLES)),
    # Briefing update history (manual and scheduled). The projection reads the latest completed
    # one: stories first captured in it are new, and "known" marked while reading it settles later.
    (5, """
    CREATE TABLE refreshes (
        id TEXT PRIMARY KEY, trigger TEXT NOT NULL, state TEXT NOT NULL,
        started_at TEXT NOT NULL, finished_at TEXT, data TEXT NOT NULL);
    CREATE INDEX refreshes_started ON refreshes(started_at);
    """ + _revision_triggers("refreshes", "reader_revision")),
    # Accounts (2026-11-23): each token is one user with its own preferences, actions, follows,
    # visits and briefing history. Content (materials, judgments, events) stays shared.
    # Existing personal rows belong to the "local" account; a token can claim it later.
    # Rebuilt tables lose their triggers with them: re-create.
    (6, f"""
    CREATE TABLE users (
        id TEXT PRIMARY KEY, token_hash TEXT UNIQUE, role TEXT NOT NULL, data TEXT NOT NULL,
        created_at TEXT NOT NULL, last_seen_at TEXT);
    INSERT INTO users VALUES ('{LOCAL_USER}', NULL, 'admin', '{{"name": "原始账号"}}',
                              strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), NULL);
    CREATE TABLE interactions_v6 (
        user_id TEXT NOT NULL, id TEXT NOT NULL, fingerprint TEXT NOT NULL, data TEXT NOT NULL,
        created_at TEXT NOT NULL, PRIMARY KEY(user_id, id));
    INSERT INTO interactions_v6 SELECT '{LOCAL_USER}', id, fingerprint, data, created_at
        FROM interactions ORDER BY rowid;
    DROP TABLE interactions;
    ALTER TABLE interactions_v6 RENAME TO interactions;
    CREATE INDEX interactions_kind ON interactions(user_id, json_extract(data, '$.kind'));
    CREATE TABLE follows_v6 (user_id TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
        PRIMARY KEY(user_id, id));
    INSERT INTO follows_v6 SELECT '{LOCAL_USER}', id, data FROM follows ORDER BY rowid;
    DROP TABLE follows;
    ALTER TABLE follows_v6 RENAME TO follows;
    CREATE TABLE visits_v6 (user_id TEXT NOT NULL, id TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(user_id, id));
    INSERT INTO visits_v6 SELECT '{LOCAL_USER}', id, created_at FROM visits ORDER BY rowid;
    DROP TABLE visits;
    ALTER TABLE visits_v6 RENAME TO visits;
    ALTER TABLE preferences ADD COLUMN user_id TEXT NOT NULL DEFAULT '{LOCAL_USER}';
    CREATE INDEX preferences_user ON preferences(user_id, id);
    ALTER TABLE snapshots ADD COLUMN user_id TEXT NOT NULL DEFAULT '{LOCAL_USER}';
    CREATE INDEX snapshots_user ON snapshots(user_id, created_at);
    ALTER TABLE follow_drafts ADD COLUMN user_id TEXT NOT NULL DEFAULT '{LOCAL_USER}';
    CREATE TABLE user_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, kind TEXT NOT NULL,
        created_at TEXT NOT NULL);
    CREATE INDEX user_usage_user ON user_usage(user_id, created_at);
    """ + _revision_triggers("interactions", "reader_revision")
        + "\n" + _revision_triggers("follows", "reader_revision")),
    # Model-judged relations between two events (2026-11-24): every decision is kept, so a pair is
    # never asked twice. Merges themselves go through event_members/aliases like a reader's.
    (7, """
    CREATE TABLE event_relations (
        a TEXT NOT NULL, b TEXT NOT NULL, relation TEXT NOT NULL, data TEXT NOT NULL,
        created_at TEXT NOT NULL, PRIMARY KEY(a, b));
    """),
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
        self._version_ids = (None, {})
        self._event_state = (None, None)
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

    def judgment(self, version):
        with self.connection() as db:
            row = db.execute("""SELECT data, model, epoch FROM judgments WHERE version=? AND epoch > 0
                                ORDER BY epoch DESC, rowid DESC LIMIT 1""", (version,)).fetchone()
        return {**json.loads(row["data"]), "model": row["model"], "epoch": row["epoch"]} if row else None

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

    def flag(self, key):
        with self.connection() as db:
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return bool(row and row["value"])

    def version_ids(self, revision=None):
        """Every stored material version -> its material id (older revisions included).

        revision: a content revision the caller just read, to skip reading it again.
        """
        revision = self.revision()[0] if revision is None else revision
        if self._version_ids[0] != revision:
            with self.connection() as db:
                self._version_ids = (revision, dict(db.execute("SELECT version, id FROM materials").fetchall()))
        return self._version_ids[1]

    def event_state(self, revision=None):
        """(material id -> event id, live event id -> frame, merged id -> successor).

        Read once per content revision; callers copy before changing anything.
        """
        revision = self.revision()[0] if revision is None else revision
        if self._event_state[0] != revision:
            with self.connection() as db:
                members = dict(db.execute("SELECT material_id, event_id FROM event_members").fetchall())
                events = {r["id"]: json.loads(r["data"]) for r in db.execute("SELECT id, data FROM events")}
                aliases = dict(db.execute("SELECT old_id, new_id FROM event_aliases").fetchall())
            self._event_state = (revision, (members, {k: v for k, v in events.items() if k not in aliases}, aliases))
        return self._event_state[1]

    def assign_events(self, rows, created, *, backfill=False):
        """Add memberships (never moving an assigned material) and the events they create."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.executemany("INSERT OR IGNORE INTO events VALUES (?, ?, ?)",
                           [(key, self.encoded(frame), now()) for key, frame in created.items()])
            db.executemany("INSERT OR IGNORE INTO event_members VALUES (?, ?, ?, ?, ?)",
                           [(material, event, method, score, now()) for material, event, method, score in rows])
            if backfill:
                db.execute("INSERT OR REPLACE INTO meta VALUES ('events_backfilled', 1)")

    def regroup(self, change, material_ids, target, frame=None, alias=None, method="manual"):
        """A reader's split or merge (or a model merge): move materials, retire an id, log it."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if frame is not None:
                db.execute("INSERT INTO events VALUES (?, ?, ?)", (target, self.encoded(frame), now()))
            db.executemany("UPDATE event_members SET event_id=?, method=?, score=NULL WHERE material_id=?",
                           [(target, method, material) for material in material_ids])
            if alias:
                db.execute("INSERT OR REPLACE INTO event_aliases VALUES (?, ?)", (alias, target))
                db.execute("UPDATE event_aliases SET new_id=? WHERE new_id=?", (target, alias))
            db.execute("INSERT INTO event_changes(data, created_at) VALUES (?, ?)", (self.encoded(change), now()))

    def relation_pairs(self):
        """Every pair of event ids the model has judged, as frozensets."""
        with self.connection() as db:
            return {frozenset((r["a"], r["b"])) for r in db.execute("SELECT a, b FROM event_relations")}

    def record_relations(self, rows):
        """rows: (event id, event id, relation, details)."""
        with self.connection() as db:
            db.executemany("INSERT OR IGNORE INTO event_relations VALUES (?, ?, ?, ?, ?)",
                           [(*sorted((a, b)), relation, self.encoded(data), now()) for a, b, relation, data in rows])

    def split_materials(self):
        """Materials a reader split out of an event: a model merge never undoes that."""
        with self.connection() as db:
            rows = db.execute("SELECT data FROM event_changes").fetchall()
        return {change["material"] for change in map(lambda r: json.loads(r["data"]), rows)
                if change.get("kind") == "split" and change.get("material")}

    def source_state(self, source_id, value):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO source_states VALUES (?, ?)",
                       (source_id, self.encoded(value)))

    def source_states(self):
        with self.connection() as db:
            return {r["id"]: json.loads(r["data"]) for r in db.execute("SELECT * FROM source_states")}

    # ---- accounts ------------------------------------------------------------------------------

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_user(self, role="user", *, claim=None, token=None):
        """A new account and its token, or a fresh token for an existing account (claim=id).

        token: chosen by the operator instead of generated (CLI only; may be easy to guess).
        Only the token's hash is stored: the token itself is returned once and never again.
        """
        if token is not None:
            token = token.strip()
            if not token or len(token) > 200 or any(c.isspace() for c in token):
                raise ValueError("令牌需为 1–200 个字符，且不能含空格")
        token = token or TOKEN_PREFIX + secrets.token_urlsafe(32)
        hashed = self.token_hash(token)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            owner = db.execute("SELECT id FROM users WHERE token_hash=?", (hashed,)).fetchone()
            if owner and owner["id"] != claim:
                raise ValueError(f"这个令牌已属于账号 {owner['id']}")
            if claim:
                if not db.execute("SELECT 1 FROM users WHERE id=?", (claim,)).fetchone():
                    raise LookupError("账号不存在")
                db.execute("UPDATE users SET token_hash=?, role=? WHERE id=?", (hashed, role, claim))
                key = claim
            else:
                key = secrets.token_hex(8)
                db.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, NULL)",
                           (key, hashed, role, self.encoded({}), now()))
        return self.user(key), token

    def user(self, key):
        with self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (key,)).fetchone()
        return self._user(row) if row else None

    def user_by_token(self, token):
        if not isinstance(token, str) or not token or len(token) > 200:
            return None
        with self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE token_hash=?", (self.token_hash(token),)).fetchone()
        return self._user(row) if row else None

    @staticmethod
    def _user(row):
        return {"id": row["id"], "role": row["role"], "created_at": row["created_at"],
                "last_seen_at": row["last_seen_at"], "has_token": row["token_hash"] is not None}

    def users(self):
        with self.connection() as db:
            return [self._user(r) for r in db.execute("SELECT * FROM users ORDER BY created_at")]

    def touch_user(self, key):
        with self.connection() as db:
            db.execute("UPDATE users SET last_seen_at=? WHERE id=?", (now(), key))

    def active_users(self, since):
        """Accounts seen since `since`, plus the local account when it has a reading history."""
        with self.connection() as db:
            rows = db.execute("SELECT id FROM users WHERE last_seen_at >= ? OR id=? ORDER BY last_seen_at DESC",
                              (since, LOCAL_USER)).fetchall()
        return [r["id"] for r in rows]

    def reserve_usage(self, user, kind, limit, since):
        """Count one quota use; raises when `limit` uses since `since` are already spent."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if limit is not None:
                used = db.execute("SELECT COUNT(*) FROM user_usage WHERE user_id=? AND created_at >= ?",
                                  (user, since)).fetchone()[0]
                if used >= limit:
                    raise ValueError("user_quota_reached")
            db.execute("INSERT INTO user_usage(user_id, kind, created_at) VALUES (?, ?, ?)", (user, kind, now()))

    def usage_count(self, user, since):
        with self.connection() as db:
            return db.execute("SELECT COUNT(*) FROM user_usage WHERE user_id=? AND created_at >= ?",
                              (user, since)).fetchone()[0]

    # ---- per-reader data (every method is scoped to one account) ------------------------------

    def preferences(self, user=LOCAL_USER):
        with self.connection() as db:
            row = db.execute("SELECT data FROM preferences WHERE user_id=? ORDER BY id DESC LIMIT 1",
                             (user,)).fetchone()
        return Preferences.model_validate_json(row["data"]) if row else Preferences()

    def save_preferences(self, value: Preferences, user=LOCAL_USER):
        with self.connection() as db:
            db.execute("INSERT INTO preferences(data, created_at, user_id) VALUES (?, ?, ?)",
                       (value.model_dump_json(), now(), user))

    def interact(self, value: Interaction, user=LOCAL_USER):
        payload = value.model_dump()
        fingerprint = digest(payload)
        with self.connection() as db:
            old = db.execute("SELECT fingerprint FROM interactions WHERE user_id=? AND id=?",
                             (user, value.request_id)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise ValueError("同一操作编号不能改变内容")
                return False
            if value.kind == "retract":
                target = db.execute("SELECT data FROM interactions WHERE user_id=? AND id=?",
                                    (user, value.retracts)).fetchone()
                old = json.loads(target["data"]) if target else None
                # Matched by version, not event id: a split or merge may have renamed the event since.
                if (not old or old["version"] != value.version
                        or old["kind"] in {"retract", "shown", "opened"}):
                    raise ValueError("找不到可撤回的操作")
            db.execute("INSERT INTO interactions (user_id, id, fingerprint, data, created_at) VALUES (?, ?, ?, ?, ?)",
                       (user, value.request_id, fingerprint, self.encoded(payload), now()))
        return True

    def interactions(self, kinds=None, user=LOCAL_USER):
        query, args = "SELECT * FROM interactions WHERE user_id=?", (user,)
        if kinds:
            # Same expression as the interactions_kind index.
            query += f" AND json_extract(data, '$.kind') IN ({','.join('?' * len(kinds))})"
            args += tuple(kinds)
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

    def visit(self, request_id, user=LOCAL_USER):
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO visits VALUES (?, ?, ?)", (user, request_id, now()))

    def last_visit(self, user=LOCAL_USER):
        with self.connection() as db:
            row = db.execute("SELECT created_at FROM visits WHERE user_id=? ORDER BY rowid DESC LIMIT 1",
                             (user,)).fetchone()
            return row["created_at"] if row else None

    def snapshots(self, key=None, user=LOCAL_USER):
        with self.connection() as db:
            if key:
                row = db.execute("SELECT data FROM snapshots WHERE id=? AND user_id=?", (key, user)).fetchone()
                return json.loads(row["data"]) if row else None
            # Older snapshots have no label fields: those come back as None.
            rows = db.execute("""SELECT id, created_at, json_extract(data, '$.snapshot_kind') AS kind,
                json_extract(data, '$.snapshot_trigger') AS trigger,
                json_extract(data, '$.headlines') AS headlines,
                json_array_length(data, '$.focus') + json_array_length(data, '$.radar') AS count
                FROM snapshots WHERE user_id=? ORDER BY rowid DESC LIMIT 20""", (user,)).fetchall()
            return [{"id": r["id"], "created_at": r["created_at"], "kind": r["kind"], "trigger": r["trigger"],
                     "headlines": json.loads(r["headlines"]) if r["headlines"] else [], "count": r["count"]}
                    for r in rows]

    def record_refresh(self, run):
        """Insert or update one briefing update; called when it starts and when it ends."""
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO refreshes VALUES (?, ?, ?, ?, ?, ?)",
                       (run["id"], run.get("trigger", "manual"), run["state"], run["started_at"],
                        run.get("finished_at"),
                        self.encoded({k: run.get(k) for k in ("analyzed", "failed", "errors", "snapshot_id")})))

    def refreshes(self, limit=20, completed=False):
        query = "SELECT * FROM refreshes" + (" WHERE state='completed'" if completed else "")
        with self.connection() as db:
            rows = db.execute(query + " ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [{**json.loads(r["data"]), **{k: r[k] for k in ("id", "trigger", "state", "started_at", "finished_at")}}
                for r in rows]

    def refresh_times(self):
        """Completion times of every completed update, oldest first."""
        with self.connection() as db:
            return [r[0] for r in db.execute("""SELECT finished_at FROM refreshes
                WHERE state='completed' AND finished_at IS NOT NULL ORDER BY finished_at""")]

    def last_refresh(self, completed=False):
        rows = self.refreshes(1, completed)
        return rows[0] if rows else None

    def receipts_today(self, since=None):
        with self.connection() as db:
            rows = db.execute("SELECT data FROM receipts WHERE created_at >= ?", (since or now()[:10],)).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def snapshot(self, value, user=LOCAL_USER):
        key = digest([now(), user, value])[:24]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_DAYS)).isoformat()
        with self.connection() as db:
            db.execute("INSERT INTO snapshots (id, data, created_at, user_id) VALUES (?, ?, ?, ?)",
                       (key, self.encoded(value), now(), user))
            # Keep each reader's newest SNAPSHOT_KEEP, and anything younger than SNAPSHOT_DAYS.
            db.execute("""DELETE FROM snapshots WHERE user_id=? AND created_at < ? AND rowid NOT IN (
                SELECT rowid FROM snapshots WHERE user_id=? ORDER BY rowid DESC LIMIT ?)""",
                       (user, cutoff, user, SNAPSHOT_KEEP))
        return key

    def follows(self, user=LOCAL_USER):
        with self.connection() as db:
            rows = [json.loads(row["data"]) for row in db.execute(
                "SELECT data FROM follows WHERE user_id=? ORDER BY rowid", (user,))]
        return [row for row in rows if not row.get("archived")]

    def all_follows(self):
        """Every account's current follows, each with its owner (for the tracking loop)."""
        with self.connection() as db:
            rows = [(r["user_id"], json.loads(r["data"])) for r in db.execute(
                "SELECT user_id, data FROM follows ORDER BY rowid")]
        return [{**row, "user_id": owner} for owner, row in rows if not row.get("archived")]

    def save_follow(self, value, user=LOCAL_USER, limit=12):
        name, query = value.name.strip(), (value.query or value.name).strip()
        if len(name) < 2 or len(query) < 2:
            raise ValueError("请输入至少两个字的话题或检索词")
        key = digest(query.casefold())[:24]
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM follows WHERE user_id=? AND id=?", (user, key)).fetchone()
            previous = json.loads(row["data"]) if row else None
            count = sum(not json.loads(row["data"]).get("archived")
                        for row in db.execute("SELECT data FROM follows WHERE user_id=?", (user,)))
            if count >= limit and (not previous or previous.get("archived")):
                raise ValueError(f"最多关注 {limit} 个话题，请先取消不再需要的话题")
            data = {"id": key, "created_at": now(), "last_checked": None, "last_status": "not_checked",
                    "material_ids": [], "seen_versions": [], **(previous or {}),
                    "name": name, "query": query, "active": value.active, "archived": False}
            db.execute("INSERT OR REPLACE INTO follows VALUES (?, ?, ?)", (user, key, self.encoded(data)))
        return data

    def update_follow(self, key, *, user=LOCAL_USER, **changes):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM follows WHERE user_id=? AND id=?", (user, key)).fetchone()
            if not row or json.loads(row["data"]).get("archived"):
                raise ValueError("这个关注话题不存在")
            data = {**json.loads(row["data"]), **changes}
            db.execute("UPDATE follows SET data=? WHERE user_id=? AND id=?", (self.encoded(data), user, key))
        return data

    def create_follow_draft(self, description, plan, follow_id=None, user=LOCAL_USER):
        previous = next((f for f in self.follows(user) if f["id"] == follow_id), None)
        if follow_id and not previous:
            raise ValueError("这个关注话题不存在")
        value = {"id": uuid4().hex, "description": description, "plan": plan.model_dump(),
                 "follow_id": follow_id, "base_plan_hash": previous.get("plan_hash") if previous else None,
                 "created_at": now(), "confirmed_at": None}
        with self.connection() as db:
            db.execute("INSERT INTO follow_drafts (id, data, user_id) VALUES (?, ?, ?)",
                       (value["id"], self.encoded(value), user))
        return value

    def confirm_follow(self, confirmation, user=LOCAL_USER, limit=12):
        plan = confirmation.plan.model_dump()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM follow_drafts WHERE id=? AND user_id=?",
                             (confirmation.draft_id, user)).fetchone()
            if not row:
                raise ValueError("追踪方案草稿不存在，请重新理解需求")
            draft = json.loads(row["data"])
            plan_hash = digest([draft["description"], plan])
            if draft["confirmed_at"]:
                if draft["plan_hash"] != plan_hash or draft["active"] != confirmation.active:
                    raise ValueError("这份草稿已确认，修改需求请重新生成方案")
                row = db.execute("SELECT data FROM follows WHERE user_id=? AND id=?", (user, draft["follow_id"])).fetchone()
                value = json.loads(row["data"]) if row else None
                if not value or value.get("archived") or value.get("plan_hash") != plan_hash:
                    raise ValueError("此确认已过期，请读取当前追踪方案")
                return value, False
            rows = [json.loads(r["data"]) for r in db.execute("SELECT data FROM follows WHERE user_id=?", (user,))]
            previous = next((r for r in rows if r["id"] == draft["follow_id"] and not r.get("archived")), None)
            if draft["follow_id"] and not previous:
                raise ValueError("原关注话题已取消，不能替换方案")
            if previous and draft.get("base_plan_hash") != previous.get("plan_hash"):
                raise ValueError("追踪方案已发生变化，请重新理解并确认")
            if not previous and sum(not r.get("archived") for r in rows) >= limit:
                raise ValueError(f"最多关注 {limit} 个话题，请先取消不再需要的话题")
            key = previous["id"] if previous else uuid4().hex[:24]
            value = {"id": key, "created_at": now(), "material_ids": [], **(previous or {}),
                     "name": plan["title"], "query": plan["searches"][0]["query"] if plan["searches"] else plan["title"],
                     "description": draft["description"], "intent_plan": plan, "plan_hash": plan_hash,
                     "confirmed_at": now(), "draft_id": draft["id"], "active": confirmation.active,
                     "archived": False, "last_checked": None, "last_status": "not_checked",
                     "seen_versions": [], "search_cursor": 0}
            draft.update(confirmed_at=value["confirmed_at"], follow_id=key, plan=plan,
                         plan_hash=plan_hash, active=confirmation.active)
            db.execute("INSERT OR REPLACE INTO follows VALUES (?, ?, ?)", (user, key, self.encoded(value)))
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
