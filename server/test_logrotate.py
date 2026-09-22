import gzip
import os
import tempfile
import unittest

import logrotate
import shadow_eval


def _write_jsonl(path, n):
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write('{"i":%d}\n' % i)


class LogRotate(unittest.TestCase):
    def test_rotates_to_gz_and_resets_live(self):
        with tempfile.TemporaryDirectory() as d:
            live = os.path.join(d, "live.jsonl")
            arch = os.path.join(d, "archive")
            _write_jsonl(live, 10)
            self.assertTrue(logrotate.rotate_if_needed(live, 50, arch, "prefix"))
            segs = [f for f in os.listdir(arch) if f.endswith(".jsonl.gz")]
            self.assertEqual(len(segs), 1)
            body = gzip.open(os.path.join(arch, segs[0])).read().decode()
            self.assertIn('"i":0', body)
            self.assertFalse(os.path.exists(live))

    def test_no_rotation_under_cap(self):
        with tempfile.TemporaryDirectory() as d:
            live = os.path.join(d, "live.jsonl")
            arch = os.path.join(d, "archive")
            _write_jsonl(live, 1)
            self.assertFalse(
                logrotate.rotate_if_needed(live, 10 ** 9, arch, "prefix"))
            self.assertFalse(os.path.exists(arch))

    def test_prune_drops_oldest_beyond_segment_count(self):
        import time as _time
        with tempfile.TemporaryDirectory() as d:
            base = _time.time()
            for i in range(5):
                p = os.path.join(d, "seg-%d.jsonl.gz" % i)
                with gzip.open(p, "wb") as fh:
                    fh.write(b"x")
                os.utime(p, (base - (4 - i), base - (4 - i)))
            logrotate._prune(d, retain_days=9999, retain_segments=3,
                             archive_max_bytes=10 ** 9)
            left = sorted(f for f in os.listdir(d) if f.endswith(".jsonl.gz"))
            self.assertEqual(
                left, ["seg-2.jsonl.gz", "seg-3.jsonl.gz", "seg-4.jsonl.gz"])

    def test_shadow_append_rotates_when_configured(self):
        with tempfile.TemporaryDirectory() as d:
            live = os.path.join(d, "s.jsonl")
            arch = os.path.join(d, "a")
            with open(live, "w", encoding="utf-8") as fh:
                fh.write("x" * 200)
            rotation = {"max_bytes": 50, "archive_dir": arch, "prefix": "p"}
            self.assertTrue(
                shadow_eval.append_event(live, {"a": 1}, rotation=rotation))
            self.assertTrue(
                [f for f in os.listdir(arch) if f.endswith(".jsonl.gz")])


    def test_manifest_indexes_segments(self):
        with tempfile.TemporaryDirectory() as d:
            live = os.path.join(d, "live.jsonl")
            arch = os.path.join(d, "a")
            _write_jsonl(live, 7)
            logrotate.rotate_if_needed(live, 50, arch, "p")
            import json as j
            manifest = j.load(open(os.path.join(arch, "MANIFEST.json"), encoding="utf-8") )
            seg = list(manifest["segments"])[0]
            self.assertEqual(manifest["segments"][seg]["records"], 7)


if __name__ == "__main__":
    unittest.main()
