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
    candidates = service.triaged()
    if reference:
        versions = {json.loads(line)["version"] for line in reference.read_text("utf-8").splitlines() if line.strip()}
        candidates = [m for m in candidates if m.version in versions]
    run = service.new_run("analyze", "understanding")
    await service.analyze(candidates, run, limit)
    print(json.dumps({k: run.get(k) for k in ("total", "analyzed", "failed", "errors")}, ensure_ascii=False), flush=True)


async def rejudge(service, days, limit):
    """Judge again, under the current prompt, recent materials it would now read differently:
    those judged unrelated or uncertain (2026-11-24: AI industry news such as Nvidia's CEO
    change was marked unrelated). Most widely reported and newest first."""
    from datetime import datetime, timedelta, timezone

    from .engine import stamp
    since = datetime.now(timezone.utc) - timedelta(days=days)
    judged = service.store.judgments()
    chosen = [m for m in service.triaged()
              if judged.get(m.version, {}).get("relevance") in {"unrelated", "uncertain"}
              and (stamp(m.published_at) or stamp(m.captured_at) or since) > since]
    run = service.new_run("analyze", "understanding")
    await service.analyze(chosen, run, limit, again=True)
    after = service.store.judgments()
    now_ai = sum(after[m.version].get("relevance") == "ai" for m in chosen[:limit] if m.version in after)
    print(json.dumps({"candidates": len(chosen), "judged": run["analyzed"], "failed": run["failed"],
                      "now_ai": now_ai, "errors": run["errors"]}, ensure_ascii=False), flush=True)


def label(store, gold, n):
    """Ask, one material at a time, whether it is worth reading. Resumable; answers saved at once."""
    from .calibrate import DECISIONS, label_row, read_labels, sample
    gold.parent.mkdir(parents=True, exist_ok=True)
    queue_path = gold.with_name(gold.stem + "-queue.json")
    done = {r["version"] for r in read_labels(gold)}
    queue = json.loads(queue_path.read_text("utf-8")) if queue_path.exists() else []
    if not [v for v in queue if v not in done]:
        queue = [m.version for m in sample(store.materials(), store.judgments(), n, done)]
        queue_path.write_text(json.dumps(queue), "utf-8")
    todo = [v for v in queue if v not in done]
    print(f"待标注 {len(todo)} 条（已标注 {len(done)} 条）。只按“这条值不值得我花时间读”判断，"
          "不用管同一件事是否已经选过别的报道。AI 的判断不显示，避免先入为主。\n")
    for index, version in enumerate(todo, 1):
        material = store.material(version)
        if not material:
            continue
        excerpt = " ".join(material.text.split())[:600]
        print(f"[{index}/{len(todo)}] {material.title}")
        print(f"    {material.source_name}（{material.source_role}） · {material.published_at or '发布时间未知'}")
        print(f"    {material.url}")
        print(f"    {excerpt}{'…' if len(material.text) > 600 else ''}\n")
        while True:
            answer = input("值得读吗？ y 值得 / n 不值得 / e 两可 / k 跳过 / q 保存退出：").strip().lower()
            if answer in DECISIONS or answer in {"k", "q"}:
                break
        if answer == "q":
            break
        if answer == "k":
            continue
        with gold.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(label_row(material, DECISIONS[answer]), ensure_ascii=False) + "\n")
        print()
    labels = read_labels(gold)
    counts = {k: sum(r["decision"] == k for r in labels) for k in ("read", "skip", "either")}
    print(f"已保存到 {gold}：值得 {counts['read']}、不值得 {counts['skip']}、两可 {counts['either']}。"
          "下一步运行 calibrate。")


def run_calibration(store, gold, split, settings):
    """Score the stored judgments on your labels; no model calls."""
    from datetime import datetime, timezone

    from .calibrate import calibrate, read_labels
    labels = read_labels(gold)
    if not labels:
        raise SystemExit(f"没有找到标注：{gold}。先运行 label。")
    current = {"official": settings.reader_threshold_official, "other": settings.reader_threshold_other}
    report = calibrate(labels, store.judgments(), current, split)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = gold.with_name(f"calibration-{split}-{stamp}.json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    now = report["current"]
    print(f"样本 {report['labels']} 条（两可 {report['either_excluded']} 条不计），划分：{split}")
    print(f"当前门槛 官方 {current['official']} / 其他 {current['other']}："
          f"查准 {now['precision']} · 查全 {now['recall']} · F1 {now['f1']} · "
          f"已判断覆盖 {now['coverage']} · 完整准确率 {now['complete_accuracy']}")
    for name, label in (("official", "官方与研究来源"), ("other", "媒体、作者与社区")):
        best = report["suggested"].get(name)
        if best:
            print(f"{label}：F1 最高的门槛 {best['threshold']}（F1 {best['f1']}，{best['labels']} 条标注）")
    errors = now["errors"]
    if errors:
        print(f"\n判错 {len(errors)} 条（前 10 条）：")
        for row in errors[:10]:
            kind = {"false_positive": "不该选却选了", "false_negative": "该选没选上", "not_judged": "还没整理"}[row["type"]]
            print(f"  [{kind}] {row['title'][:50]}（{row['source']}，分数 {row.get('score', '-')}）")
    print(f"\n完整报告：{path}")
    print("先在 development 上调整，最后用 --split holdout 检查一次；门槛写进 .env 的 "
          "READER_THRESHOLD_OFFICIAL / READER_THRESHOLD_OTHER。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["collect", "enrich", "analyze", "status", "export", "evaluate", "discover", "recheck", "publish", "token", "users",
                                            "label", "calibrate", "relate", "rejudge"])
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
    parser.add_argument("--gold", type=Path, default=None,
                        help="label/calibrate: your labels (default .local/reader-quality/gold.jsonl)")
    parser.add_argument("--n", type=int, default=120, help="label: how many materials to sample (default 120)")
    parser.add_argument("--days", type=int, default=14, help="rejudge: how far back to look (default 14)")
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
    if args.command in {"label", "calibrate"}:
        gold = args.gold or settings.root / ".local/reader-quality/gold.jsonl"
        if args.command == "label":
            label(store, gold, args.n)
        else:
            run_calibration(store, gold, args.split, settings)
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
    if args.command == "rejudge":
        asyncio.run(rejudge(service, args.days, args.limit))
        return
    if args.command == "relate":
        # Judge up to --limit candidate pairs of recent events now (each update does 24 itself).
        run = service.new_run("relate", "grouping")
        asyncio.run(service.relate_events(run, args.limit))
        print(json.dumps({"relations": run.get("relations"), "errors": run["errors"]}, ensure_ascii=False))
        return
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
