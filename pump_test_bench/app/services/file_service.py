"""文件服务（默认端口 5002，前端代理前缀 /api/file）。

负责列出数据目录中的文件、分页读取试验数据，以及实时监控试验台正在写入的数据文件。

接口一览：
    GET  /files?path=&recursive=1             列出目录（及子目录）下的数据文件，返回相对路径
    GET  /files/page?path=&file_name=&page=&page_size=   分页读取文件内容（file_name 可带子目录）
    GET  /watch                               当前监控目录及状态
    POST /watch {path}                        切换监控目录（会保存，服务重启后自动恢复）
    GET  /watch/events?since=<seq>            序号 since 之后的“文件写完”事件（自动诊断用）
    GET  /live/status                         实时监控状态：目录、当前文件、是否有数据在写入
    GET  /live/frames?since=<seq>&limit=      序号 since 之后的实时特征帧（工作台用）

监控逻辑见 pump_test_bench.app.core.live_monitor。

启动：在仓库根目录执行 ``python -m pump_test_bench.app.services.file_service``
"""
import logging
import os

from flask import jsonify, request

from pump_test_bench.app.core.data_reader import TABLE_SUFFIXES, TDMS_SUFFIXES, read_page
from pump_test_bench.app.core.live_monitor import LiveMonitor
from shared.config import get_settings
from shared.flask_app import create_app, json_body
from shared.logging_setup import setup_logging
from shared.paths import resolve_data_dir, resolve_data_file

SERVICE_NAME = "file_service"
logger = logging.getLogger(SERVICE_NAME)
LISTED_SUFFIXES = TABLE_SUFFIXES + TDMS_SUFFIXES
MAX_LISTED_FILES = 5000

app = create_app(SERVICE_NAME)
_monitor = None


def get_monitor() -> LiveMonitor:
    """按配置创建监控器（首次调用时创建，便于测试替换配置）。"""
    global _monitor
    if _monitor is None:
        settings = get_settings()
        _monitor = LiveMonitor(
            scan_interval=settings.live_scan_seconds,
            settle_seconds=settings.live_settle_seconds,
            state_file=settings.db_path.parent / "live_monitor.json",
        )
    return _monitor


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
    recursive = request.args.get("recursive", "") in ("1", "true")
    files = []
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".")) if recursive else []
        for name in filenames:
            if name.lower().endswith(LISTED_SUFFIXES) and not name.startswith((".", "~$")):
                files.append(os.path.relpath(os.path.join(dirpath, name), directory).replace(os.sep, "/"))
        if len(files) >= MAX_LISTED_FILES:
            break
    return jsonify({"path": str(directory), "files": sorted(files)[:MAX_LISTED_FILES]})


@app.get("/files/page")
def file_page():
    path = resolve_data_file(request.args.get("path"), request.args.get("file_name"), TABLE_SUFFIXES)
    return jsonify(read_page(path, _int_arg("page", 0), _int_arg("page_size", 500)))


@app.get("/watch")
def get_watch():
    return jsonify(get_monitor().status())


@app.post("/watch")
def set_watch():
    directory = resolve_data_dir(json_body().get("path"))
    monitor = get_monitor()
    monitor.watch(directory)
    return jsonify({**monitor.status(), "latest_event_seq": monitor.events_since(0)["latest_seq"]})


@app.get("/watch/events")
def watch_events():
    return jsonify(get_monitor().events_since(_int_arg("since", 0)))


@app.get("/live/status")
def live_status():
    return jsonify(get_monitor().status())


@app.get("/live/frames")
def live_frames():
    limit = min(max(_int_arg("limit", 300), 1), 3600)
    return jsonify(get_monitor().frames_since(_int_arg("since", 0), limit))


def main() -> None:
    settings = get_settings()
    setup_logging(SERVICE_NAME)
    logger.info("文件服务启动：http://%s:%s，数据目录：%s", settings.bind_host, settings.file_service_port,
                ", ".join(str(p) for p in settings.data_roots))
    monitor = get_monitor()
    monitor.restore(resolve_data_dir)
    try:
        app.run(host=settings.bind_host, port=settings.file_service_port, threaded=True)
    finally:
        monitor.stop()


if __name__ == "__main__":
    main()
