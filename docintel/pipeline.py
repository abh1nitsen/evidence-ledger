"""Transactional document checkpoints. One active process per database."""
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from .core import VERSION, NUMBER_FORMAT_VERSION, digest, stable_json, validate
from .providers import ProviderError
from .vision import IMAGE_SUFFIXES, MAX_IMAGE_BYTES, prepare_image, validate_image

MAX_BYTES = 100_000


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False, suffix=".tmp") as stream:
            name = stream.name
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


@contextlib.contextmanager
def exclusive(db):
    """OS-held advisory lock; automatically released on process death (no stale lock)."""
    path = Path(str(db) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as stream:
        try:
            stream.seek(0)
            if not stream.read(1):
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("another process owns this checkpoint database") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_document(path):
    if path.is_symlink():
        raise ValueError("symlink inputs are unsupported")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("input exceeds 100 KB")
    text = raw.decode("utf-8")
    if not text.strip() or "\x00" in text:
        raise ValueError("empty or binary document")
    return text


def run(input_dir, db, output, provider, retry_failed=False, stop_after=None, after_extract=None):
    input_dir, db = Path(input_dir), Path(db)
    if not input_dir.is_dir():
        raise ValueError("input directory does not exist")
    paths = sorted(path for path in input_dir.iterdir() if path.suffix.lower() in {".txt"} | IMAGE_SUFFIXES and (path.is_file() or path.is_symlink()))
    if not paths:
        raise ValueError("no supported documents found")
    if stop_after is not None and stop_after < 1:
        raise ValueError("stop_after must be positive")
    db.parent.mkdir(parents=True, exist_ok=True)
    with exclusive(db), contextlib.closing(sqlite3.connect(db, timeout=5)) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("""CREATE TABLE IF NOT EXISTS jobs (
            job_key TEXT PRIMARY KEY, status TEXT NOT NULL, attempts INTEGER NOT NULL,
            result TEXT, error TEXT)""")
        con.commit()
        records, processed, skipped = [], 0, 0
        for path in paths:
            is_image = path.suffix.lower() in IMAGE_SUFFIXES
            try:
                if is_image:
                    if path.is_symlink():
                        raise ValueError("symlink inputs unsupported")
                    with path.open("rb") as stream:
                        raw = stream.read(MAX_IMAGE_BYTES + 1)
                    prepared = prepare_image(raw)
                    if hasattr(provider,"prepare_image"):
                        prepared=provider.prepare_image(prepared)
                    content_hash = prepared["metadata"]["original_sha256"]
                    identity = getattr(provider, "image_identity", provider.identity) + prepared["metadata"]["pillow_version"]
                else:
                    text = read_document(path)
                    content_hash, identity = digest(text), provider.identity
            except (OSError, ValueError, ProviderError) as exc:
                # Input failures are evaluated again on resume; content may be repaired.
                records.append({"document": path.name, "status": "failed",
                                "error": exc.code if isinstance(exc,ProviderError) else "invalid_input", "detail": type(exc).__name__})
                continue
            key = digest(content_hash + identity + VERSION + (NUMBER_FORMAT_VERSION if not is_image else ''))
            previous = con.execute("SELECT status,attempts,result,error FROM jobs WHERE job_key=?", (key,)).fetchone()
            if previous and (previous[0] == "completed" or (previous[0] == "failed" and not retry_failed)):
                skipped += 1
                status, attempts, result, error = previous
            else:
                attempts = (previous[1] if previous else 0) + 1
                # A crash after this commit leaves an explicit pending job. Next run reclaims it.
                with con:
                    con.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?)", (key, "pending", attempts, None, None))
                try:
                    if is_image:
                        if not getattr(provider, "supports_images", False):
                            raise ProviderError("image input requires a vision provider")
                        proposed = provider.extract_image(prepared)
                        result = stable_json(validate_image(prepared, proposed, provider))
                    else:
                        proposed = provider.extract(text)
                        result = stable_json(validate(text, proposed))
                    if after_extract:
                        after_extract()  # Fault injection used only by recovery tests.
                    status, error = "completed", None
                except (ProviderError, ValueError) as exc:
                    status, result = "failed", None
                    error = exc.code if isinstance(exc, ProviderError) else "invalid_provider_schema"
                with con:
                    con.execute("UPDATE jobs SET status=?,result=?,error=? WHERE job_key=?", (status, result, error, key))
                processed += 1
            record = {"document": path.name, "job_key": key, "status": status,
                      "attempts": attempts, "provider": provider.name, "error": error}
            if result:
                from .numbers import number_view
                record["extraction"] = number_view(json.loads(result))
            records.append(record)
            if stop_after is not None and processed >= stop_after:
                break
        report = {"schema_version": VERSION, "provider": provider.name,
                  "provider_identity": provider.identity, "processed": processed, "skipped": skipped,
                  "discovered": len(paths), "remaining": len(paths) - len(records), "documents": records}
        # Regenerate even if every job was cached. DB commits survive export failure.
        atomic_json(output, report)
        return report
