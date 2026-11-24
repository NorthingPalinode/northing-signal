"""Which materials the model reads first, and judging again (2026-11-24: Nvidia's CEO story)."""

import asyncio
from datetime import datetime, timedelta, timezone

from northing_signal.briefing.service import ContentService
from northing_signal.briefing.store import Store
from northing_signal.briefing.triage import PER_SOURCE, outlets, triage
from northing_signal.briefing.understand import PROMPT
from test_reader import assessment, material, settings

NOW = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)
LAST_UPDATE = (NOW - timedelta(hours=1)).isoformat()


def item(key, source, title, hours=2, role="media"):
    at = (NOW - timedelta(hours=hours)).isoformat()
    return material(id=key, url=f"https://example.org/{key}", source_id=source, source_name=source,
                    source_role=role, title=title, published_at=at, captured_at=at, text=title + ". Details.")


def test_a_story_several_outlets_report_is_read_before_newer_single_reports():
    huang = [item("tc", "techcrunch-ai", "Nvidia reverses course and brings Jensen Huang back as CEO", hours=15),
             item("dec", "decoder", "Nvidia tried life without Jensen Huang and it lasted two weeks", hours=16),
             item("ls", "latent-space", "Jensen Is Back! Nvidia reinstates Huang as CEO", hours=2)]
    newer = [item(f"card{i}", "hf-qwen", f"Qwen/Qwen4-{i}B-Instruct", hours=1, role="official") for i in range(3)]
    papers = [item(f"p{i}", "arxiv-recent", f"Robotic Manipulation with Diffusion Policy variant {i}", hours=1,
                   role="research") for i in range(3)]
    blog = item("blog", "simon", "datasette-charts 0.1a0", hours=1, role="author")
    old = item("old", "openai", "Combatting adversarial distillation", hours=24 * 5, role="official")
    order = [m.id for m in triage([old, blog, *papers, *newer, *huang], NOW, [LAST_UPDATE])]
    assert set(order[:3]) == {"tc", "dec", "ls"}  # three outlets, older than the cards and papers
    assert order.index("blog") < min(order.index(f"card{i}") for i in range(3))  # articles before catalogs
    assert order[-1] == "old"  # no longer news: last
    # Papers sharing jargon do not count as coverage of each other.
    assert not any(outlets(papers, NOW).values())


def test_judged_materials_count_as_coverage_but_take_no_place_and_no_outlet_floods_the_front():
    covered = item("tc", "techcrunch-ai", "Jensen Huang scheduled to testify in Senate following reinstatement")
    judged = item("dec", "decoder", "Jensen Huang to testify in Senate after reinstatement as Nvidia CEO")
    flood = [item(f"tc{i}", "techcrunch-ai", f"Startup {i} raises seed round", hours=1) for i in range(PER_SOURCE + 2)]
    other = item("q", "qbitai", "某公司发布新模型", hours=3)
    order = triage([*flood, other, covered, judged], NOW, [LAST_UPDATE], done={judged.version})
    ids = [m.id for m in order]
    assert ids[0] == "tc" and ids[-1] == "dec"  # covered by a judged report: first; the judged one: last
    techcrunch_before_other = sum(1 for m in order[:ids.index("q")] if m.source_id == "techcrunch-ai")
    assert techcrunch_before_other == PER_SOURCE


def test_ai_industry_news_counts_and_old_judgments_can_be_redone(tmp_path):
    assert "CEO、创始人任免" in PROMPT and "出口管制" in PROMPT
    store = Store(tmp_path / "reader.db")
    story = item("tc", "techcrunch-ai", "Nvidia reverses course and brings Jensen Huang back as CEO")
    store.capture(story)
    store.judge(story.version, "older-policy", assessment(relevance="unrelated", topic="industry").model_dump(),
                "fixture")
    service = ContentService(store, settings(llm_mode="compatible"))

    async def batch(materials):
        return {m.version: assessment(relevance="ai", topic="industry", significance=4).model_dump()
                for m in materials}
    service.analyzer.batch = batch
    run = service.new_run("analyze", "understanding")
    asyncio.run(service.analyze([story], run, 10))
    assert run["analyzed"] == 0  # already judged: an ordinary update leaves it
    asyncio.run(service.analyze([story], run, 10, again=True))
    assert run["analyzed"] == 1
    latest = store.judgments()[story.version]
    assert latest["relevance"] == "ai" and latest["significance"] == 4
