"""Time the reader's data path on synthetic judged materials in a temporary database.

    python scripts/bench_reader.py [materials=5000]

Not a CI gate: numbers depend on the machine. Nothing is sent over the network and the
personal database is not touched.
"""

import json
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from northing_signal.briefing.models import Assessment, Interaction, Material  # noqa: E402
from northing_signal.briefing.service import ContentService  # noqa: E402
from northing_signal.briefing.settings import ReaderSettings  # noqa: E402
from northing_signal.briefing.store import Store  # noqa: E402
from northing_signal.briefing.understand import POLICY_HASH  # noqa: E402

TOPICS = ["models", "agents", "research", "engineering", "products", "industry"]


def seed(store, total):
    base = datetime.now(timezone.utc) - timedelta(days=20)
    for i in range(total):
        at = (base + timedelta(minutes=5 * i)).isoformat()
        product = f"Product{i % 900} {i % 7}.{i % 5}"
        item = Material(id=f"m{i}", source_id=f"s{i % 45}", source_name=f"Source {i % 45}",
                        source_role="official", title=f"{product} released", url=f"https://example.org/{i}",
                        text=f"{product} is available now with {i} new features. " * 4,
                        published_at=at, captured_at=at, origin="synthetic")
        store.capture(item)
        if i % 5:  # 80% judged
            value = Assessment(relevance="ai", topic=TOPICS[i % 6], content_type="release", title=product,
                               summary="摘要" * 20, reason="原因", subject=f"Company{i % 300}", object=product,
                               action="release", event_key=f"p{i % 900}-{i % 7}-{i % 5}", significance=3,
                               novelty=3, usefulness=3, evidence="source_attributed",
                               claims=[dict(statement="已发布", quote=f"Product{i % 900}", kind="announcement")])
            store.judge(item.version, POLICY_HASH, value.model_dump(), "bench")


def median_ms(function, runs=5):
    samples = []
    for _ in range(runs):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples)


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    store = Store(Path(tempfile.mkdtemp()) / "bench.db")
    seed(store, total)
    service = ContentService(store, ReaderSettings(_env_file=None, root=ROOT))
    ids = count()
    events = service.view()["events"]
    for event in events[:300]:
        store.interact(Interaction(request_id=f"shown-{next(ids):06d}", event_id=event["id"],
                                   version=event["version"], kind="shown"))

    def after_change():
        event = events[1]
        store.interact(Interaction(request_id=f"useful-{next(ids):06d}", event_id=event["id"],
                                   version=event["version"], kind="useful"))
        started = time.perf_counter()
        service.view()
        return (time.perf_counter() - started) * 1000

    def interaction():
        service.record_interaction(Interaction(request_id=f"shown-{next(ids):06d}", event_id=events[0]["id"],
                                               version=events[0]["version"], kind="shown"))

    changed = statistics.median([after_change() for _ in range(5)])
    cached = median_ms(service.view)
    action = median_ms(interaction)
    snapshot = len(json.dumps(service.snapshot_view(), ensure_ascii=False).encode()) / 1024
    print(f"materials={total} events={len(events)} view_after_change={changed:.0f}ms "
          f"view_cached={cached:.0f}ms interaction={action:.0f}ms snapshot={snapshot:.0f}KB")


if __name__ == "__main__":
    main()
