"""End-to-end smoke test (no Discord, no external internet).

Spins up a tiny local HTTP server serving a few pages, points Immanuel's engine
at it, runs one crawl cycle, then queries via the FastAPI app with a real key.
"""
import asyncio
import http.server
import socketserver
import threading

from fastapi.testclient import TestClient

from immanuel.api.app import create_app
from immanuel.config import Config
from immanuel.db import Database
from immanuel.engine import Engine
from immanuel.keys import generate_api_key

PAGES = {
    "/": b"<html><head><title>Home</title></head><body><p>Welcome</p>"
         b"<a href='/fact'>f</a><a href='/rumor'>r</a><a href='/conspiracy'>c</a></body></html>",
    "/fact": b"<html><head><title>Official report</title></head><body>"
             b"<p>The government agency officially confirmed the data shows growth. Published in the register.</p></body></html>",
    "/rumor": b"<html><head><title>Reported plan</title></head><body>"
              b"<p>Sources say the public company might allegedly cut jobs, according to speculation.</p></body></html>",
    "/conspiracy": b"<html><head><title>Hidden truth</title></head><body>"
                   b"<p>It's a false flag cover-up by the deep state; wake up sheeple, it's a hoax.</p></body></html>",
    "/robots.txt": b"User-agent: *\nAllow: /\n",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path.split("?")[0])
        if body is None:
            self.send_response(404); self.end_headers(); return
        ct = "text/plain" if self.path.endswith("robots.txt") else "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


async def main():
    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        base = f"http://127.0.0.1:{port}"
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()

        cfg = Config(
            database_path=":memory:",
            seed_urls=[f"{base}/"],
            crawl_delay_seconds=0,
            cycle_interval_seconds=1,
            max_pages_per_cycle=10,
        )
        db = Database(cfg.database_path)
        eng = Engine(db, cfg)

        await eng.seed()
        eng.start()
        # run a couple of cycles to fetch home + discovered pages
        for _ in range(3):
            await eng._run_cycle()

        snap = eng.snapshot()
        print("Engine snapshot:", snap["state"], "items:", snap["items_total"])
        print("By category:", snap["by_category"])

        app = create_app(db, eng)
        client = TestClient(app)
        key = generate_api_key(db, owner="smoke")

        r = client.get("/health")
        print("health:", r.status_code, r.json())

        r = client.get("/v1/search", headers={"X-API-Key": key})
        print("search count:", r.json()["count"])
        for it in r.json()["results"]:
            print("  -", it["category_display"], "|", it["title"])

        r = client.get("/v1/search", headers={"X-API-Key": key},
                       params={"category": "conspiracy"})
        print("conspiracy results:", r.json()["count"])

        assert snap["items_total"] >= 3, "expected to collect several items"
        assert r.json()["count"] >= 1, "expected a conspiracy-classified item"
        httpd.shutdown()
        db.close()
        print("\nSMOKE OK ✅")


if __name__ == "__main__":
    asyncio.run(main())
