"""Lenses on the same events: company moves, open source and community, research, policy and industry.

Pure: no model, network or database. Nothing regroups events or changes their membership; each
event only gains labels the reader filters by (2026-11-24, docs/plans/LENSES_PLAN.md).

A company's line holds what the company itself did: an event belongs to it when the event's
subject (who acts) names the company or one of its products, or when one of its reports comes
from the company's own source. Events that only mention the company in their object or title
(a customer building on its models, a third party's report about it) are listed as mentions.
"""

import re

RESEARCH, CORPORATE = "research", "corporate"
IMPLIED = {RESEARCH: "研究与安全", CORPORATE: "公司与政策"}
OPEN_SOURCE_KINDS = {"releases"}  # GitHub releases of open-source projects
LENSES = ("company", "community", "research", "policy")


def alias_pattern(alias):
    """English names match whole words and case; a name ending in a hyphen (GPT-) only checks
    its start. Chinese names match as written."""
    if not alias.isascii():
        return re.compile(re.escape(alias))
    start = r"(?<![A-Za-z0-9])"
    end = r"(?![A-Za-z0-9])" if alias[-1].isalnum() else ""
    return re.compile(start + re.escape(alias) + end)


class Names:
    """Find which keys a text names. A name inside a longer matched name does not count
    (Claude in Claude Code, Gemini in Gemini API)."""

    def __init__(self, entries):
        self.patterns = [(alias_pattern(alias), key) for key, aliases in entries for alias in aliases if alias]

    def __call__(self, text, leading=False):
        """leading: only a name that opens the text (a Chinese headline names who acts first)."""
        found = sorted(((m.start(), m.end(), key) for pattern, key in self.patterns
                        for m in pattern.finditer(text or "")), key=lambda f: f[0] - f[1])
        taken, keys = [], set()
        for start, end, key in found:
            if any(start < b and a < end for a, b in taken):
                continue
            taken.append((start, end))
            if not leading or start == 0:
                keys.add(key)
        return keys


class Lenses:
    def __init__(self, companies, sources=()):
        self.companies = companies
        self.names = {c["id"]: c["name"] for c in companies}
        self.company_names = Names([(c["id"], [*c["aliases"], *(a for p in c.get("products", []) for a in p["aliases"])])
                                    for c in companies])
        self.product_names = {c["id"]: Names([(p["id"], p["aliases"]) for p in c.get("products", [])])
                              for c in companies}
        self.source_company = {s: c["id"] for c in companies for s in c.get("sources", [])}
        self.open_source = {s["id"] for s in sources if s.get("kind") in OPEN_SOURCE_KINDS}

    def catalog(self):
        """Companies and their product groups, in the table's order, for the reader's filters."""
        return [{"id": c["id"], "name": c["name"],
                 "products": [{"id": p["id"], "name": p["name"]} for p in c.get("products", [])]
                 + [{"id": key, "name": name} for key, name in IMPLIED.items()]}
                for c in self.companies]

    def tag(self, event):
        """Add `companies` (actors, with `official` and `products`), `mentions` and `lenses`."""
        timeline = event.get("timeline", [])
        official = {c for t in timeline if (c := self.source_company.get(t.get("source_id")))}
        # The subject says who acts; a headline opening with a company says so too when the
        # subject names someone else ("Anthropic 完成 IPO", subject: its investors).
        actors = (self.company_names(event.get("subject")) | official
                  | self.company_names((event.get("title") or "").strip(), leading=True))
        if event.get("roundup"):
            actors = set()  # a digest of several stories is no company's move; it only mentions them
        named = " ".join([event.get("subject") or "", event.get("object") or "", event.get("title") or ""])
        implied = set()
        if event.get("content_type") == "research":
            implied.add(RESEARCH)
        if event.get("content_type") == "industry" or event.get("topic") == "industry":
            implied.add(CORPORATE)
        order = list(self.names)
        event["companies"] = [{"id": c, "official": c in official,
                               "products": sorted(self.product_names[c](named) | implied)}
                              for c in sorted(actors, key=order.index)]
        event["mentions"] = sorted(self.company_names(named) - actors, key=order.index)
        lenses = []
        if event["companies"]:
            lenses.append("company")
        if (any(t.get("source_id") in self.open_source or t.get("role") == "community"
                or t.get("content_kind") == "community_post" for t in timeline)):
            lenses.append("community")
        # Research: papers and research work, and tests run by others (a benchmark of coding
        # agents); a company testing its own product stays on its line only.
        if (event.get("topic") == "research" or event.get("content_type") == "research"
                or (event.get("content_type") == "test" and not event["companies"])):
            lenses.append("research")
        if event.get("topic") == "industry" or event.get("content_type") == "industry":
            lenses.append("policy")
        event["lenses"] = lenses
        return event
