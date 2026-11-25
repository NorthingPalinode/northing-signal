"""Export the retired 0.2 personal database (goals, runs, decisions, articles) to JSON Lines.

The old runtime was removed from the main branch; its code remains in the history
at commit 287e2c6. This script needs only the standard library,
opens the database read-only and never changes or deletes it.

    python scripts/export_legacy.py [--db .local/cfaw-news.db] [--out .local/legacy-export]
"""

import argparse
import base64
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def encode(value):
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode()}
    return value


def export(db, out):
    out.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        manifest = {"source": str(db), "source_sha256": hashlib.sha256(db.read_bytes()).hexdigest(),
                    "exported_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
        for table in tables:
            cursor = connection.execute(f'SELECT * FROM "{table}"')
            columns = [item[0] for item in cursor.description]
            path = out / f"{table}.jsonl"
            count = 0
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                for row in cursor:
                    record = {column: encode(value) for column, value in zip(columns, row)}
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
            manifest["tables"][table] = {"rows": count, "file": path.name,
                                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    finally:
        connection.close()
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=ROOT / ".local/cfaw-news.db")
    parser.add_argument("--out", type=Path, default=ROOT / ".local/legacy-export")
    args = parser.parse_args()
    if not args.db.is_file():
        sys.exit(f"Legacy database not found: {args.db}")
    manifest = export(args.db, args.out)
    for table, info in manifest["tables"].items():
        print(f"{table}: {info['rows']} rows")
    print(f"Exported to {args.out}")


if __name__ == "__main__":
    main()
