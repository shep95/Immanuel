"""Built-in bootstrap seeds for zero-config auto-discovery.

With AUTO_DISCOVER on (default), Immanuel starts from these public, link-rich
"firehose" pages and feeds — no manual sources needed. Each fetch yields many
outbound links to *other domains*, which the swarm registers as new sources and
follows (up to MAX_HOPS). Several of these change constantly (news feeds, HN,
Reddit, Wikipedia random/recent), so re-crawling them keeps surfacing brand-new
domains over time — the crawler finds its own sources.

All are public and crawled politely (robots.txt respected). This is a bootstrap,
not a claim of total web coverage — see the README note on scale.
"""
from __future__ import annotations

DEFAULT_SEEDS: list[str] = [
    # --- broad, link-rich hubs -------------------------------------------
    "https://en.wikipedia.org/wiki/Main_Page",
    "https://en.wikipedia.org/wiki/Special:Random",     # different links each fetch
    "https://en.wikipedia.org/wiki/Lists_of_websites",
    "https://news.ycombinator.com/",
    "https://news.ycombinator.com/newest",
    "https://lite.cnn.com/",                             # lightweight, link-rich
    "https://text.npr.org/",                             # text-only, crawl-friendly
    "https://www.gov.uk/",
    "https://www.usa.gov/",
    "https://dmoztools.net/",                            # curated directory mirror

    # --- live feeds (entry links become new sources) ---------------------
    "https://news.google.com/rss",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://www.reddit.com/r/all/new/.rss",
    "https://hnrss.org/newest",
    "https://en.wikipedia.org/w/index.php?title=Special:RecentChanges&feed=atom",

    # --- public data / dataset portals (fan out to many domains) ---------
    "https://data.gov/",
    "https://data.europa.eu/en",
    "https://www.data.gov.uk/",
]


def bootstrap_seeds() -> list[str]:
    return list(DEFAULT_SEEDS)
