"""Flask 服务的公共工厂：统一鉴权、统一错误格式。

错误响应统一为 ``{"error": "<中文说明>"}``：
- ``ValueError``（包括路径校验失败）视为请求参数问题，返回 400 和具体原因；
- ``ApiError`` 返回其自带的状态码；
- 其它异常记录完整堆栈，只向前端返回通用提示，不泄露服务器内部信息。
"""
import logging
from typing import Iterable

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from shared.auth import TOKEN_HEADER, verify_token


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def create_app(name: str, public_paths: Iterable[str] = ("/health",)) -> Flask:
    app = Flask(name)
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.json.sort_keys = False  # type: ignore[attr-defined]
    logger = logging.getLogger(name)
    public = set(public_paths)

    @app.before_request
    def _authenticate():
        if request.method == "OPTIONS" or request.path in public:
            return None
        user = verify_token(request.headers.get(TOKEN_HEADER))
        if not user:
            return jsonify({"error": "未登录或登录已过期"}), 401
        g.user = user
        return None

    @app.get("/health")
    def _health():
        return jsonify({"status": "ok", "service": name})

    @app.errorhandler(ApiError)
    def _api_error(err: ApiError):
        return jsonify({"error": err.message}), err.status

    @app.errorhandler(ValueError)
    def _value_error(err: ValueError):
        return jsonify({"error": str(err)}), 400

    @app.errorhandler(HTTPException)
    def _http_error(err: HTTPException):
        return jsonify({"error": err.description}), err.code

    @app.errorhandler(Exception)
    def _unexpected(err: Exception):
        logger.exception("未处理的异常: %s %s", request.method, request.path)
        return jsonify({"error": "服务器内部错误，请查看服务日志"}), 500

    return app


def json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("请求体必须是 JSON 对象")
    return data
