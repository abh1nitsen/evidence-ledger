"""Loopback-only offline demo. Not a production web service."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse

from .core import baseline, validate


def handler(report):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Do not log pasted documents or request paths.

        def send(self, code, content, kind="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(content if isinstance(content, bytes) else content.encode())

        def do_GET(self):
            path = urlparse(self.path).path
            if path in {"/", "/app.js"}:
                name = "index.html" if path == "/" else "app.js"
                self.send(200, (Path(__file__).parent / "web" / name).read_bytes(),
                          "text/html" if path == "/" else "application/javascript")
            elif path == "/api/report":
                try:
                    self.send(200, report.read_bytes())
                except OSError:
                    self.send(200, '{"documents":[],"remaining":0}')
            else:
                self.send(404, '{"error":"not_found"}')

        def do_POST(self):
            # No cross-origin writes; custom content type stops simple form submission.
            expected = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if self.headers.get("Origin") not in expected:
                self.send(403, '{"error":"origin_rejected"}')
                return
            if self.path != "/api/extract" or self.headers.get("Content-Type") != "application/json":
                self.send(400, '{"error":"invalid_request"}')
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 110_000:
                    raise ValueError()
                data = json.loads(self.rfile.read(length))
                text = data["text"]
                if not isinstance(text, str) or not text.strip() or len(text.encode()) > 100_000 or "\x00" in text:
                    raise ValueError()
                self.send(200, json.dumps(validate(text, baseline(text))))
            except (ValueError, KeyError, TypeError):
                self.send(400, '{"error":"invalid_document"}')
    return Handler


def serve(port, report):
    with HTTPServer(("127.0.0.1", port), handler(report)) as server:
        print(f"Evidence Ledger: http://127.0.0.1:{port} (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
