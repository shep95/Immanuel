import asyncio

from immanuel.config import Config
from immanuel.db import Database
from immanuel.githubscout.classify import classify_repo, is_software
from immanuel.githubscout.scout import GitHubScout


# --------------------------------------------------------------- classifier
def test_classifies_each_family():
    osint = classify_repo({
        "full_name": "user/recon-x", "description": "recon toolkit",
        "language": "Python", "topics": ["osint", "reconnaissance"], "stars": 50,
    })
    assert osint is not None and osint.category == "osint"
    assert "osint" in osint.matched
    assert osint.how_useful  # non-empty explanation

    red = classify_repo({
        "full_name": "x/c2", "description": "adversary emulation framework",
        "language": "Go", "topics": ["red-team", "c2"], "stars": 200,
    })
    assert red is not None and red.category == "red-team"

    surv = classify_repo({
        "full_name": "x/track", "description": "location tracking",
        "language": "C", "topics": ["surveillance", "tracking"], "stars": 10,
    })
    assert surv is not None and surv.category == "surveillance"


def test_rejects_non_security_repo():
    assert classify_repo({
        "full_name": "me/todo", "description": "a todo list app",
        "language": "JavaScript", "topics": ["productivity"], "stars": 999,
    }) is None


def test_rejects_docs_only_awesome_list():
    # matches 'osint' by name/topic but has no code (docs-only) -> not software
    repo = {
        "full_name": "user/awesome-osint",
        "description": "a curated list of osint resources",
        "language": None, "topics": ["osint", "awesome"], "stars": 5000,
    }
    assert is_software(repo) is False
    assert classify_repo(repo) is None


def test_classification_is_deterministic():
    repo = {
        "full_name": "x/exploit-kit", "description": "pentest exploit payloads",
        "language": "Python", "topics": ["hacking", "exploit"], "stars": 30,
    }
    a = classify_repo(repo)
    b = classify_repo(repo)
    assert a is not None and b is not None
    assert a.as_dict() == b.as_dict()
    assert a.category == "hacking"


# ---------------------------------------------------------------------- db
def test_db_roundtrip_and_dedup():
    db = Database(":memory:")
    repo = {
        "full_name": "user/recon-x", "html_url": "https://github.com/user/recon-x",
        "name": "recon-x", "description": "recon", "category": "osint",
        "how_useful": "useful", "language": "Python", "stars": 50,
        "topics": ["osint"], "matched": ["osint"], "score": 4, "pushed_at": None,
    }
    assert db.add_github_repo(repo) is True
    assert db.add_github_repo(repo) is False  # dedup on full_name
    assert db.count_github_repos() == 1
    assert db.github_repo_exists("user/recon-x") is True
    assert db.github_category_counts().get("osint") == 1

    unpub = db.unpublished_github_repos()
    assert len(unpub) == 1
    db.mark_github_published("user/recon-x")
    assert db.unpublished_github_repos() == []
    db.close()


# ------------------------------------------------------------------- scout
def test_scout_pass_stores_useful_and_dedups():
    db = Database(":memory:")
    config = Config()  # defaults: 5 families, min_stars=5

    async def fake_search(category, page):
        if category != "osint":
            return []
        return [
            {  # useful -> kept
                "full_name": "user/recon-x",
                "html_url": "https://github.com/user/recon-x",
                "name": "recon-x", "description": "osint recon toolkit",
                "language": "Python", "stargazers_count": 120,
                "topics": ["osint", "reconnaissance"],
            },
            {  # below min stars -> filtered
                "full_name": "user/tiny", "name": "tiny",
                "description": "osint", "language": "Python",
                "stargazers_count": 1, "topics": ["osint"],
            },
            {  # not security -> classifier drops it
                "full_name": "me/todo", "name": "todo",
                "description": "todo app", "language": "JavaScript",
                "stargazers_count": 500, "topics": ["productivity"],
            },
        ]

    events = []
    scout = GitHubScout(db, config, emit=events.append, search_fn=fake_search)

    summary = asyncio.run(scout.run_once())
    assert summary["new"] == 1
    assert db.count_github_repos() == 1
    assert events and events[0]["kind"] == "github"
    assert events[0]["repo"]["full_name"] == "user/recon-x"
    assert events[0]["repo"]["category"] == "osint"
    # page cursor advanced for next pass
    assert db.get_state("gh_page_osint") == "2"

    # second pass over the same data -> no new inserts, no new events
    summary2 = asyncio.run(scout.run_once())
    assert summary2["new"] == 0
    assert db.count_github_repos() == 1
    assert len(events) == 1
    db.close()


def test_scout_snapshot_shape():
    db = Database(":memory:")
    scout = GitHubScout(db, Config(), emit=None, search_fn=None)
    snap = scout.snapshot()
    assert set(["enabled", "passes", "repos_total", "by_category"]).issubset(snap)
    db.close()
