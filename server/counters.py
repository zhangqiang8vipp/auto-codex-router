"""Daily, persisted operational counters.

Counters are maintained incrementally in code (never by scanning the large
logs), persisted to a small JSON file, and reset naturally per calendar day.
They let /control/status show how many times the runtime avoided a paid Jev
decision without any expensive aggregation.
"""
import json
import os
import threading
import time

FIELDS = ("total", "jev_decisions", "jev_cache_hits", "lease_keep",
          "local_escalations", "fallbacks")


class DailyCounters:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._last_flush = 0.0
        self.data = self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and isinstance(data.get("days"), dict):
                return data
        except (OSError, ValueError):
            pass
        return {"version": 1, "days": {}}

    @staticmethod
    def _today():
        return time.strftime("%Y-%m-%d")

    def record(self, route_source, jev_cache=None):
        """Increment today's counters based on the request's route source."""
        day = self._today()
        with self._lock:
            bucket = self.data.setdefault("days", {}).setdefault(
                day, {key: 0 for key in FIELDS})
            bucket["total"] = bucket.get("total", 0) + 1
            if route_source == "jev":
                bucket["jev_decisions"] = bucket.get("jev_decisions", 0) + 1
                if jev_cache and jev_cache != "miss":
                    bucket["jev_cache_hits"] = bucket.get("jev_cache_hits", 0) + 1
            elif route_source == "lease":
                bucket["lease_keep"] = bucket.get("lease_keep", 0) + 1
            elif route_source == "lease_escalation":
                bucket["local_escalations"] = bucket.get("local_escalations", 0) + 1
            elif route_source in ("fallback", "jev_error_fallback", "off"):
                bucket["fallbacks"] = bucket.get("fallbacks", 0) + 1
            if time.time() - self._last_flush > 5:
                self._flush_locked()

    def _flush_locked(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh)
            os.replace(tmp, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            self._last_flush = time.time()
        except OSError:
            pass

    def flush(self):
        with self._lock:
            self._flush_locked()

    def today(self):
        day = self._today()
        with self._lock:
            bucket = dict(self.data.get("days", {}).get(
                day, {key: 0 for key in FIELDS}))
        total = bucket.get("total", 0)
        jev = bucket.get("jev_decisions", 0)
        keep = bucket.get("lease_keep", 0)
        bucket["date"] = day
        # How many completed requests did NOT need a fresh Jev decision.
        bucket["jev_saved"] = max(0, total - jev)
        bucket["jev_share_pct"] = round(100 * jev / total, 1) if total else 0.0
        bucket["keep_pct"] = round(100 * keep / total, 1) if total else 0.0
        return bucket
