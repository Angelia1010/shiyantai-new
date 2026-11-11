"""文件服务（默认端口 5002，前端代理前缀 /api/file）。

负责列出数据目录中的文件、分页读取试验数据，以及监控目录中的新增/修改文件。

接口一览：
    GET  /files?path=                         列出目录下的数据文件
    GET  /files/page?path=&file_name=&page=&page_size=   分页读取文件内容
    GET  /watch                               当前监控目录
    POST /watch {path}                        切换监控目录
    GET  /watch/events?since=<seq>            取序号 since 之后的文件事件

文件事件带递增序号，每个页面各自记住自己读到的序号，因此多个页面同时轮询
也不会互相“抢走”事件。

启动：在仓库根目录执行 ``python -m pump_test_bench.app.services.file_service``
"""
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional

from flask import jsonify, request
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from pump_test_bench.app.core.data_reader import TABLE_SUFFIXES, TDMS_SUFFIXES, read_page
from shared.config import get_settings
from shared.flask_app import create_app, json_body
from shared.logging_setup import setup_logging
from shared.paths import resolve_data_dir, resolve_data_file

SERVICE_NAME = "file_service"
logger = logging.getLogger(SERVICE_NAME)
LISTED_SUFFIXES = TABLE_SUFFIXES + TDMS_SUFFIXES

app = create_app(SERVICE_NAME)


class FileWatcher:
    """监控单个目录，把文件事件记录在带序号的环形缓冲区里。

    试验台写文件时会连续触发多次事件。这里做“尾部防抖”：同一文件最后一次事件之后
    安静 SETTLE_SECONDS 秒才发布一条事件，这样前端拿到事件时文件已经写完。
    """

    MAX_EVENTS = 1000
    SETTLE_SECONDS = 2.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._observer: Optional[Observer] = None
        self._directory: Optional[Path] = None
        self._events: Deque[Dict] = deque(maxlen=self.MAX_EVENTS)
        self._seq = 0
        self._pending: Dict[str, Dict] = {}
        self._flusher = threading.Thread(target=self._flush_loop, name="watch-flusher", daemon=True)
        self._flusher.start()

    @property
    def directory(self) -> Optional[Path]:
        return self._directory

    def watch(self, directory: Path) -> None:
        with self._lock:
            if self._directory == directory and self._observer is not None:
                return
            self._stop_locked()
            handler = _Handler(self)
            observer = Observer()
            observer.schedule(handler, str(directory), recursive=False)
            observer.start()
            self._observer = observer
            self._directory = directory
            self._pending.clear()
        logger.info("开始监控目录：%s", directory)

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

    def record(self, kind: str, path: str) -> None:
        name = Path(path).name
        if not name.lower().endswith(LISTED_SUFFIXES):
            return
        with self._lock:
            pending = self._pending.get(name)
            if pending is None:
                self._pending[name] = {"type": kind, "last": time.monotonic()}
            else:
                pending["last"] = time.monotonic()  # 保留这一串事件里第一个事件的类型

    def flush(self, force: bool = False) -> None:
        """发布已经安静下来的文件事件（force=True 时全部发布，供测试使用）。"""
        now = time.monotonic()
        with self._lock:
            ready = [n for n, p in self._pending.items() if force or now - p["last"] >= self.SETTLE_SECONDS]
            for name in sorted(ready):
                pending = self._pending.pop(name)
                self._seq += 1
                self._events.append({
                    "seq": self._seq,
                    "type": pending["type"],
                    "file_name": name,
                    "directory": str(self._directory),
                    "time": int(time.time() * 1000),
                })

    def _flush_loop(self) -> None:
        while True:
            time.sleep(0.5)
            try:
                self.flush()
            except Exception:  # 不能让后台线程退出
                logger.exception("发布文件事件失败")

    def events_since(self, since: int) -> Dict:
        with self._lock:
            events: List[Dict] = [e for e in self._events
                                  if e["seq"] > since and e["directory"] == str(self._directory)]
            return {"latest_seq": self._seq, "directory": str(self._directory) if self._directory else None,
                    "events": events}


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: FileWatcher) -> None:
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher.record("created", event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher.record("modified", event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher.record("created", event.dest_path)


watcher = FileWatcher()


def _int_arg(name: str, default: int) -> int:
    value = request.args.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"参数 {name} 必须是整数") from None


@app.get("/files")
def list_files():
    directory = resolve_data_dir(request.args.get("path"))
    files = sorted(p.name for p in directory.iterdir()
                   if p.is_file() and p.name.lower().endswith(LISTED_SUFFIXES))
    return jsonify({"path": str(directory), "files": files})


@app.get("/files/page")
def file_page():
    path = resolve_data_file(request.args.get("path"), request.args.get("file_name"), TABLE_SUFFIXES)
    return jsonify(read_page(path, _int_arg("page", 0), _int_arg("page_size", 500)))


@app.get("/watch")
def get_watch():
    directory = watcher.directory
    return jsonify({"path": str(directory) if directory else None})


@app.post("/watch")
def set_watch():
    directory = resolve_data_dir(json_body().get("path"))
    watcher.watch(directory)
    return jsonify({"path": str(directory), "latest_seq": watcher.events_since(0)["latest_seq"]})


@app.get("/watch/events")
def watch_events():
    return jsonify(watcher.events_since(_int_arg("since", 0)))


def main() -> None:
    settings = get_settings()
    setup_logging(SERVICE_NAME)
    logger.info("文件服务启动：http://%s:%s，数据目录：%s", settings.bind_host, settings.file_service_port,
                ", ".join(str(p) for p in settings.data_roots))
    try:
        app.run(host=settings.bind_host, port=settings.file_service_port, threaded=True)
    finally:
        watcher.stop()


if __name__ == "__main__":
    main()
