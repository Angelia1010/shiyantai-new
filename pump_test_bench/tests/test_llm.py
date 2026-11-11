import asyncio

import numpy as np
import pytest

from pump_test_bench.app.llm import analyzer
from pump_test_bench.app.llm.ollama_client import strip_thinking
from pump_test_bench.app.llm.session_store import MemorySessionStore


class FakeLLM:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, **_):
        self.prompts.append(prompt)
        return f"回答{len(self.prompts)}"


def run(coro):
    return asyncio.run(coro)


def test_strip_thinking():
    assert strip_thinking("<think>推理</think>\n结论") == "结论"
    assert strip_thinking("推理</think>结论") == "结论"
    assert strip_thinking("结论") == "结论"


def test_plan_windows_caps_window_count():
    assert analyzer.plan_windows(100, 200, 50, 10) == [0]
    starts = analyzer.plan_windows(1_000_000, 10_000, 5_000, 50)
    assert len(starts) <= 50 and starts[0] == 0
    with pytest.raises(ValueError):
        analyzer.plan_windows(10, 0, 1, 5)


def test_analyze_and_chat_share_session():
    data = np.random.default_rng(0).normal(size=(300, 3))
    llm, session = FakeLLM(), {}

    async def collect():
        return [e async for e in analyzer.analyze(llm, data, ["a", "b", "c"], "f.tdms", 100, 100, 50, session)]

    events = run(collect())
    assert [e["event"] for e in events] == ["start", "window", "window", "window", "summary"]
    assert session["summary"] == "回答4" and len(session["windows"]) == 3
    # 第 2 个窗口的提示词带上了第 1 个窗口的结论
    assert "回答1" in llm.prompts[1]

    reply = run(analyzer.answer(llm, "有什么异常？", session))
    assert reply == "回答5"
    assert "回答4" in llm.prompts[-1]  # 问答带上了分析总结
    assert session["history"][-1] == {"role": "assistant", "content": "回答5"}


def test_memory_store_evicts_oldest():
    store = MemorySessionStore(max_sessions=2)
    for key in ("a", "b", "c"):
        store.save(key, {"k": key})
    assert store.get("a") is None and store.get("c") == {"k": "c"}
