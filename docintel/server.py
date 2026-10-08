"""Loopback-only offline demo. Not a production web service."""
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
import json
import importlib.util
import os
import math
import re
import sqlite3
import secrets
import tempfile
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

from .core import VERSION, baseline, validate, digest
from .documents import attach_document
from .reviews import ReviewStore, ReviewConflict
from .pipeline import run
from .providers import Groq, ProviderError
from .vision import MAX_IMAGE_BYTES


def handler(report, image_provider=None, image_db=None, review_threshold=0.85):
    if not isinstance(review_threshold,(int,float)) or not math.isfinite(review_threshold) or not 0<=review_threshold<=1:
        raise ValueError("invalid threshold")
    image_db = image_db or report.parent / "uploads.sqlite"
    downloads = OrderedDict()
    reviews = ReviewStore(image_db.parent / (image_db.stem + "-reviews.sqlite"))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Do not log pasted documents or request paths.

        def send(self, code, content, kind="application/json", attachment=False):
            self.send_response(code)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if attachment:
                self.send_header("Content-Disposition", 'attachment; filename="extraction.json"')
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(content if isinstance(content, bytes) else content.encode())

        def send_result(self, result, identity=None):
            if identity:
                checkpoint=result.get("checkpoint")
                result=reviews.register(identity,result)
                if checkpoint: result["checkpoint"]=checkpoint
            if "score_policy" in result:
                result["score_policy"]["threshold"]=review_threshold
            token = secrets.token_urlsafe(24)
            downloads[token] = json.dumps(result, ensure_ascii=False, indent=2).encode()
            while len(downloads) > 16:
                downloads.popitem(last=False)
            self.send(200, json.dumps({**result, "download_url": "/api/download/" + token}))

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
            elif path == "/api/recent":
                try:
                    self.send(200,json.dumps({"documents":reviews.recent()}))
                except (OSError,sqlite3.Error):
                    self.send(503,'{"error":"review_storage_unavailable"}')
            elif path == "/api/config":
                self.send(200, json.dumps({"image_enabled": image_provider is not None,
                    "image_provider": image_provider.name if image_provider else None, "model": image_provider.model if image_provider else None,
                    "ocr_enabled": getattr(image_provider,"uses_ocr",False), "score_calibrated":False, "review_threshold":review_threshold, "max_image_bytes": MAX_IMAGE_BYTES}))
            elif path.startswith("/api/review/") and re.fullmatch(r"[a-f0-9]{64}",path.removeprefix("/api/review/")):
                try:
                    self.send_result(reviews.get(path.removeprefix("/api/review/")))
                except KeyError:
                    self.send(404,'{"error":"unknown_review"}')
                except (OSError,sqlite3.Error):
                    self.send(503,'{"error":"review_storage_unavailable"}')
            elif path.startswith("/api/download/") and path.removeprefix("/api/download/") in downloads:
                self.send(200, downloads[path.removeprefix("/api/download/")], attachment=True)
            else:
                self.send(404, '{"error":"not_found"}')

        def do_POST(self):
            self.connection.settimeout(15)
            # No cross-origin writes; custom content type stops simple form submission.
            expected = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if self.headers.get("Origin") not in expected:
                self.send(403, '{"error":"origin_rejected"}')
                return
            if self.path == "/api/review":
                try:
                    if self.headers.get("Content-Type")!="application/json": raise ValueError()
                    length=int(self.headers.get("Content-Length","0"))
                    if not 0<length<=4096: raise ValueError()
                    data=json.loads(self.rfile.read(length))
                    if set(data)!={"document_id","field","action","value","revision"}: raise ValueError()
                    if not isinstance(data["document_id"],str) or not re.fullmatch(r"[a-f0-9]{64}",data["document_id"]): raise ValueError()
                    result=reviews.decide(data["document_id"],data["field"],data["action"],data["value"],data["revision"])
                    self.send_result(result)
                except ReviewConflict:
                    self.send(409,'{"error":"review_changed_reload_saved_reading"}')
                except (ValueError,KeyError,TypeError):
                    self.send(400,'{"error":"invalid_review"}')
                except (OSError,RuntimeError,sqlite3.Error):
                    self.send(503,'{"error":"review_storage_unavailable"}')
                return
            if self.path == "/api/extract-image":
                if self.headers.get("Content-Type") != "application/octet-stream":
                    self.send(400, '{"error":"invalid_content_type"}')
                    return
                if image_provider is None:
                    self.send(503, '{"error":"groq_not_configured"}')
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= MAX_IMAGE_BYTES:
                        raise ValueError()
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise ValueError()
                    # Original upload is temporary; committed output/transcript can be resumed
                    # by re-uploading identical bytes. No filename from the client is trusted.
                    with tempfile.TemporaryDirectory(prefix="ledger-upload-") as directory:
                        folder = Path(directory)
                        (folder / "invoice.jpg").write_bytes(raw)
                        report_data = run(folder, image_db, folder / "report.json", image_provider,
                                          retry_failed=True)
                    record = report_data["documents"][0]
                    if record["status"] != "completed":
                        code = 400 if record["error"] == "invalid_input" else 502
                        self.send(code, json.dumps({"error": record["error"]}))
                    else:
                        result = record["extraction"]
                        result["checkpoint"] = {"job_key": record["job_key"], "attempts": record["attempts"],
                                                "reused": bool(report_data["skipped"])}
                        self.send_result(result, record["job_key"])
                except ValueError:
                    self.send(400, '{"error":"invalid_image"}')
                except (OSError, RuntimeError,sqlite3.Error):
                    self.send(503, '{"error":"image_processing_unavailable"}')
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
                result=attach_document(validate(text, baseline(text)),text)
                result["transcript"]=text
                self.send_result(result,digest(result["source_sha256"]+VERSION+":ui-text"))
            except (ValueError, KeyError, TypeError):
                self.send(400, '{"error":"invalid_document"}')
    return Handler


def serve(port, report, vision_model="qwen/qwen3.8-27b", image_db=None, ocr="none", review_threshold=0.85):
    from .ocr import Hybrid
    image_provider = Groq(vision_model) if os.environ.get("GROQ_API_KEY") and importlib.util.find_spec("PIL") else None
    if image_provider and ocr=="paddle":
        image_provider=Hybrid(image_provider)
    with ThreadingHTTPServer(("127.0.0.1", port), handler(report, image_provider, image_db,review_threshold)) as server:
        print(f"Evidence Ledger: http://127.0.0.1:{port} (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
