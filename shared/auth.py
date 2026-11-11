"""登录与令牌校验。

令牌由 ``SECRET_KEY`` 签名（itsdangerous，Flask 自带依赖），所有服务共用同一个密钥，
因此任何一个服务签发的令牌在其它服务都能校验。前端通过请求头 ``X-Token`` 传递。
"""
import hmac
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from shared.config import get_settings

TOKEN_HEADER = "X-Token"
_SALT = "shiyantai-auth"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt=_SALT)


def check_credentials(username: str, password: str) -> bool:
    settings = get_settings()
    user_ok = hmac.compare_digest((username or "").encode(), settings.admin_username.encode())
    pass_ok = hmac.compare_digest((password or "").encode(), settings.admin_password.encode())
    return user_ok and pass_ok


def issue_token(username: str) -> str:
    return _serializer().dumps({"u": username})


def verify_token(token: Optional[str]) -> Optional[str]:
    """校验令牌，成功返回用户名，失败返回 None。"""
    if not token:
        return None
    max_age = get_settings().token_ttl_hours * 3600
    try:
        data = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("u") if isinstance(data, dict) else None
