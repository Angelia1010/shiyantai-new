"""统一入口（安装包部署用，取代 Nginx）：同一个端口提供前端页面，并把 /api/<服务> 转发到本机的各后端服务。

    /             前端静态文件（WEB_ROOT，默认 digital-twin-platform/dist），找不到的路径回到 index.html（前端路由）
    /api/task/    → 任务服务 TASK_SERVICE_PORT
    /api/file/    → 文件服务 FILE_SERVICE_PORT
    /api/ai/      → 大模型分析服务 LLM_SERVICE_PORT（流式响应边收边转发）
    /api/amesim/  → AMESim 服务 AMESIM_SERVICE_PORT（其路由以 /api 开头）

与 deploy/nginx.conf 的转发规则一致。只用标准库，不需要额外依赖。
监听地址 GATEWAY_HOST（默认 127.0.0.1；允许局域网访问时为 0.0.0.0），端口 GATEWAY_PORT（默认 8080）。
后端服务始终只监听本机，对外只有这个入口。

单独运行：python -m pump_test_bench.app.services.gateway（通常由 supervisor 启动）
"""
import http.client
import logging
import mimetypes
import os
import posixpath
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import unquote, urlsplit

from shared.config import REPO_ROOT, get_settings

logger = logging.getLogger("gateway")
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
              "transfer-encoding", "upgrade", "host", "content-length"}
CHUNK = 64 * 1024
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("video/mp4", ".mp4")


def routes() -> Dict[str, Tuple[int, str, float]]:
    """前缀 → (端口, 转发后的路径前缀, 读超时秒)。"""
    s = get_settings()
    return {
        "/api/task/": (s.task_service_port, "/", 300),
        "/api/file/": (s.file_service_port, "/", 300),
        "/api/ai/": (s.llm_service_port, "/", 3600),
        "/api/amesim/": (s.amesim_service_port, "/api/", 900),
    }


def web_root() -> Path:
    value = os.environ.get("WEB_ROOT", "").strip()
    return Path(value) if value else REPO_ROOT / "digital-twin-platform" / "dist"


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "BenchGateway"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 写入日志而不是标准错误
        logger.debug("%s %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------------ 分派
    def _dispatch(self):
        path = urlsplit(self.path).path
        for prefix, target in routes().items():
            if path.startswith(prefix) or path + "/" == prefix:
                return self._proxy(prefix, *target)
        if self.command in ("GET", "HEAD"):
            return self._static(path)
        self._plain(405, "Method Not Allowed")

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _dispatch

    # ------------------------------------------------------------------ 转发
    def _proxy(self, prefix: str, port: int, upstream_prefix: str, timeout: float):
        rest = self.path[len(prefix):] if self.path.startswith(prefix) else ""
        target = upstream_prefix + rest
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        headers["Host"] = f"127.0.0.1:{port}"
        headers["X-Forwarded-For"] = self.client_address[0]
        if body is not None:
            headers["Content-Length"] = str(len(body))
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        try:
            conn.request(self.command, target, body=body, headers=headers)
            resp = conn.getresponse()
        except (ConnectionRefusedError, socket.timeout, OSError) as exc:
            conn.close()
            name = {"/api/ai/": "智能助手服务", "/api/amesim/": "AMESim 服务"}.get(prefix, "后端服务")
            logger.warning("转发 %s 失败：%s", self.path, exc)
            return self._json(502, f'{{"error": "{name}未运行或无响应，请稍后重试；如持续出现，请查看日志目录中的日志"}}')
        try:
            self.send_response(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() not in HOP_BY_HOP:
                    self.send_header(k, v)
            clen = resp.getheader("Content-Length")
            if clen is not None and self.command != "HEAD":
                self.send_header("Content-Length", clen)
                self.end_headers()
                remaining = int(clen)
                while remaining > 0:
                    data = resp.read(min(CHUNK, remaining))
                    if not data:
                        break
                    self.wfile.write(data)
                    remaining -= len(data)
            else:
                # 长度未知（流式响应）：分块转发，收到一块发一块
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                if self.command != "HEAD":
                    while True:
                        data = resp.read1(CHUNK) if hasattr(resp, "read1") else resp.read(CHUNK)
                        if not data:
                            break
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
                        self.wfile.flush()
                    self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass  # 浏览器提前断开
        finally:
            conn.close()

    # ------------------------------------------------------------------ 静态文件
    def _static(self, path: str):
        root = web_root()
        rel = posixpath.normpath(unquote(path)).lstrip("/")
        file = (root / rel).resolve() if rel not in ("", ".") else root / "index.html"
        try:
            file.relative_to(root.resolve())
        except ValueError:
            return self._plain(403, "Forbidden")
        if not file.is_file():
            if "." in posixpath.basename(rel):  # 缺少的资源文件
                return self._plain(404, "Not Found")
            file = root / "index.html"      # 前端路由
        if not file.is_file():
            return self._plain(503, f"前端页面不存在：{root}")
        ctype = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        size = file.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        # index.html 不缓存（升级后立即生效）；带哈希的资源长期缓存
        self.send_header("Cache-Control", "no-cache" if file.name == "index.html" else "public, max-age=604800")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(file, "rb") as f:
            while True:
                data = f.read(CHUNK)
                if not data:
                    break
                self.wfile.write(data)

    def _plain(self, code: int, text: str):
        data = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, code: int, text: str):
        data = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(host: Optional[str] = None, port: Optional[int] = None) -> GatewayServer:
    host = host or os.environ.get("GATEWAY_HOST", "127.0.0.1")
    port = int(port or os.environ.get("GATEWAY_PORT", "8080"))
    return GatewayServer((host, port), GatewayHandler)


def main() -> None:
    from shared.logging_setup import setup_logging
    setup_logging("gateway")
    server = make_server()
    logger.info("统一入口：http://%s:%s（页面：%s）", *server.server_address[:2], web_root())
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
