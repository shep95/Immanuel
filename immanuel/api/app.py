"""FastAPI application: health + API-key-protected knowledge API.

Users generate a key in Discord (/apikey) and call these endpoints from their
platform or LLM tools. The API is read-only over the collected knowledge base.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from ..classifier import CATEGORIES, DISPLAY
from ..db import Database
from ..keys import verify_api_key


def create_app(db: Database, engine: Any = None, forge: Any = None) -> FastAPI:
    app = FastAPI(
        title="Immanuel API",
        version="0.2.0",
        description="Read-only API over Immanuel's collected knowledge base + the "
        "asherin.eng search engine and Pattern Forge library. Authenticate with an "
        "API key from the Discord /apikey command (header: `X-API-Key: imk_...` or "
        "`Authorization: Bearer imk_...`).",
    )

    def require_key(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        authorization: str | None = Header(default=None),
    ) -> dict:
        raw = x_api_key
        if not raw and authorization and authorization.lower().startswith("bearer "):
            raw = authorization[7:].strip()
        rec = verify_api_key(db, raw)
        if not rec:
            raise HTTPException(status_code=401, detail="invalid or missing API key")
        return rec

    def require_admin(rec: dict = Depends(require_key)) -> dict:
        if "admin" not in (rec.get("scopes") or ""):
            raise HTTPException(status_code=403,
                                detail="admin API key required (generate with /adminkey)")
        return rec

    # ---- public: health (used by Railway healthcheck) --------------------
    @app.get("/")
    def root() -> dict:
        return {"service": "immanuel", "status": "ok", "docs": "/docs"}

    @app.get("/health")
    def health() -> dict:
        state = engine.state if engine else "n/a"
        return {"status": "ok", "engine": state, "items": db.count_items()}

    # ---- authenticated knowledge API -------------------------------------
    @app.get("/v1/status")
    def status(_: dict = Depends(require_key)) -> dict:
        if engine:
            return engine.snapshot()
        return {"items_total": db.count_items(),
                "by_category": db.counts_by_category()}

    @app.get("/v1/categories")
    def categories(_: dict = Depends(require_key)) -> dict:
        return {"categories": {c: DISPLAY[c] for c in CATEGORIES},
                "counts": db.counts_by_category()}

    @app.get("/v1/search")
    def search(
        _: dict = Depends(require_key),
        q: str | None = Query(default=None, description="text query"),
        category: str | None = Query(default=None),
        domain: str | None = Query(default=None),
        company: str | None = Query(default=None),
        topic: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        if category and category not in CATEGORIES:
            raise HTTPException(status_code=400,
                                detail=f"category must be one of {list(CATEGORIES)}")
        rows = db.search_items(query=q, category=category, domain=domain,
                               company=company, topic=topic,
                               limit=limit, offset=offset)
        return {"count": len(rows), "results": [_public_item(r) for r in rows]}

    # ---- organization: companies + topics --------------------------------
    @app.get("/v1/companies")
    def companies(_: dict = Depends(require_key),
                  limit: int = Query(default=200, ge=1, le=500)) -> dict:
        return {"companies": db.list_companies(limit)}

    @app.get("/v1/topics")
    def topics(_: dict = Depends(require_key)) -> dict:
        return {"topics": db.list_topics()}

    # ---- intel data-reports ----------------------------------------------
    @app.get("/v1/intel")
    def intel_list(_: dict = Depends(require_key),
                   limit: int = Query(default=25, ge=1, le=200)) -> dict:
        return {"reports": db.recent_intel(limit)}

    @app.get("/v1/intel/report")
    def intel_report(url: str = Query(...), _: dict = Depends(require_key)) -> dict:
        rep = db.get_intel_report(url)
        if not rep:
            raise HTTPException(status_code=404, detail="no intel report for that url")
        return rep

    # ---- Pattern Forge library -------------------------------------------
    @app.get("/v1/patterns")
    def patterns(_: dict = Depends(require_key),
                 status: str | None = Query(default=None),
                 limit: int = Query(default=200, ge=1, le=1000)) -> dict:
        rows = db.list_patterns(status=status, limit=limit)
        forge_snap = forge.snapshot() if forge else {"patterns_total": len(rows)}
        return {"count": len(rows), "forge": forge_snap, "patterns": rows}

    @app.get("/v1/patterns/export")
    def patterns_export(_: dict = Depends(require_key),
                        only_validated: bool = Query(default=False)) -> JSONResponse:
        from ..patternforge.skills import render_skills
        text = render_skills(db, only_validated=only_validated)
        return JSONResponse({"format": "text", "skills": text})

    # ---- exposed secrets (ADMIN ONLY; values are masked) -----------------
    @app.get("/v1/secrets")
    def secrets(_: dict = Depends(require_admin),
                limit: int = Query(default=50, ge=1, le=200)) -> dict:
        return {"count": db.count_secrets(), "findings": db.recent_secrets(limit)}

    @app.get("/v1/items/{item_id}")
    def get_item(item_id: int, _: dict = Depends(require_key)) -> dict:
        for r in db.iter_all_items():
            if r["id"] == item_id:
                return _public_item(r, full=True)
        raise HTTPException(status_code=404, detail="not found")

    @app.get("/v1/versions")
    def versions(url: str = Query(..., description="the page URL"),
                 _: dict = Depends(require_key)) -> dict:
        rows = db.get_versions(url, limit=200)
        ts = db.url_timestamps(url)
        return {"url": url, "timestamps": ts, "versions": rows}

    @app.get("/v1/updates")
    def updates(_: dict = Depends(require_key),
                limit: int = Query(default=25, ge=1, le=200)) -> dict:
        rows = db.recent_updates(limit)
        return {"count": len(rows), "updates": rows}

    @app.get("/v1/export")
    def export(_: dict = Depends(require_key),
               limit: int = Query(default=1000, ge=1, le=10000)) -> JSONResponse:
        items = []
        for i, r in enumerate(db.iter_all_items()):
            if i >= limit:
                break
            items.append(_public_item(r, full=True))
        return JSONResponse({"count": len(items), "items": items})

    return app


def _public_item(r: dict, full: bool = False) -> dict:
    out = {
        "id": r["id"],
        "url": r["url"],
        "domain": r["source_domain"],
        "title": r["title"],
        "category": r["category"],
        "category_display": DISPLAY.get(r["category"] or "unknown", "unknown"),
        "confidence": r["category_confidence"],
        "epistemic_status": r["epistemic_status"],
        "company": r.get("company"),
        "topic": r.get("topic"),
        "lang": r.get("lang"),
        "timeline_ts": r["timeline_ts"],
        "collector": r["collector"],
        "fetched_at": r["fetched_at"],
        "excerpt": r["excerpt"],
        "media": r["media"],
        "secrets_count": r.get("secrets_count", 0),
    }
    if full:
        out["content"] = r["content"]
        out["signals"] = r["signals"]
        out["content_hash"] = r["content_hash"]
    return out
