"""Protect the YooKassa webhook from accidental public TCP binding."""
import ast
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

    def test_integrated_bot_honors_host_and_port_config(self):
        tree = ast.parse((ROOT / "bot" / "bot.py").read_text())
        runner = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run_webhook_server"
        )
        calls = [
            node for node in ast.walk(runner)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "webhook_handler"
        ]
        self.assertEqual(len(calls), 1)
        args = {kw.arg: ast.unparse(kw.value) for kw in calls[0].keywords}
        self.assertEqual(args["host"], "config.WEBHOOK_HOST")
        self.assertEqual(args["port"], "config.WEBHOOK_PORT")

    def test_standalone_launcher_defaults_to_config(self):
        tree = ast.parse((ROOT / "bot" / "webhook_service.py").read_text())
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
        ]
        defaults = {}
        for call in calls:
            if call.args and isinstance(call.args[0], ast.Constant):
                name = call.args[0].value
                for keyword in call.keywords:
                    if keyword.arg == "default":
                        defaults[name] = ast.unparse(keyword.value)
        self.assertEqual(defaults["--host"], "config.WEBHOOK_HOST")
        self.assertEqual(defaults["--port"], "config.WEBHOOK_PORT")


if __name__ == "__main__":
    unittest.main()
