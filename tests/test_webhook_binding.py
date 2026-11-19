"""Protect the YooKassa webhook from accidental public TCP binding."""
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def configured_host(override=None):
    env = os.environ.copy()
    env.pop("WEBHOOK_HOST", None)
    if override is not None:
        env["WEBHOOK_HOST"] = override
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import sys; sys.path.insert(0, 'bot'); "
            "from config import config; print(config.WEBHOOK_HOST)",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class WebhookBindTests(unittest.TestCase):
    def test_default_bind_is_loopback(self):
        self.assertEqual(configured_host(), "127.0.0.1")

    def test_explicit_override_is_preserved(self):
        self.assertEqual(configured_host("0.0.0.0"), "0.0.0.0")


if __name__ == "__main__":
    unittest.main()
