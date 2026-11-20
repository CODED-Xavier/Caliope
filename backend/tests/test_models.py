"""Tests for the Models window backend (no internet: Hugging Face is faked)."""
import asyncio
import hashlib
import tempfile
import unittest
from pathlib import Path

from app import modelhub, runtime
from app.modelhub import ModelError, ModelHub, quant_of
from tests.test_core import make_services

BLOB = b"GGUF" + bytes(range(256)) * 40  # 10244 bytes


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "models"
        self.root.mkdir()
        self._old = (runtime.MODEL_DIRS, modelhub.download_root, runtime.ENGINE_DIR)
        runtime.MODEL_DIRS = [self.root]
        runtime.ENGINE_DIR = self.tmp / "engine"
        modelhub.download_root = lambda: self.root
        self.svc = make_services()
        self.tree = [
            {"type": "file", "path": "README.md", "size": 10},
            {"type": "file", "path": "Stheno-Q4_K_S.gguf", "size": len(BLOB), "lfs": {"size": len(BLOB), "oid": hashlib.sha256(BLOB).hexdigest()}},
            {"type": "file", "path": "mmproj-f16.gguf", "size": 5},
            {"type": "file", "path": "big/Big-Q8_0-00002-of-00002.gguf", "size": 3, "lfs": {"size": 3, "oid": hashlib.sha256(b"def").hexdigest()}},
            {"type": "file", "path": "big/Big-Q8_0-00001-of-00002.gguf", "size": 3, "lfs": {"size": 3, "oid": hashlib.sha256(b"abc").hexdigest()}},
        ]
        self.served = {"Stheno-Q4_K_S.gguf": BLOB, "big/Big-Q8_0-00001-of-00002.gguf": b"abc", "big/Big-Q8_0-00002-of-00002.gguf": b"def"}
        self.requests = []

        async def fetch_json(url):
            self.requests.append(url)
            if "/tree/" in url:
                return self.tree
            return [{"id": "bartowski/L3-8B-Stheno-v3.2-GGUF", "downloads": 74666, "likes": 84, "tags": ["gguf", "en", "license:x", "roleplay"]},
                    {"id": "someone/private", "private": True}, {"id": "bad id"}]

        async def stream(url, start=0):
            name = url.split("/resolve/main/")[1].replace("%2F", "/")
            data = self.served[name][start:]
            for i in range(0, len(data), 1000):
                yield data[i:i + 1000]
                await asyncio.sleep(0)

        self.hub = ModelHub(self.svc.db, self.svc.runtime, self.svc.settings.all, self.svc.settings.update, fetch_json, stream)

    def tearDown(self):
        runtime.MODEL_DIRS, modelhub.download_root, runtime.ENGINE_DIR = self._old

    async def wait(self, key):
        await asyncio.wait_for(self.hub._tasks[key], 5)


class SearchTests(Base):
    async def test_search_and_files(self):
        found = await self.hub.search("stheno")
        self.assertEqual([r["id"] for r in found], ["bartowski/L3-8B-Stheno-v3.2-GGUF"])
        self.assertEqual(found[0]["tags"], ["en", "roleplay"])
        self.assertIn("search=stheno", self.requests[0])
        files = await self.hub.files("bartowski/L3-8B-Stheno-v3.2-GGUF")
        self.assertEqual([f["name"] for f in files], ["Big-Q8_0.gguf", "Stheno-Q4_K_S.gguf"])
        big = files[0]
        self.assertEqual([p["path"] for p in big["parts"]], ["big/Big-Q8_0-00001-of-00002.gguf", "big/Big-Q8_0-00002-of-00002.gguf"])
        self.assertEqual(files[1]["quant"], "Q4_K_S")
        self.assertIn("recommended", files[1]["note"])
        with self.assertRaises(ModelError):
            await self.hub.files("../etc")
        self.assertEqual(quant_of("x.IQ3_XS.gguf"), "IQ3_XS")


class DownloadTests(Base):
    async def test_download_verify_and_list(self):
        item = self.hub.start_download("a/b", "Stheno-Q4_K_S.gguf")
        await self.wait(item["key"])
        self.assertEqual(item["state"], "done", item["error"])
        path = self.root / "a" / "b" / "Stheno-Q4_K_S.gguf"
        self.assertEqual(path.read_bytes(), BLOB)
        local = self.hub.local()
        self.assertEqual(local[0]["repo"], "a/b")
        self.assertEqual((await self.hub.files("a/b"))[1]["installed"], True)

    async def test_split_download_and_delete_all_parts(self):
        item = self.hub.start_download("a/b", "big/Big-Q8_0-00001-of-00002.gguf")
        await self.wait(item["key"])
        self.assertEqual(item["state"], "done", item["error"])
        self.assertEqual(item["done"], 6)
        names = [m["name"] for m in self.hub.local()]
        self.assertEqual(names, ["Big-Q8_0-00001-of-00002.gguf"])  # shown once
        await self.hub.delete(item["path"])
        self.assertFalse((self.root / "a").exists())  # empty folders tidied

    async def test_resume_and_checksum(self):
        folder = self.root / "a" / "b"
        folder.mkdir(parents=True)
        (folder / "Stheno-Q4_K_S.gguf.part").write_bytes(BLOB[:4000])
        item = self.hub.start_download("a/b", "Stheno-Q4_K_S.gguf")
        await self.wait(item["key"])
        self.assertEqual((folder / "Stheno-Q4_K_S.gguf").read_bytes(), BLOB)

        self.served["Stheno-Q4_K_S.gguf"] = b"X" * len(BLOB)
        (folder / "Stheno-Q4_K_S.gguf").unlink()
        item = self.hub.start_download("a/b", "Stheno-Q4_K_S.gguf")
        await self.wait(item["key"])
        self.assertEqual(item["state"], "error")
        self.assertIn("checksum", item["error"])
        self.assertFalse((folder / "Stheno-Q4_K_S.gguf").exists())

    async def test_cancel_and_forget_removes_part(self):
        async def slow(url, start=0):
            yield BLOB[:100]
            await asyncio.sleep(10)
            yield BLOB[100:]

        self.hub._stream = slow
        item = self.hub.start_download("a/b", "Stheno-Q4_K_S.gguf")
        await asyncio.sleep(0.1)
        self.assertEqual(item["state"], "downloading")
        self.hub.cancel(item["key"])
        await asyncio.sleep(0.05)
        self.assertEqual(item["state"], "cancelled")
        self.assertTrue((self.root / "a" / "b" / "Stheno-Q4_K_S.gguf.part").exists())
        self.hub.forget(item["key"])
        self.assertFalse((self.root / "a" / "b" / "Stheno-Q4_K_S.gguf.part").exists())
        self.assertEqual(self.hub.list_downloads(), [])

    def test_rejects_bad_requests(self):
        for repo, file in (("a/b", "../x.gguf"), ("a/b", "x.exe"), ("nope", "x.gguf")):
            with self.assertRaises(ModelError):
                self.hub.start_download(repo, file)


class LocalTests(Base):
    async def test_hide_load_and_safe_delete(self):
        m = self.root / "x" / "y" / "Model-Q4_K_M.gguf"
        m.parent.mkdir(parents=True)
        m.write_bytes(b"x")
        self.hub.set_disabled(str(m), True)
        self.assertTrue(self.hub.local()[0]["disabled"])
        self.hub.set_disabled(str(m), False)
        self.assertFalse(self.hub.local()[0]["disabled"])
        with self.assertRaises(ModelError):  # engine not downloaded
            self.hub.load_values(str(m))
        (runtime.ENGINE_DIR).mkdir()
        (runtime.ENGINE_DIR / "llama-server").write_text("x")
        values = self.hub.load_values(str(m))
        self.assertEqual(values, {"ai_engine": "builtin", "engine_model_path": str(m)})
        self.svc.settings.update(values)
        self.assertEqual(self.hub.local()[0]["selected"], "story")

        outside = self.tmp / "Other.gguf"
        outside.write_bytes(b"x")
        with self.assertRaises(ModelError):
            await self.hub.delete(str(outside))
        await self.hub.delete(str(m))
        self.assertFalse(m.exists())
        self.assertEqual(self.svc.settings.get("engine_model_path"), "")


if __name__ == "__main__":
    unittest.main()


class FolderTests(Base):
    def setUp(self):
        super().setUp()
        self._lm = modelhub.lmstudio_folder
        modelhub.lmstudio_folder = lambda: None

    def tearDown(self):
        modelhub.lmstudio_folder = self._lm
        super().tearDown()

    def test_add_folder_lists_its_models(self):
        other = self.tmp / "D" / "lmstudio-models" / "bartowski"
        other.mkdir(parents=True)
        (other / "Stheno-Q4_K_S.gguf").write_bytes(BLOB)
        self.assertEqual(self.hub.local(), [])
        added = self.hub.add_folder(f'"{other / "Stheno-Q4_K_S.gguf"}"')  # a pasted file path, with quotes
        self.assertEqual(added, str(other.resolve()))
        self.assertEqual([m["name"] for m in self.hub.local()], ["Stheno-Q4_K_S.gguf"])
        self.assertTrue(any(f["added"] and f["path"] == added for f in self.hub.folders()))
        self.hub.add_folder(str(other))  # adding twice keeps one entry
        self.assertEqual(self.hub.added_folders(), [added])
        self.hub.remove_folder(added)
        self.assertEqual(self.hub.local(), [])
        self.assertTrue((other / "Stheno-Q4_K_S.gguf").exists())  # removing a folder never deletes files

    def test_bad_folders(self):
        with self.assertRaises(ModelError):
            self.hub.add_folder(str(self.tmp / "missing"))
        empty = self.tmp / "empty"
        empty.mkdir()
        with self.assertRaises(ModelError):
            self.hub.add_folder(str(empty))
        with self.assertRaises(ModelError):
            self.hub.add_folder(str(Path.home()))

    def test_lmstudio_moved_folder(self):
        moved = self.tmp / "E" / "models"
        moved.mkdir(parents=True)
        (moved / "x-Q4_K_M.gguf").write_bytes(BLOB)
        modelhub.lmstudio_folder = lambda: moved
        self.assertEqual([m["name"] for m in self.hub.local()], ["x-Q4_K_M.gguf"])
