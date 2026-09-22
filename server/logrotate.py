"""Shared size-bounded log rotation.

The live logs stay small for fast writes/tailing; when a log reaches its cap it
is sealed into a timestamped, gzip-compressed segment in an archive directory.
Archives are non-destructive (never overwritten) and serve as the later
distillation / evaluation corpus. Retention prunes only the oldest segments.
"""
import gzip
import json
import os
import shutil
import time

DEFAULT_ARCHIVE_MAX_BYTES = 200 * 1024 * 1024
DEFAULT_RETAIN_DAYS = 30
DEFAULT_RETAIN_SEGMENTS = 30


def archive_segment(path, archive_dir, prefix, tag=""):
    """Gzip *path* into a timestamped segment and return the new path."""
    os.makedirs(archive_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"-{tag}" if tag else ""
    dest = os.path.join(archive_dir, f"{prefix}-{stamp}{suffix}.jsonl.gz")
    n = 1
    while os.path.exists(dest):
        dest = os.path.join(
            archive_dir, f"{prefix}-{stamp}{suffix}-{n}.jsonl.gz")
        n += 1
    with open(path, "rb") as src, gzip.open(dest, "wb") as out:
        shutil.copyfileobj(src, out)
    return dest


def _prune(archive_dir, retain_days, retain_segments, archive_max_bytes):
    try:
        segs = [os.path.join(archive_dir, f) for f in os.listdir(archive_dir)
                if f.endswith(".jsonl.gz")]
    except FileNotFoundError:
        return
    segs.sort(key=lambda item: os.path.getmtime(item))  # oldest first
    now = time.time()
    for item in list(segs):
        if now - os.path.getmtime(item) > retain_days * 86400:
            os.remove(item)
            segs.remove(item)

    def total():
        return sum(os.path.getsize(item) for item in segs)

    while segs and (len(segs) > retain_segments
                    or total() > archive_max_bytes):
        os.remove(segs.pop(0))


def _scan_jsonl(path):
    """Return (record_count, first 'at', last 'at') for a JSONL file."""
    count = 0
    first_at = None
    last_at = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            count += 1
            try:
                at = json.loads(line).get("at")
            except ValueError:
                at = None
            if at:
                if first_at is None:
                    first_at = at
                last_at = at
    return count, first_at, last_at


def reconcile_manifest(archive_dir, added=None, added_meta=None):
    """Maintain MANIFEST.json: index every segment for incremental distill."""
    manifest_path = os.path.join(archive_dir, "MANIFEST.json")
    data = {"version": 1, "segments": {}}
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict) and isinstance(loaded.get("segments"), dict):
            data = loaded
    except (OSError, ValueError):
        pass
    if added:
        data["segments"][added] = added_meta or {}
    try:
        present = {f for f in os.listdir(archive_dir) if f.endswith(".jsonl.gz")}
    except FileNotFoundError:
        present = set()
    data["segments"] = {k: v for k, v in data["segments"].items() if k in present}
    for f in sorted(present):
        data["segments"].setdefault(f, {})
    try:
        tmp = manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, manifest_path)
    except OSError:
        pass


def rotate_if_needed(path, max_bytes, archive_dir, prefix, tag="",
                     retain_days=DEFAULT_RETAIN_DAYS,
                     retain_segments=DEFAULT_RETAIN_SEGMENTS,
                     archive_max_bytes=DEFAULT_ARCHIVE_MAX_BYTES):
    """Seal *path* into the archive once it reaches *max_bytes*; reset it.

    Returns True when a rotation happened. Failures are swallowed: log rotation
    must never break the calling request path.
    """
    try:
        if os.path.exists(path) and os.path.getsize(path) >= max_bytes:
            count, first_at, last_at = _scan_jsonl(path)
            dest = archive_segment(path, archive_dir, prefix, tag)
            os.remove(path)
            _prune(archive_dir, retain_days, retain_segments, archive_max_bytes)
            reconcile_manifest(
                archive_dir, added=os.path.basename(dest),
                added_meta={"records": count, "first_at": first_at, "last_at": last_at})
            return True
    except OSError:
        pass
    return False
