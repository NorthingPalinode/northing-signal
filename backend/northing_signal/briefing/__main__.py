"""One command surface. Offline inspection never creates a network event loop."""

import argparse
import asyncio
import json
from pathlib import Path

from .models import day_start
from .service import ContentService
from .settings import ReaderSettings
from .store import Store


async def analyze_pending(service, limit, reference=None):
    """Same selection, batching and backoff as an in-app update, without collecting."""
    candidates = sorted(service.store.materials(), key=lambda m: m.published_at or m.captured_at, reverse=True)
    if reference:
        versions = {json.loads(line)["version"] for line in reference.read_text("utf-8").splitlines() if line.strip()}
        candidates = [m for m in candidates if m.version in versions]
    run = service.new_run("analyze", "understanding")
    await service.analyze(candidates, run, limit)
    print(json.dumps({k: run.get(k) for k in ("total", "analyzed", "failed", "errors")}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["collect", "enrich", "analyze", "status", "export", "evaluate", "discover", "recheck", "publish", "token", "users"])
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--database", default=None)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--split", choices=["all", "development", "holdout"], default="all")
    parser.add_argument("--query", default="AI agents")
    parser.add_argument("--out", default=None, help="publish: output directory (default READER_PUBLISH_DIR)")
    parser.add_argument("--admin", action="store_true", help="token: the account may do shared corrections")
    parser.add_argument("--claim", default=None,
                        help="token: issue a new token for this existing account id (the old one stops working)")
    parser.add_argument("--claim-local", action="store_true",
                        help="token: take over the data written before accounts existed")
    parser.add_argument("--token", default=None,
                        help="token: use this value instead of a generated one (short values are easy to guess)")
    args = parser.parse_args()
    if not 0 <= args.limit <= 120:
        parser.error("limit must be between 0 and 120")
    settings = ReaderSettings()
    store = Store(args.database or settings.root / ".local/briefing-v2.db")
    if args.command == "token":
        from .store import LOCAL_USER
        claim = LOCAL_USER if args.claim_local else args.claim
        try:
            user, token = store.create_user("admin" if args.admin else "user", claim=claim, token=args.token)
        except (LookupError, ValueError) as error:
            parser.error(str(error))
        result = {"user_id": user["id"], "role": user["role"], "token": token,
                  "note": "令牌只显示这一次，请妥善保存；丢失后用 --claim 账号ID 重新签发。"}
        if args.token and len(args.token.strip()) < 24:
            result["warning"] = "这个令牌很短，容易被猜到；公网部署前请换成自动生成的令牌。"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == "users":
        print(json.dumps(store.users(), ensure_ascii=False, indent=2))
        return
    if args.command == "evaluate":
        from .evaluate import compare
        from .understand import POLICY_HASH
        store.adopt_policy(POLICY_HASH)
        if not args.reference:
            parser.error("evaluate requires --reference")
        print(json.dumps(compare(store, args.reference, args.split), ensure_ascii=False, indent=2))
        return
    if args.command == "export":
        for material in store.materials()[:args.limit]:
            print(material.model_dump_json(), flush=True)
        return
    service = ContentService(store, settings)
    if args.command == "publish":
        try:
            result = service.publish_digest(args.out)
        except ValueError as error:
            parser.error(str(error))
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return
    if args.command == "recheck":
        from .models import Assessment
        from .understand import POLICY_HASH, validate
        path = settings.root / ".local/reader-quality/failed_outputs.jsonl"
        recovered = 0
        old = store.judgments()
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
                      "receipts": len(store.receipts_today(day_start(settings.reader_timezone)))},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
