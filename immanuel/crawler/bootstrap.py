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

# Multi-country / multi-language hubs so discovery is not US/English-only.
# Different countries publish different data — these fan out into local domains.
GLOBAL_SEEDS: list[str] = [
    # multilingual Wikipedias (each fans out to that language's web)
    "https://es.wikipedia.org/wiki/Especial:Aleatoria",
    "https://fr.wikipedia.org/wiki/Sp%C3%A9cial:Page_au_hasard",
    "https://de.wikipedia.org/wiki/Spezial:Zuf%C3%A4llige_Seite",
    "https://pt.wikipedia.org/wiki/Especial:Aleat%C3%B3ria",
    "https://ru.wikipedia.org/wiki/%D0%A1%D0%BB%D1%83%D0%B6%D0%B5%D0%B1%D0%BD%D0%B0%D1%8F:%D0%A1%D0%BB%D1%83%D1%87%D0%B0%D0%B9%D0%BD%D0%B0%D1%8F_%D1%81%D1%82%D1%80%D0%B0%D0%BD%D0%B8%D1%86%D0%B0",
    "https://ar.wikipedia.org/wiki/%D8%AE%D8%A7%D8%B5:%D8%B9%D8%B4%D9%88%D8%A7%D8%A6%D9%8A",
    "https://zh.wikipedia.org/wiki/Special:%E9%9A%8F%E6%9C%BA%E9%A1%B5%E9%9D%A2",
    "https://ja.wikipedia.org/wiki/Special:Randompage",
    "https://hi.wikipedia.org/wiki/%E0%A4%B5%E0%A4%BF%E0%A4%B6%E0%A5%87%E0%A4%B7:%E0%A4%AF%E0%A4%BE%E0%A4%A6%E0%A5%83%E0%A4%9A%E0%A5%8D%E0%A4%9B%E0%A4%BF%E0%A4%95_%E0%A4%AA%E0%A5%83%E0%A4%B7%E0%A5%8D%E0%A4%A0",
    # regional news (Europe)
    "https://www.dw.com/en/top-stories/s-9097",
    "https://www.france24.com/en/rss",
    "https://elpais.com/rss/elpais/portada.xml",
    "https://www.spiegel.de/international/index.rss",
    # Middle East / Africa
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
    # Asia / Pacific
    "https://www.thehindu.com/feeder/default.rss",
    "https://www3.nhk.or.jp/nhkworld/en/news/feeds/",
    "https://www.abc.net.au/news/feed/51120/rss.xml",
    "https://www.channelnewsasia.com/rssfeeds/8395986",
    # Americas
    "https://g1.globo.com/rss/g1/",
    "https://www.cbc.ca/webfeed/rss/rss-topstories",
    # multi-country government / open-data portals
    "https://www.canada.ca/en.html",
    "https://www.india.gov.in/",
    "https://www.gov.za/",
    "https://www.gov.sg/",
    "https://www.gob.mx/",
    "https://www.dataportal.org/",          # index of national open-data portals
    "https://www.oecd.org/",
    "https://data.un.org/",
]


def bootstrap_seeds() -> list[str]:
    return list(DEFAULT_SEEDS) + list(GLOBAL_SEEDS)
