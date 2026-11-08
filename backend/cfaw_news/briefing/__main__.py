"""One command surface. Offline inspection never creates a network event loop."""

import argparse
import asyncio
import json
from pathlib import Path

from .service import ContentService
from .settings import ReaderSettings
from .store import Store


async def analyze_pending(service, limit, reference=None):
    from .understand import POLICY_HASH, has_material
    store = service.store
    old = store.judgments(POLICY_HASH)
    candidates = sorted((m for m in store.materials() if m.version not in old and has_material(m)),
                        key=lambda m: m.published_at or m.captured_at, reverse=True)[:limit]
    if reference:
        versions = {json.loads(line)["version"] for line in reference.read_text("utf-8").splitlines() if line.strip()}
        candidates = [m for m in store.materials() if m.version not in old and m.version in versions and has_material(m)][:limit]
    for start in range(0, len(candidates), 2):
        batch = candidates[start:start + 2]
        try:
            result = await service.analyzer.batch(batch)
            for version, value in result.items():
                store.judge(version, POLICY_HASH, value, service.settings.llm_model)
            print(json.dumps({"attempted": start + len(batch), "accepted": len(result),
                              "failed": len(batch) - len(result), "total": len(candidates),
                              "titles": [v["title"] for v in result.values()]}, ensure_ascii=False), flush=True)
        except ValueError as error:
            print(json.dumps({"attempted": start, "error": str(error)}, ensure_ascii=False), flush=True)
            if str(error) == "daily_model_budget_reached":
                break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["collect", "enrich", "analyze", "status", "export", "evaluate", "discover", "recheck"])
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--database", default=None)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--split", choices=["all", "development", "holdout"], default="all")
    parser.add_argument("--query", default="AI agents")
    args = parser.parse_args()
    if not 0 <= args.limit <= 120:
        parser.error("limit must be between 0 and 120")
    settings = ReaderSettings()
    store = Store(args.database or settings.root / ".local/briefing-v2.db")
    if args.command == "evaluate":
        from .evaluate import compare
        if not args.reference:
            parser.error("evaluate requires --reference")
        print(json.dumps(compare(store, args.reference, args.split), ensure_ascii=False, indent=2))
        return
    if args.command == "export":
        for material in store.materials()[:args.limit]:
            print(material.model_dump_json(), flush=True)
        return
    service = ContentService(store, settings)
    if args.command == "recheck":
        from .models import Assessment
        from .understand import POLICY_HASH, validate
        path = settings.root / ".local/reader-quality/failed_outputs.jsonl"
        recovered = 0
        old = store.judgments(POLICY_HASH)
        for line in path.read_text("utf-8").splitlines() if path.exists() else []:
            for item in json.loads(line)["items"]:
                material = store.material(item["id"])
                if not material or item["id"] in old:
                    continue
                try:
                    result = validate(Assessment.model_validate(item["assessment"]), material)
                    store.judge(item["id"], POLICY_HASH, result.model_dump(), settings.llm_model)
                    old[item["id"]] = result.model_dump()
                    recovered += 1
                except ValueError:
                    continue
        print(json.dumps({"cached_outputs_revalidated": recovered, "new_model_calls": 0}))
    if args.command == "collect":
        from .collect import collect
        def progress(name, state):
            print(json.dumps({"source": name, **state}, ensure_ascii=False), flush=True)
        asyncio.run(collect(store, service.sources, min(args.limit, 20), progress))
    elif args.command == "enrich":
        from .collect import enrich
        asyncio.run(enrich(store, min(args.limit, 40), lambda row: print(json.dumps(row), flush=True)))
    elif args.command == "analyze":
        asyncio.run(analyze_pending(service, args.limit, args.reference))
    elif args.command == "discover":
        from .discover import discover
        found = asyncio.run(discover(store, args.query, min(args.limit, 6), settings=settings))
        print(json.dumps({"found": len(found), "titles": [m.title for m in found]}, ensure_ascii=False))
    view = service.view()
    print(json.dumps({"counts": view["counts"], "focus": len(view["focus"]), "radar": len(view["radar"]),
                      "source_health": {"ok": sum(s["state"]["status"] == "ok" for s in view["sources"]),
                                        "total": len(view["sources"]),
                                        "unavailable": [s["name"] for s in view["sources"] if s["state"]["status"] == "error"]},
                      "receipts": len(store.receipts_today())}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
