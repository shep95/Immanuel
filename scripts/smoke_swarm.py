"""Live swarm smoke test: run the agent-per-page swarm against a local server."""
import asyncio
import http.server
import socketserver
import threading

from immanuel.config import Config
from immanuel.db import Database
from immanuel.engine import Engine

# a small linked site: home -> p1..p3 ; each pN -> pN-child
PAGES = {}
def _page(title, body, links):
    hrefs = "".join(f"<a href='{l}'>x</a>" for l in links)
    return (f"<html><head><title>{title}</title></head><body><p>{body}</p>"
            f"{hrefs}</body></html>").encode()

LINKS = {
    "/": ["/p1", "/p2", "/p3"],
    "/p1": ["/p1a"], "/p2": ["/p2a"], "/p3": ["/p3a"],
    "/p1a": [], "/p2a": [], "/p3a": [],
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/robots.txt":
            body = b"User-agent: *\nAllow: /\n"; ct = "text/plain"
        elif path in LINKS:
            body = _page(f"Page {path}", f"official confirmed content for {path}",
                         LINKS[path]); ct = "text/html"
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


async def main():
    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        base = f"http://127.0.0.1:{port}"
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        cfg = Config(
            database_path=":memory:", crawler_mode="swarm",
            seed_urls=[f"{base}/"], max_agents=20, crawl_delay_seconds=0,
            cycle_interval_seconds=1, recrawl_interval_seconds=9999,
            publish_to_discord=False,
        )
        db = Database(cfg.database_path)
        eng = Engine(db, cfg)
        await eng.seed()
        eng.start()

        task = asyncio.create_task(eng.run_forever())
        await asyncio.sleep(3)          # let the swarm fan out
        eng.request_shutdown()
        await asyncio.wait_for(task, timeout=10)

        snap = eng.snapshot()
        print("mode:", snap["mode"], "| items:", snap["items_total"],
              "| agents spawned:", snap["swarm"]["agents_spawned"],
              "| peak agents:", snap["swarm"]["peak_agents"])
        print("by category:", snap["by_category"])

        # 7 pages in the graph (/, p1..p3, p1a..p3a) each get an agent + collected
        assert snap["items_total"] >= 7, f"expected >=7 items, got {snap['items_total']}"
        assert snap["swarm"]["agents_spawned"] >= 7
        assert snap["swarm"]["peak_agents"] <= 20  # respected the cap
        httpd.shutdown(); db.close()
        print("\nSWARM SMOKE OK ✅")


if __name__ == "__main__":
    asyncio.run(main())
