"""Run the Node unit tests for the vendored stealth-forward module.

The proxy discovery / CONNECT logic lives in vendored JavaScript, so it is
tested with `node --test`. This wrapper locates a Node runtime and integrates
that run into the Python suite; it skips cleanly when Node is unavailable.
"""
import os
import shutil
import subprocess
import unittest

_NODE_CANDIDATES = [
    r"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime"
    r"\dependencies\node\bin\node.exe",
]


def find_node():
    for candidate in _NODE_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("node")


class NativeStealthJs(unittest.TestCase):
    def test_node_unit_tests_pass(self):
        node = find_node()
        if not node:
            self.skipTest("Node runtime not available")
        here = os.path.dirname(os.path.abspath(__file__))
        test_file = os.path.join(here, "native-stealth-forward.test.mjs")
        proc = subprocess.run(
            [node, "--test", test_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            self.fail(proc.stdout)


if __name__ == "__main__":
    unittest.main()
