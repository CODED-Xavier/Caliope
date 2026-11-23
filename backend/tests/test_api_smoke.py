"""The web server itself: main.py imports, its routes exist, the local-only guard holds, and a few 5e endpoints answer.
Called straight through ASGI (no network, no extra packages); skipped where FastAPI isn't installed."""
import asyncio
import importlib.util
import json
import unittest

from tests.test_core import make_services, new_game

HAS_WEB = importlib.util.find_spec("fastapi") is not None


async def call(app, method: str, path: str, body=None, host: str = "127.0.0.1:8000", origin: str | None = None):
    """One request through the app; returns (status, parsed JSON or text)."""
    raw = json.dumps(body).encode() if body is not None else b""
    path, _, query = path.partition("?")
    headers = [(b"host", host.encode()), (b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode())]
    if origin:
        headers.append((b"origin", origin.encode()))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": query.encode(), "headers": headers,
             "client": ("127.0.0.1", 5000), "server": ("127.0.0.1", 8000), "root_path": ""}
    sent = {"done": False}
    out = {"status": 0, "body": b""}

    async def receive():
        if not sent["done"]:
            sent["done"] = True
            return {"type": "http.request", "body": raw, "more_body": False}
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
        elif msg["type"] == "http.response.body":
            out["body"] += msg.get("body", b"")

    await app(scope, receive, send)
    try:
        return out["status"], json.loads(out["body"] or b"null")
    except ValueError:
        return out["status"], out["body"].decode(errors="replace")


@unittest.skipUnless(HAS_WEB, "FastAPI is not installed here")
class ApiSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app import main
        self.main = main
        self.s = make_services()
        main.app.state.svc = self.s
        main.app.state.tasks = set()

    def test_routes_exist(self):
        paths = {getattr(r, "path", "") for r in self.main.app.routes}
        for p in ("/api/health", "/api/conversations/{conv_id}/character", "/api/conversations/{conv_id}/character/levels",
                  "/api/conversations/{conv_id}/character/levelup", "/api/conversations/{conv_id}/combat/options",
                  "/api/conversations/{conv_id}/character/use", "/api/conversations/{conv_id}/systems",
                  "/api/conversations/{conv_id}/refresh-card"):
            self.assertIn(p, paths)

    async def test_only_this_pc(self):
        status, _ = await call(self.main.app, "GET", "/api/settings", host="evil.example")
        self.assertEqual(status, 403)
        status, _ = await call(self.main.app, "POST", "/api/conversations", {"scenario_id": 1}, origin="https://evil.example")
        self.assertEqual(status, 403)
        status, body = await call(self.main.app, "GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertIn("ui_language", body)

    async def test_bad_bodies_are_refused_not_crashed(self):
        app = self.main.app
        cid = new_game(self.s, kind="adventure")
        for method, path, body in (("POST", "/api/conversations", {"scenario_id": {"x": 1}}),
                                   ("POST", f"/api/conversations/{cid}/pay", {"amount": {"x": 1}}),
                                   ("POST", f"/api/conversations/{cid}/fork", {})):
            status, _ = await call(app, method, path, body)
            self.assertLess(status, 500, path)

    async def test_5e_sheet_levels_and_resources(self):
        app = self.main.app
        cid = new_game(self.s, kind="adventure")
        for change in ({"op": "add", "type": "class", "name": "Paladin", "source": "PHB"},
                       {"op": "set", "field": "level", "value": 5}):
            status, body = await call(app, "PATCH", f"/api/conversations/{cid}/character", {"change": change})
            self.assertEqual(status, 200, body)
        sheet = body["sheet"]
        self.assertEqual((sheet["class"], sheet["level"]), ("Paladin", 5))
        status, rows = await call(app, "GET", f"/api/conversations/{cid}/character/levels")
        self.assertEqual(status, 200, rows)
        self.assertEqual(len(rows["levels"]), 20)
        status, plan = await call(app, "GET", f"/api/conversations/{cid}/character/levelup")
        self.assertEqual(status, 200, plan)
        self.assertEqual(plan["to_level"], 6)
        self.assertTrue(any(c["label"] == "Lay on Hands" for c in plan["changes"]))
        status, body = await call(app, "PATCH", f"/api/conversations/{cid}/character", {"change": {"op": "slot", "level": "1", "delta": 1}})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["sheet"]["slots_left"]["1"], 3)
        status, body = await call(app, "PATCH", f"/api/conversations/{cid}/character", {"change": {"op": "slot", "level": "9", "delta": 1}})
        self.assertEqual(status, 400)  # a clear refusal, not a crash
        status, opts = await call(app, "GET", f"/api/conversations/{cid}/combat/options")
        self.assertEqual(status, 200, opts)
        names = [o["name"] for g in opts["groups"].values() for o in g]
        self.assertEqual(names.count("Divine Smite"), 1)
        self.assertFalse(opts["can_smite"])

    async def test_a_risky_blast_asks_first(self):
        from app.combat import AreaRisk
        exc = AreaRisk("You would be inside Fireball's area (20 ft around Orc). Cast it anyway?", ["Aster"])
        handler = self.main.app.exception_handlers[AreaRisk]
        res = await handler(None, exc)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(json.loads(res.body)["confirm"], "risk")


if __name__ == "__main__":
    unittest.main()
