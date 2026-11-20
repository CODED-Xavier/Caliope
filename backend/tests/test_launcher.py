"""Tests for the one-click launcher (v0.9.0)."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import launcher


def touch(path: Path, when: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    os.utime(path, (when, when))


class BuildCheckTests(unittest.TestCase):
    def setUp(self):
        self.front = Path(tempfile.mkdtemp())
        now = time.time()
        touch(self.front / "src" / "App.jsx", now - 100)
        touch(self.front / "package.json", now - 100)

    def test_missing_build_needs_build(self):
        self.assertTrue(launcher.needs_build(self.front))

    def test_fresh_build_and_changed_code(self):
        touch(self.front / "dist" / "index.html", time.time() - 10)
        self.assertFalse(launcher.needs_build(self.front))
        touch(self.front / "src" / "components" / "New.jsx", time.time())
        self.assertTrue(launcher.needs_build(self.front))

    def test_npm_install_check(self):
        self.assertTrue(launcher.needs_npm_install(self.front))
        touch(self.front / "node_modules" / ".package-lock.json", time.time())
        self.assertFalse(launcher.needs_npm_install(self.front))

    def test_no_node_keeps_old_build(self):
        touch(self.front / "dist" / "index.html", time.time() - 1000)
        with mock.patch.object(launcher, "find_npm", return_value=None), mock.patch.object(launcher, "say"):
            self.assertTrue(launcher.build_interface(self.front))
        (self.front / "dist" / "index.html").unlink()
        with mock.patch.object(launcher, "find_npm", return_value=None), mock.patch.object(launcher, "say"):
            self.assertFalse(launcher.build_interface(self.front))


class LMStudioTests(unittest.TestCase):
    def test_root_url(self):
        self.assertEqual(launcher.lmstudio_root("http://localhost:1234/v1"), "http://localhost:1234")
        self.assertEqual(launcher.lmstudio_root("http://localhost:1234/v1/"), "http://localhost:1234")
        self.assertEqual(launcher.lmstudio_root(""), "http://localhost:1234")

    def test_loaded_models(self):
        data = {"data": [{"id": "stheno", "state": "loaded", "type": "llm"}, {"id": "nomic", "state": "loaded", "type": "embeddings"},
                         {"id": "other", "state": "not-loaded", "type": "llm"}]}
        with mock.patch.object(launcher, "get_json", return_value=data):
            self.assertEqual(launcher.loaded_models("http://localhost:1234/v1"), ["stheno"])
        with mock.patch.object(launcher, "get_json", return_value=None):
            self.assertIsNone(launcher.loaded_models("http://localhost:1234/v1"))

    def test_loads_model_when_nothing_loaded(self):
        calls = []
        settings = {"llm_base_url": "http://localhost:1234/v1", "model": "stheno", "context_window": 12288}
        with mock.patch.object(launcher, "find_lms", return_value="lms"), \
             mock.patch.object(launcher, "get_json", side_effect=lambda url, timeout=3.0: {"llm": {"ok": True}} if "health" in url else {"data": []}), \
             mock.patch.object(launcher.subprocess, "call", side_effect=lambda cmd, **kw: calls.append(cmd) or 0), \
             mock.patch.object(launcher, "say"):
            launcher.prepare_lmstudio(settings)
        self.assertEqual(calls, [["lms", "load", "stheno", "--context-length", "12288", "-y"]])

    def test_remote_server_is_left_alone(self):
        with mock.patch.object(launcher.subprocess, "call") as call:
            launcher.prepare_lmstudio({"llm_base_url": "http://192.168.0.5:1234/v1"})
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
