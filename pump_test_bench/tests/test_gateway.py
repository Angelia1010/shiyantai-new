"""统一入口（安装包部署用）：静态页面、前端路由回退、接口转发（含流式）、后端未运行时的提示。"""
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from pump_test_bench.app.services import gateway


class _Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for i in range(3):
                d = (json.dumps({"i": i}) + "\n").encode()
                self.wfile.write(b"%x\r\n%s\r\n" % (len(d), d))
                self.wfile.flush()
                time.sleep(0.3)
            self.wfile.write(b"0\r\n\r\n")
            return
        data = json.dumps({"path": self.path, "body": body.decode(), "token": self.headers.get("X-Token")}).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def gw(tmp_path, monkeypatch):
    web = tmp_path / "web"
    (web / "static").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>bench</title>", encoding="utf-8")
    (web / "static" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("WEB_ROOT", str(web))
    up = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    port = up.server_address[1]
    monkeypatch.setattr(gateway, "routes", lambda: {"/api/task/": (port, "/", 10), "/api/ai/": (port, "/", 10),
                                                    "/api/amesim/": (1, "/api/", 2)})
    srv = gateway.make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    up.shutdown()


def _get(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    return r, r.read()


def test_static_and_spa_fallback(gw):
    r, body = _get(gw, "GET", "/")
    assert r.status == 200 and b"bench" in body and r.getheader("Cache-Control") == "no-cache"
    r, body = _get(gw, "GET", "/simulation/models")  # 前端路由
    assert r.status == 200 and b"bench" in body
    r, _ = _get(gw, "GET", "/static/app.js")
    assert r.status == 200 and r.getheader("Content-Type").startswith("application/javascript")
    assert _get(gw, "GET", "/static/missing.js")[0].status == 404
    r, body = _get(gw, "GET", "/../../etc/passwd")
    assert b"root:" not in body


def test_proxy_forwards_path_body_and_headers(gw):
    r, body = _get(gw, "POST", "/api/task/auth/login?x=1", b'{"a":1}', {"X-Token": "t", "Content-Type": "application/json"})
    data = json.loads(body)
    assert r.status == 201 and data == {"path": "/auth/login?x=1", "body": '{"a":1}', "token": "t"}


def test_streaming_is_forwarded_incrementally(gw):
    c = http.client.HTTPConnection("127.0.0.1", gw, timeout=10)
    t0 = time.time()
    c.request("POST", "/api/ai/stream", body=b"{}")
    r = c.getresponse()
    first = r.readline()
    assert json.loads(first) == {"i": 0} and time.time() - t0 < 0.5  # 第一行不等全部完成就到
    assert [json.loads(r.readline())["i"] for _ in range(2)] == [1, 2]


def test_service_down_gives_clear_error(gw):
    r, body = _get(gw, "GET", "/api/amesim/models")
    assert r.status == 502 and "AMESim 服务未运行" in json.loads(body)["error"]
