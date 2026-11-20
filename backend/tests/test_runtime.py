"""Tests for the built-in AI engine manager (no real llama.cpp needed)."""
import asyncio
import io
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from app import runtime
from app.config import DEFAULT_SETTINGS, embedding_key
from app.llm import LLMClient
from app.runtime import EngineError, EngineManager, build_command, find_models, server_binary
from tests.test_core import make_services


class Paths(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._old = (runtime.ENGINE_DIR, runtime.LOG_PATH, runtime.PID_PATH, runtime.DATA_DIR)
        runtime.ENGINE_DIR = self.tmp / "engine"
        runtime.DATA_DIR = self.tmp / "data"
        runtime.LOG_PATH = runtime.DATA_DIR / "engine.log"
        runtime.PID_PATH = runtime.DATA_DIR / "engine.pid"
        self.settings = dict(DEFAULT_SETTINGS, ai_engine="builtin", engine_port=18091)

    def tearDown(self):
        runtime.ENGINE_DIR, runtime.LOG_PATH, runtime.PID_PATH, runtime.DATA_DIR = self._old

    def fake_server(self) -> Path:
        d = runtime.ENGINE_DIR / "llama-b1"
        d.mkdir(parents=True)
        p = d / "llama-server"
        p.write_text("#!/bin/sh\nsleep 30\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        return p


class FindingTests(Paths):
    def test_models_found_and_sorted(self):
        d = self.tmp / "lm" / "author" / "repo"
        d.mkdir(parents=True)
        (d / "Stheno-8B.Q4_K_S.gguf").write_bytes(b"0" * 3000)
        (d / "small.Q2.gguf").write_bytes(b"0" * 1000)
        (d / "mmproj-f16.gguf").write_bytes(b"0")
        (d / "nomic-embed-text-v1.5.Q8_0.gguf").write_bytes(b"0" * 5000)
        found = find_models([self.tmp / "lm", self.tmp / "missing"])
        self.assertEqual([m["name"] for m in found], ["Stheno-8B.Q4_K_S.gguf", "small.Q2.gguf", "nomic-embed-text-v1.5.Q8_0.gguf"])
        self.assertTrue(found[-1]["embedding"])

    def test_binary_and_command(self):
        self.assertIsNone(server_binary())
        p = self.fake_server()
        self.assertEqual(server_binary(), p)
        cmd = build_command(p, "m.gguf", 8192, 8091, "auto")
        self.assertEqual(cmd[cmd.index("-c") + 1], "8192")
        self.assertIn("--cache-reuse", cmd)
        self.assertEqual(cmd[cmd.index("--port") + 1], "8091")
        emb = build_command(p, "e.gguf", 2048, 8092, "all", embedding=True)
        self.assertIn("--embeddings", emb)
        self.assertNotIn("--cache-reuse", emb)


class StartTests(Paths):
    async def test_errors_are_explained(self):
        rt = EngineManager(lambda: self.settings)
        st = await rt.start()
        self.assertEqual(st["state"], "error")
        self.assertIn("not downloaded", st["message"])
        self.fake_server()
        st = await rt.start()
        self.assertIn("Choose a model", st["message"])
        rt2 = EngineManager(lambda: dict(self.settings, ai_engine="lmstudio"))
        self.assertEqual((await rt2.start())["state"], "stopped")

    @unittest.skipIf(os.name == "nt", "uses a shell script as the fake server")
    async def test_start_ready_stop(self):
        self.fake_server()
        model = self.tmp / "m.gguf"
        model.write_bytes(b"x")
        emb = self.tmp / "e.gguf"
        emb.write_bytes(b"x")
        self.settings.update(engine_model_path=str(model), engine_embedding_path=str(emb))
        calls = []

        async def http_get(url):
            calls.append(url)
            return 200 if len(calls) >= 2 else 503

        rt = EngineManager(lambda: self.settings, http_get=http_get)
        st = await rt.start()
        self.assertEqual(st["state"], "ready")
        self.assertEqual(calls[0], "http://127.0.0.1:18091/health")
        self.assertIsNotNone(rt.embed)
        self.assertTrue(runtime.PID_PATH.exists())
        self.assertIn("-m", runtime.LOG_PATH.read_text())
        chat = rt.chat
        await rt.stop()
        self.assertIsNotNone(chat.poll())
        self.assertFalse(runtime.PID_PATH.exists())
        self.assertEqual(rt.status()["state"], "stopped")

    @unittest.skipIf(os.name == "nt", "uses a shell script as the fake server")
    async def test_crash_while_loading(self):
        p = self.fake_server()
        p.write_text("#!/bin/sh\necho 'out of memory'\nexit 1\n")
        model = self.tmp / "m.gguf"
        model.write_bytes(b"x")
        self.settings["engine_model_path"] = str(model)

        async def never(url):
            return 503

        rt = EngineManager(lambda: self.settings, http_get=never)
        st = await rt.start()
        self.assertEqual(st["state"], "error")
        self.assertIn("video memory", st["message"])
        self.assertIn("out of memory", st["log"])


class DownloadTests(Paths):
    @staticmethod
    def zipped(files: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in files.items():
                z.writestr(name, data)
        return buf.getvalue()

    async def test_download_picks_vulkan_asset(self):
        releases = [{"assets": [{"name": "llama-b9-bin-win-cuda-x64.zip", "browser_download_url": "u/cuda"},
                                {"name": "llama-b9-bin-win-vulkan-x64.zip", "browser_download_url": "u/vulkan"}]}]
        got = []

        async def fj(url):
            return releases

        async def fb(url, progress):
            got.append(url)
            progress(5, 10)
            return self.zipped({"llama-server.exe": b"bin", "ggml.dll": b"x"})

        rt = EngineManager(lambda: self.settings)
        await rt.download(fj, fb)
        self.assertEqual(got, ["u/vulkan"])
        self.assertTrue((runtime.ENGINE_DIR / "llama-server.exe").is_file())
        self.assertIn("u/vulkan", (runtime.ENGINE_DIR / "SOURCE.txt").read_text())
        self.assertEqual(rt.state, "stopped")

    async def test_falls_back_to_pinned_and_rejects_bad_zips(self):
        async def fj(url):
            raise OSError("offline")

        urls = []

        async def bad(url, progress):
            urls.append(url)
            return self.zipped({"../evil.exe": b"x", "llama-server.exe": b"x"})

        rt = EngineManager(lambda: self.settings)
        with self.assertRaises(EngineError):
            await rt.download(fj, bad)
        self.assertIn(runtime.PINNED_TAG, urls[0])
        self.assertEqual(rt.state, "error")
        self.assertFalse((self.tmp / "evil.exe").exists())

        async def empty(url, progress):
            return self.zipped({"readme.txt": b"x"})

        with self.assertRaises(EngineError):
            await rt.download(fj, empty)


class SettingsAndClientTests(unittest.IsolatedAsyncioTestCase):
    def test_settings_validation(self):
        svc = make_services()
        s = svc.settings.update({"ai_engine": "builtin", "engine_gpu_layers": " 28 "})
        self.assertEqual(s["engine_gpu_layers"], "28")
        for bad in ({"ai_engine": "ollama"}, {"engine_gpu_layers": "lots"}, {"engine_port": 80}):
            with self.assertRaises(ValueError):
                svc.settings.update(bad)

    def test_client_urls_and_embedding_key(self):
        s = dict(DEFAULT_SETTINGS, ai_engine="builtin", engine_port=9000, engine_embedding_path=r"C:\m\nomic-embed.Q8.gguf")
        c = LLMClient(lambda: s)
        self.assertEqual(c._base(), "http://127.0.0.1:9000/v1")
        self.assertEqual(c._embed_base(), "http://127.0.0.1:9001/v1")
        self.assertTrue(embedding_key(s).startswith("gguf:"))
        lm = dict(DEFAULT_SETTINGS, embedding_model="text-embedding-nomic")
        self.assertEqual(LLMClient(lambda: lm)._base(), "http://localhost:1234/v1")
        self.assertEqual(embedding_key(lm), "text-embedding-nomic")
        self.assertEqual(embedding_key(dict(DEFAULT_SETTINGS, ai_engine="builtin")), "")

    async def test_builtin_model_name_and_schema(self):
        s = dict(DEFAULT_SETTINGS, ai_engine="builtin")
        c = LLMClient(lambda: s)
        self.assertEqual(await c._resolve_model(), "local")
        sent = {}

        class Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": "{}"}}]}

        class Http:
            async def post(self, url, json=None, headers=None):
                sent.update(json)
                return Resp()

        async def http():
            return Http()

        c._http = http
        import sys
        import types
        fake = "httpx" not in sys.modules  # the sandbox may lack httpx; only its error class is touched here
        if fake:
            sys.modules["httpx"] = types.SimpleNamespace(HTTPError=OSError)
        try:
            await c.chat([{"role": "user", "content": "x"}], json_schema={"type": "object"})
        finally:
            if fake:
                del sys.modules["httpx"]
        self.assertEqual(sent["response_format"]["schema"], {"type": "object"})
        self.assertEqual(sent["response_format"]["json_schema"]["schema"], {"type": "object"})


if __name__ == "__main__":
    unittest.main()
