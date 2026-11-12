"""运行 Flask 服务：装有 waitress（安装包部署）时用它（多线程、适合长期运行），否则用 Flask 自带服务器（开发）。"""
import logging

logger = logging.getLogger(__name__)


def serve_app(app, host: str, port: int) -> None:
    try:
        from waitress import serve
    except ImportError:
        app.run(host=host, port=port, threaded=True)
        return
    logger.info("使用 waitress 运行：http://%s:%s", host, port)
    serve(app, host=host, port=port, threads=16, channel_timeout=900, max_request_body_size=200 * 1024 * 1024)
