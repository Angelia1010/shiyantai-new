"""大模型会话存储。

会话内容为 JSON 可序列化的字典：{"file_name", "windows": [...], "summary", "history": [...]}。
配置了 REDIS_URL 时存到 Redis（JSON 格式，24 小时过期），否则保存在进程内存中
（最多保留 MAX_SESSIONS 个最近使用的会话）。
"""
import json
import threading
from collections import OrderedDict
from typing import Dict, Optional

from shared.config import get_settings

MAX_SESSIONS = 50
REDIS_TTL_SECONDS = 24 * 3600


class MemorySessionStore:
    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self._data: "OrderedDict[str, str]" = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_sessions

    def get(self, session_id: str) -> Optional[Dict]:
        with self._lock:
            raw = self._data.get(session_id)
            if raw is None:
                return None
            self._data.move_to_end(session_id)
            return json.loads(raw)

    def save(self, session_id: str, session: Dict) -> None:
        with self._lock:
            self._data[session_id] = json.dumps(session, ensure_ascii=False)
            self._data.move_to_end(session_id)
            while len(self._data) > self._max:
                self._data.popitem(last=False)


class RedisSessionStore:
    def __init__(self, url: str):
        import redis  # 只有配置了 REDIS_URL 才需要安装

        self._redis = redis.Redis.from_url(url, socket_timeout=5)
        self._redis.ping()

    def get(self, session_id: str) -> Optional[Dict]:
        raw = self._redis.get(f"llm_session:{session_id}")
        return json.loads(raw) if raw else None

    def save(self, session_id: str, session: Dict) -> None:
        self._redis.set(f"llm_session:{session_id}", json.dumps(session, ensure_ascii=False), ex=REDIS_TTL_SECONDS)


def create_session_store():
    url = get_settings().redis_url
    return RedisSessionStore(url) if url else MemorySessionStore()
