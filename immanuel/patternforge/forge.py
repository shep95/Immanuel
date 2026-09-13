"""Deterministic pattern miners + a forge pass over the collected corpus.

Each miner turns raw observations into an abstract mechanism (a Universal Pattern
Object), assigns evidence + a deterministic confidence, tests it against a
falsifier, scopes it, and stores it. Re-running updates the same pattern id
(stable), letting confidence and lifecycle evolve as more data arrives.

Non-AI: every number here is a count/ratio over the database.
"""
from __future__ import annotations

import math
from collections import defaultdict
from urllib.parse import urlparse

from .ontology import PatternObject, stable_id


def _confidence(dominant: int, total: int) -> float:
    """Consistency (dominant share) tempered by support (log of total)."""
    if total <= 0:
        return 0.0
    ratio = dominant / total
    support = min(1.0, math.log10(total + 1) / 2.0)  # ~1.0 around 100 obs
    return round(ratio * (0.5 + 0.5 * support), 4)


# --------------------------------------------------------------------- miners
def mine_topic_category(db) -> list[PatternObject]:
    """Within a topic, which epistemic category dominates? (bias mechanism)."""
    by_topic: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in db.agg_topic_category():
        by_topic[r["topic"]][r["category"] or "unknown"] += r["c"]
    out = []
    for topic, cats in by_topic.items():
        total = sum(cats.values())
        if total < 3:
            continue
        dom_cat, dom_n = max(cats.items(), key=lambda kv: kv[1])
        conf = _confidence(dom_n, total)
        p = PatternObject(
            pattern_id=stable_id("topic_category", topic),
            name=f"topic '{topic}' skews {dom_cat}",
            family="topic_category", domain="knowledge", scope="domain",
            trigger=f"a page is classified under topic '{topic}'",
            mechanism=f"pages about '{topic}' are published as {dom_cat} "
                      f"({dom_n}/{total} = {dom_n/total:.0%})",
            function=f"predict a new '{topic}' page is most likely {dom_cat}",
            invariant=f"'{topic}' -> {dom_cat} plurality",
            evidence=[f"{c}: {n}" for c, n in sorted(cats.items(), key=lambda x: -x[1])],
            evidence_count=total, confidence=conf,
            tests=[f"sample new '{topic}' pages; check {dom_cat} remains the plurality"],
            falsifiers=[f"another category overtakes {dom_cat} for '{topic}'"],
            success_conditions=[f"{dom_cat} share stays >= 40%"],
            failure_modes=["topic keyword drift mislabels pages"],
        )
        out.append(p)
    return out


def mine_company_topic(db) -> list[PatternObject]:
    """Which topic does a company predominantly publish? (focus mechanism)."""
    by_company: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in db.agg_company_topic():
        by_company[r["company"]][r["topic"]] += r["c"]
    out = []
    for company, topics in by_company.items():
        total = sum(topics.values())
        if total < 3:
            continue
        dom_topic, dom_n = max(topics.items(), key=lambda kv: kv[1])
        conf = _confidence(dom_n, total)
        out.append(PatternObject(
            pattern_id=stable_id("company_topic", company),
            name=f"{company} focuses on {dom_topic}",
            family="company_topic", domain="organizational", scope="domain",
            trigger=f"a page belongs to company '{company}'",
            mechanism=f"'{company}' output concentrates on '{dom_topic}' "
                      f"({dom_n}/{total} = {dom_n/total:.0%})",
            function=f"route/anticipate '{company}' content as '{dom_topic}'",
            invariant=f"{company} -> {dom_topic} concentration",
            evidence=[f"{t}: {n}" for t, n in sorted(topics.items(), key=lambda x: -x[1])[:8]],
            evidence_count=total, confidence=conf,
            tests=[f"new '{company}' pages keep concentrating on '{dom_topic}'"],
            falsifiers=[f"'{company}' output diversifies away from '{dom_topic}'"],
            success_conditions=[f"'{dom_topic}' share stays the plurality"],
        ))
    return out


def mine_secret_exposure(db) -> list[PatternObject]:
    """Domains that repeatedly leak credentials publicly (exposure mechanism)."""
    out = []
    for r in db.agg_secret_domains():
        total = r["c"]
        if total < 2:
            continue
        conf = _confidence(total, total)  # recurrence itself is the signal
        out.append(PatternObject(
            pattern_id=stable_id("secret_exposure", r["domain"] or "?"),
            name=f"{r['domain']} publicly exposes credentials",
            family="secret_exposure", domain="security", scope="domain",
            trigger=f"crawling pages on '{r['domain']}'",
            mechanism=f"'{r['domain']}' publishes secrets in page/source "
                      f"({total} findings across {r['types']} type(s))",
            function="prioritize this host for secret-exposure monitoring",
            invariant="repeated public secret exposure on one host",
            evidence=[f"findings={total}", f"distinct_types={r['types']}"],
            evidence_count=total, confidence=conf,
            epistemic_status="observation",
            tests=["re-scan the host; confirm findings persist / are not placeholders"],
            falsifiers=["all findings were placeholders/examples (false positives)"],
            failure_modes=["regex false positives", "sample/demo keys"],
            transfer_constraints=["host-specific; do not generalize across TLDs"],
        ))
    return out


def mine_domain_breadth(db, top_n: int = 30) -> list[PatternObject]:
    """Hub domains that yield disproportionate data (breadth mechanism)."""
    rows = sorted(db.agg_domain_items(), key=lambda r: -r["c"])
    total_all = sum(r["c"] for r in rows) or 1
    out = []
    for r in rows[:top_n]:
        if r["c"] < 5:
            continue
        share = r["c"] / total_all
        conf = _confidence(r["c"], total_all)
        out.append(PatternObject(
            pattern_id=stable_id("domain_breadth", r["domain"]),
            name=f"{r['domain']} is a data hub",
            family="domain_breadth", domain="network", scope="domain",
            trigger="allocating crawl attention",
            mechanism=f"'{r['domain']}' accounts for {r['c']} items "
                      f"({share:.1%} of the corpus)",
            function="treat as a high-yield recurring source",
            invariant="one host contributes an outsized share of items",
            evidence=[f"items={r['c']}", f"corpus_share={share:.2%}"],
            evidence_count=r["c"], confidence=conf,
            epistemic_status="observation",
            tests=["confirm the host keeps producing new unique items"],
            falsifiers=["host stops yielding new unique content"],
        ))
    return out


def mine_volatility(db) -> list[PatternObject]:
    """Domains whose pages change often (volatility / freshness mechanism)."""
    per_domain: dict[str, list[int]] = defaultdict(list)
    for r in db.agg_url_versions(min_versions=2):
        dom = urlparse(r["url"]).netloc
        if dom:
            per_domain[dom].append(r["v"])
    out = []
    for dom, versions in per_domain.items():
        n_pages = len(versions)
        if n_pages < 2:
            continue
        avg_v = sum(versions) / n_pages
        conf = _confidence(n_pages, n_pages + 3)
        out.append(PatternObject(
            pattern_id=stable_id("volatility", dom),
            name=f"{dom} updates frequently",
            family="volatility", domain="temporal", scope="domain",
            trigger="scheduling re-crawls",
            mechanism=f"'{dom}' has {n_pages} pages revised "
                      f"(avg {avg_v:.1f} versions each)",
            function="re-crawl this host more often to catch changes",
            invariant="host pages change on a short cadence",
            evidence=[f"changing_pages={n_pages}", f"avg_versions={avg_v:.1f}"],
            evidence_count=n_pages, confidence=conf,
            epistemic_status="observation",
            tests=["shorten recrawl interval; confirm changes keep appearing"],
            falsifiers=["pages stop changing between crawls"],
        ))
    return out


def mine_github_family_language(db) -> list[PatternObject]:
    """Within a tool family, which language dominates? (tooling-language bias)."""
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in db.agg_github_category_language():
        by_cat[r["category"]][r["language"] or "unknown"] += r["c"]
    out = []
    for category, langs in by_cat.items():
        total = sum(langs.values())
        if total < 3:
            continue
        dom_lang, dom_n = max(langs.items(), key=lambda kv: kv[1])
        conf = _confidence(dom_n, total)
        out.append(PatternObject(
            pattern_id=stable_id("github_tool_language", category),
            name=f"{category} tools are mostly {dom_lang}",
            family="github_tool_language", domain="tooling", scope="domain",
            trigger=f"evaluating/looking for a {category} tool on GitHub",
            mechanism=f"public {category} tooling concentrates in {dom_lang} "
                      f"({dom_n}/{total} = {dom_n/total:.0%})",
            function=f"expect a new {category} tool to be written in {dom_lang}; "
                     f"prioritize {dom_lang} tooling when building/porting",
            invariant=f"{category} -> {dom_lang} plurality",
            evidence=[f"{lng}: {n}" for lng, n in
                      sorted(langs.items(), key=lambda x: -x[1])[:8]],
            evidence_count=total, confidence=conf,
            epistemic_status="observation",
            tests=[f"sample new {category} repos; check {dom_lang} stays the plurality"],
            falsifiers=[f"another language overtakes {dom_lang} for {category}"],
            success_conditions=[f"{dom_lang} share stays the plurality"],
            transfer_constraints=["reflects what is published publicly, not what is best"],
        ))
    return out


def mine_github_family_breadth(db) -> list[PatternObject]:
    """Which tool family dominates what we've discovered? (attention mechanism)."""
    counts = db.github_category_counts()
    total = sum(counts.values())
    if total < 5:
        return []
    dom_cat, dom_n = max(counts.items(), key=lambda kv: kv[1])
    conf = _confidence(dom_n, total)
    return [PatternObject(
        pattern_id=stable_id("github_tool_breadth", "corpus"),
        name=f"discovered tooling skews {dom_cat}",
        family="github_tool_breadth", domain="tooling", scope="domain",
        trigger="allocating tool-scouting attention across families",
        mechanism=f"of {total} useful repos found, {dom_cat} is the largest share "
                  f"({dom_n}/{total} = {dom_n/total:.0%})",
        function=f"expect {dom_cat} to keep yielding the most tools; "
                 "rebalance queries if another family is under-covered",
        invariant="one tool family contributes an outsized share",
        evidence=[f"{c}: {n}" for c, n in sorted(counts.items(), key=lambda x: -x[1])],
        evidence_count=total, confidence=conf,
        epistemic_status="observation",
        tests=[f"keep scouting; confirm {dom_cat} stays the largest family"],
        falsifiers=[f"another family overtakes {dom_cat}"],
    )]


MINERS = (
    mine_topic_category,
    mine_company_topic,
    mine_secret_exposure,
    mine_domain_breadth,
    mine_volatility,
    mine_github_family_language,
    mine_github_family_breadth,
)


def run_pass(db, *, min_evidence: int = 3, min_confidence: float = 0.6) -> dict:
    """Run every miner once, apply lifecycle, and persist. Returns a summary."""
    discovered = 0
    promoted = 0
    by_status: dict[str, int] = defaultdict(int)
    for miner in MINERS:
        try:
            patterns = miner(db)
        except Exception:
            continue
        for p in patterns:
            prior = db.get_pattern(p.pattern_id)
            prior_status = prior["status"] if prior else None
            p.status = p.lifecycle(prior_status, min_evidence=min_evidence,
                                   min_confidence=min_confidence)
            if p.status in ("validated", "active") and prior_status not in (
                    "validated", "active"):
                promoted += 1
            db.upsert_pattern(p.to_row())
            discovered += 1
            by_status[p.status] += 1
    return {
        "patterns_seen": discovered,
        "promoted": promoted,
        "by_status": dict(by_status),
        "total_in_library": db.count_patterns(),
    }
