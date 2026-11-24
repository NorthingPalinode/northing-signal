"""Company lines and the other lenses: who acts, not who is mentioned (2026-11-24)."""

import json
from pathlib import Path

from northing_signal.briefing.lenses import Lenses, Names

ROOT = Path(__file__).resolve().parents[1]
COMPANIES = json.loads((ROOT / "data/companies.json").read_text("utf-8"))["companies"]
SOURCES = json.loads((ROOT / "data/briefing_sources.json").read_text("utf-8"))["sources"]
LENSES = Lenses(COMPANIES, SOURCES)


def event(title, subject="", object="", sources=(("decoder", "media"),), **changes):
    timeline = [{"source_id": s, "role": role, "content_kind": "feed_excerpt"} for s, role in sources]
    return LENSES.tag({"title": title, "subject": subject, "object": object, "topic": "models",
                       "content_type": "release", "timeline": timeline, **changes})


def ids(value):
    return [c["id"] for c in value["companies"]]


def test_the_acting_company_owns_the_event_and_mentions_stay_apart():
    launch = event("OpenAI 在 ChatGPT 中推出 GPT-6.2", subject="OpenAI", object="GPT-6.2")
    assert ids(launch) == ["openai"] and launch["companies"][0]["official"] is False
    assert launch["companies"][0]["products"] == ["api", "chatgpt"]
    customer = event("Richpanel 用 OpenAI 模型做客服", subject="Richpanel", object="OpenAI 模型")
    assert ids(customer) == [] and customer["mentions"] == ["openai"]
    assert "company" not in customer["lenses"]


def test_an_official_source_makes_its_company_an_actor():
    note = event("API changelog: new realtime voice", subject="", sources=[("openai", "official")])
    assert ids(note) == ["openai"] and note["companies"][0]["official"] is True
    hosted = event("百炼上架 deepseek-v4.1-flash", subject="阿里云百炼", object="DeepSeek V4.1 Flash",
                   sources=[("alibaba-model-studio", "official")])
    assert ids(hosted) == ["alibaba"] and hosted["mentions"] == ["deepseek"]


def test_a_longer_product_name_wins_over_the_name_inside_it():
    code = event("Claude Code 新增后台任务", subject="Anthropic", object="Claude Code")
    assert code["companies"][0]["products"] == ["claude-code"]
    model = event("Anthropic 发布 Claude Opus 5", subject="Anthropic", object="Claude Opus 5")
    assert model["companies"][0]["products"] == ["claude"]
    names = Names([("meta", ["Meta"])])
    assert names("metadata Metamorph") == set() and names("Meta 发布 Llama") == {"meta"}


def test_research_and_industry_are_lenses_and_company_product_groups():
    paper = event("DeepMind 新论文", subject="Google DeepMind", content_type="research", topic="research",
                  sources=[("deepmind", "research")])
    assert paper["lenses"] == ["company", "research"]
    assert "research" in paper["companies"][0]["products"]
    ceo = event("英伟达董事会恢复黄仁勋 CEO 职务", subject="英伟达", content_type="industry", topic="industry")
    assert ceo["lenses"] == ["company", "policy"] and ceo["companies"][0]["products"] == ["corporate"]
    rule = event("美国更新 AI 芯片出口管制", subject="美国商务部", content_type="industry", topic="industry")
    assert rule["lenses"] == ["policy"]


def test_open_source_releases_and_community_posts_are_the_community_lens():
    release = event("vLLM v0.32.0 发布", subject="vLLM", sources=[("vllm-release", "official")])
    assert release["lenses"] == ["community"]
    post = event("社区实测本地推理", sources=[("hn", "community")])
    assert "community" in post["lenses"]


def test_every_company_source_exists_and_the_catalog_adds_the_implied_groups():
    known = {s["id"] for s in SOURCES}
    assert all(s in known for c in COMPANIES for s in c["sources"])
    catalog = LENSES.catalog()
    assert catalog[0]["id"] == "openai"
    assert [p["id"] for p in catalog[0]["products"]][-2:] == ["research", "corporate"]


def test_a_headline_opening_with_the_company_names_the_actor():
    ipo = event("Anthropic完成史上最大IPO，投资方披露投资历程", subject="Notable Capital、GIC",
                content_type="industry", topic="industry")
    assert ids(ipo) == ["anthropic"]
    suit = event("加州总检察长起诉OpenAI", subject="加州总检察长", content_type="industry", topic="industry")
    assert ids(suit) == [] and suit["mentions"] == ["openai"]


def test_tests_by_others_are_research_and_a_company_testing_itself_is_not():
    bench = event("模拟职场测试：AI编程智能体完成不足一成", subject="研究团队", content_type="test", topic="agents")
    assert bench["lenses"] == ["research"]
    own = event("OpenAI 公布 GPT-6.2 自测成绩", subject="OpenAI", content_type="test")
    assert own["lenses"] == ["company"]


def test_a_roundup_of_several_stories_only_mentions_the_companies():
    digest = event("英伟达恢复黄仁勋CEO职务；智谱上线GLM-5.4", subject="英伟达、智谱", roundup=True)
    assert ids(digest) == [] and digest["mentions"] == ["nvidia", "zhipu"]
