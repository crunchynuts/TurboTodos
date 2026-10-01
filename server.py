"""Dependency-free, loopback-only HTTP UI/API. Optional browser mode."""
from __future__ import annotations

import argparse
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from importing import apply_import, plan_import
from storage import DEFAULT_DB, ROOT, Conflict, Store, bulk_tags, save_receipt

MAX_BODY = 16 * 1024 * 1024
PUBLIC = {"index.html", "style.css", "app.js", "bulk.js", "bulk.css", "export.js", "transport.js", "render.js", "filters.js", "power.js", "power.css", "favicon.svg", "import-template.csv"}


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=3000, db_path=DEFAULT_DB):
        self.store = Store(db_path)
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "TurboTodosPython/2"

    def log_message(self, *args):
        pass

    def respond(self, status, content, mime="application/json; charset=utf-8"):
        data = json.dumps(content, ensure_ascii=False).encode("utf-8") if isinstance(content, (dict, list)) else content
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self' http://localhost:* http://127.0.0.1:*")
        self.end_headers()
        self.wfile.write(data)

    def trusted(self):
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        if host not in {f"localhost:{port}", f"127.0.0.1:{port}"}:
            self.respond(403, {"error": "Use localhost to open this personal workspace"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{host}":
            self.respond(403, {"error": "Origin not allowed"})
            return False
        return True

    def do_GET(self):
        if not self.trusted():
            return
        path = urlparse(self.path).path
        if path == "/api/workspace":
            return self.respond(200, self.server.store.read())
        if path == "/api/health":
            return self.respond(200, {"app": "TurboTodos", "runtime": "python"})
        name = "index.html" if path == "/" else path.removeprefix("/")
        if name not in PUBLIC:
            return self.respond(404, {"error": "Not found"})
        mime = {".js": "text/javascript", ".css": "text/css", ".csv": "text/csv"}.get(
            (ROOT / name).suffix, mimetypes.guess_type(name)[0] or "application/octet-stream")
        return self.respond(200, (ROOT / "public" / name).read_bytes(), mime + "; charset=utf-8")

    def handle_write(self):
        if not self.trusted():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.respond(413, {"error": "Request must be between 1 byte and 16 MB"})
            if self.headers.get_content_type() != "application/json":
                return self.respond(415, {"error": "Send application/json"})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Send a JSON object")
            path = urlparse(self.path).path
            store = self.server.store
            if path == "/api/workspace" and self.command == "PUT":
                return self.respond(200, save_receipt(store.save(payload), payload))
            if path == "/api/import/preview" and self.command == "POST":
                summary, _ = plan_import(payload, store.read())
                return self.respond(200, summary)
            if path == "/api/import" and self.command == "POST":
                result = store.edit(payload.get("version"), lambda s: apply_import(payload, s))
                return self.respond(200, result)
            if path == "/api/tags" and self.command == "POST":
                result = store.edit(payload.get("version"), lambda s: bulk_tags(s, payload.get("ids"), payload.get("tags"), payload.get("mode")))
                return self.respond(200, result)
            return self.respond(404, {"error": "Not found"})
        except Conflict as exc:
            self.respond(409, {"error": str(exc)})
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            self.respond(400, {"error": str(exc)})

    do_PUT = handle_write
    do_POST = handle_write


def start_background(port=0, db_path=DEFAULT_DB):
    server = AppServer(port, db_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="turbotodos-local-api")
    thread.start()
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run TurboTodos locally with Python")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    server = AppServer(args.port, args.db)
    print(f"TurboTodos (Python) is ready at http://localhost:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
