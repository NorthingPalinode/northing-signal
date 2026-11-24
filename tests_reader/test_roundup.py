"""Roundups never lead or name an event, and minor fixes are not corrections (2026-11-24)."""

import asyncio
from datetime import datetime, timedelta, timezone

from northing_signal.briefing.engine import is_roundup, project
from northing_signal.briefing.models import Preferences
from northing_signal.briefing.relate import POLICY, candidates
from northing_signal.briefing.service import ContentService
from northing_signal.briefing.store import Store
from northing_signal.briefing.understand import POLICY_HASH
from test_reader import assessment, material, settings

NOW = datetime.now(timezone.utc)


def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat()


def report(key, source, title, hours=3, **judged):
    item = material(id=key, url=f"https://example.org/{key}", source_id=source, source_name=source,
                    source_role="media", title=title, published_at=ago(hours), captured_at=ago(hours),
                    text=title + ". Details of the story follow here.")
    frame = dict(subject="英伟达", object="黄仁勋复任 CEO", event_key="nvidia-ceo-reinstated", topic="industry",
                 content_type="industry", action="other", title=title)
    return item, assessment(**{**frame, **judged}).model_dump()


def test_roundup_titles():
    def titled(title):
        return material(id="x", title=title)
    assert is_roundup(titled("黄仁勋重返英伟达，市值涨31.48%；马斯克：出租算力比自研更赚钱；新模型更爱「爆粗口」"))
    assert is_roundup(titled("OpenAI 首席科学家：AI 最早明年加速进化｜极客早知道"))
    assert is_roundup(titled("[AINews] GPT-6.2 Astra is better and cheaper;"))
    assert is_roundup(titled("October sponsors-only newsletter"))
    # One story with a section label, or a trailing semicolon: not a roundup.
    assert not is_roundup(titled("科研成果 | 方承煜同学成果被NeurIPS2026接收｜NeurIPS 2026"))
    assert not is_roundup(titled("Nvidia reverses course and brings Jensen Huang back as CEO"))


def test_a_roundup_neither_leads_nor_names_the_event_and_alone_stays_out_of_focus():
    brief, brief_judged = report("gp", "geekpark", "黄仁勋重返英伟达，市值涨31.48%；马斯克称出租算力比自研更赚钱",
                                 significance=4, novelty=3, usefulness=3)
    single, single_judged = report("ars", "ars-ai", "英伟达董事会恢复黄仁勋CEO与董事长职务",
                                   significance=3, novelty=2, usefulness=2)
    morning, morning_judged = report("lp", "leiphone", "英伟达恢复黄仁勋CEO职务；智谱上线GLM-5.4；蚂蚁开源医疗模型家族",
                                     subject="雷峰网", object="早报合集", event_key="leiphone-morning",
                                     significance=4, novelty=3, usefulness=2)
    result = project([brief, single, morning], {brief.version: brief_judged, single.version: single_judged,
                                                morning.version: morning_judged}, Preferences())
    events = {e["source_id"]: e for e in result["events"]}
    story = events["ars-ai"]  # led by the single report though the roundup scored higher
    assert story["title"] == "英伟达董事会恢复黄仁勋CEO与董事长职务" and story["report_count"] == 2
    assert not story["roundup"] and story["id"] in result["focus"]
    alone = events["leiphone"]
    assert alone["roundup"] and alone["id"] not in result["focus"] and alone["id"] in result["radar"]
    # Not offered to the relation model either.
    assert all(alone["id"] not in {a["id"], b["id"]} for _, a, b in candidates(result["events"], clock=NOW))


def test_a_minor_bug_fix_release_is_not_a_pinned_correction():
    fix, minor = report("fix", "simon", "llm-gemini 0.38.1 修复推理档", subject="llm-gemini",
                        object="llm-gemini 0.38.1", event_key="llm-gemini-0-38-1", action="correction",
                        topic="models", significance=1, novelty=1, usefulness=2)
    real, major = report("cor", "openai", "OpenAI 更正 Atlas 2 基准成绩", subject="OpenAI", object="Atlas 2 基准",
                         event_key="atlas-2-correction", action="correction", topic="models", significance=3)
    events = {e["source_id"]: e for e in project([fix, real], {fix.version: minor, real.version: major},
                                                 Preferences())["events"]}
    assert not events["simon"]["protected"] and not events["simon"]["qualified"]
    assert events["openai"]["protected"]


def test_a_roundup_answer_from_an_older_prompt_is_asked_once_more(tmp_path):
    store = Store(tmp_path / "reader.db")
    items = [report("ars", "ars-ai", "英伟达董事会恢复黄仁勋CEO与董事长职务", hours=5),
             report("tc", "techcrunch-ai", "黄仁勋复任英伟达CEO，科技高管表态支持", hours=3,
                    object="黄仁勋复任与高管表态", event_key="huang-support")]
    for item, judged in items:
        store.capture(item)
        store.judge(item.version, POLICY_HASH, judged, "fixture")
    service = ContentService(store, settings(llm_mode="compatible"))
    a, b = (e["id"] for e in service.neutral_events())
    store.record_relations([(a, b, "ROUNDUP", {"reason": "old prompt"})])
    calls = []

    async def fake(prompt, payload, validator, *, purpose, maximum):
        calls.append(payload)
        return validator({"items": [{"id": row["id"], "relation": "SAME_OCCURRENCE"} for row in payload]})
    service.analyzer.request_json = fake
    run = service.new_run("refresh", "grouping")
    asyncio.run(service.relate_events(run))
    assert len(calls) == 1 and run["relations"] == {"checked": 1, "merged": 1}
    assert len(service.neutral_events()) == 1
    # The new answer replaced the old one and kept it; it is not asked a third time.
    stale = []
    assert store.relation_pairs(recheck=lambda relation, data: stale.append(data) or
                                data.get("policy") != POLICY) == {frozenset((a, b))}
    assert stale[0]["previous"]["relation"] == "ROUNDUP" and stale[0]["previous"]["reason"] == "old prompt"
    asyncio.run(service.relate_events(service.new_run("refresh", "grouping")))
    assert len(calls) == 1
