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


