"""Ollama 客户端：一次请求返回完整回答（非流式），在线程池里执行，不阻塞事件循环。"""
import asyncio
import re

import requests

from shared.config import get_settings

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)


class LLMError(RuntimeError):
    pass


def strip_thinking(text: str) -> str:
    """去掉 DeepSeek-R1 类模型输出里的 <think>…</think> 推理过程。"""
    text = _THINK_BLOCK.sub("", text)
    if "</think>" in text:  # 只有结束标签的情况
        text = text.split("</think>", 1)[1]
    return text.strip()


class OllamaClient:
    def __init__(self, base_url: str = None, model: str = None, timeout: int = None):
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout or settings.ollama_timeout

    def _generate_sync(self, prompt: str, max_tokens: int, temperature: float) -> str:
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": temperature},
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMError(f"无法连接大模型服务 {self.base_url}：{exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"大模型服务返回错误 {resp.status_code}：{resp.text[:200]}")
        return strip_thinking(resp.json().get("response", ""))

    async def generate(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.3) -> str:
        return await asyncio.to_thread(self._generate_sync, prompt, max_tokens, temperature)
