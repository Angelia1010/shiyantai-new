"""基于大模型的数据分析与问答。

分析流程：把多通道数据按滑动窗口切分，每个窗口计算统计量后交给大模型解读，
最后让大模型基于各窗口结论给出总体评估。窗口数超过 LLM_MAX_WINDOWS 时自动加大步长。
问答时会把该会话的分析结论和最近几轮对话作为上下文。
"""
import math
import warnings
from typing import AsyncIterator, Dict, List, Sequence

import numpy as np

HISTORY_TURNS = 6           # 问答时带上的最近对话轮数
CONTEXT_WINDOWS = 2         # 分析单个窗口时参考的前序窗口数
TOP_CHANNELS = 8            # 提示词中列出的通道数


def plan_windows(n_samples: int, window_size: int, stride: int, max_windows: int) -> List[int]:
    """返回各窗口的起始下标。"""
    if window_size <= 0 or stride <= 0:
        raise ValueError("window_size 和 stride 必须大于 0")
    if n_samples <= window_size:
        return [0]
    count = (n_samples - window_size) // stride + 1
    if count > max_windows > 1:
        stride = math.ceil((n_samples - window_size) / (max_windows - 1))
    return list(range(0, n_samples - window_size + 1, stride))


def window_stats(data: np.ndarray, names: Sequence[str]) -> List[Dict]:
    with warnings.catch_warnings():  # 整列为空时 numpy 会警告，这些通道下面会被过滤掉
        warnings.simplefilter("ignore", RuntimeWarning)
        mean, std = np.nanmean(data, axis=0), np.nanstd(data, axis=0)
        low, high = np.nanmin(data, axis=0), np.nanmax(data, axis=0)
    stats = [
        {"channel": n, "mean": float(m), "std": float(s), "min": float(lo), "max": float(hi)}
        for n, m, s, lo, hi in zip(names, mean, std, low, high)
        if not math.isnan(m)
    ]
    # 按波动程度排序，最值得关注的通道排在前面
    stats.sort(key=lambda s: s["std"] / (abs(s["mean"]) + 1e-9), reverse=True)
    return stats


def _format_stats(stats: List[Dict]) -> str:
    return "\n".join(
        f"- {s['channel']}: 均值 {s['mean']:.4g}，标准差 {s['std']:.4g}，范围 [{s['min']:.4g}, {s['max']:.4g}]"
        for s in stats[:TOP_CHANNELS]
    )


def window_prompt(index: int, start: int, end: int, stats: List[Dict], previous: List[Dict]) -> str:
    prompt = (
        f"你是燃油泵标准试验台的故障诊断专家。下面是试验数据第 {index} 个窗口（样本 {start}–{end}）"
        f"中波动最大的通道统计：\n{_format_stats(stats)}\n"
    )
    if previous:
        prompt += "\n前面窗口的结论：\n" + "\n".join(
            f"- 窗口 {w['index']}：{w['analysis'][:150]}" for w in previous
        ) + "\n"
    prompt += "\n请用中文简要回答：1. 是否有异常通道及依据；2. 本窗口系统状态；3. 与前面窗口相比的变化趋势。"
    return prompt


def summary_prompt(file_name: str, windows: List[Dict]) -> str:
    lines = "\n".join(f"- 窗口 {w['index']}（样本 {w['start']}–{w['end']}）：{w['analysis'][:200]}" for w in windows)
    return (
        f"你是燃油泵标准试验台的首席分析师。文件 {file_name} 共分析了 {len(windows)} 个窗口，各窗口结论如下：\n"
        f"{lines}\n\n请用中文分条给出：1. 系统整体健康评估（优/良/中/差）；2. 最需要关注的问题；3. 按优先级排序的维护建议。"
    )


def chat_prompt(question: str, session: Dict) -> str:
    parts = ["你是燃油泵标准试验台的故障诊断专家，擅长运维排障、数据分析和故障诊断。请用中文简洁回答。"]
    if session.get("summary"):
        parts.append(f"\n已完成的数据分析（文件 {session.get('file_name', '')}）结论：\n{session['summary'][:1500]}")
    history = session.get("history", [])[-HISTORY_TURNS * 2:]
    if history:
        parts.append("\n最近的对话：\n" + "\n".join(
            f"{'用户' if h['role'] == 'user' else '助手'}：{h['content'][:500]}" for h in history))
    parts.append(f"\n用户问题：{question}")
    return "\n".join(parts)


async def analyze(llm, data: np.ndarray, names: Sequence[str], file_name: str,
                  window_size: int, stride: int, max_windows: int, session: Dict) -> AsyncIterator[Dict]:
    """逐个产出事件：start / window / summary。分析结论写回 session。"""
    starts = plan_windows(len(data), window_size, stride, max_windows)
    yield {"event": "start", "windows": len(starts), "samples": int(len(data)), "channels": len(names)}

    windows: List[Dict] = []
    for i, start in enumerate(starts, 1):
        end = min(start + window_size, len(data))
        stats = window_stats(data[start:end], names)
        analysis = await llm.generate(window_prompt(i, start, end, stats, windows[-CONTEXT_WINDOWS:]))
        window = {"index": i, "start": start, "end": end, "analysis": analysis}
        windows.append(window)
        yield {"event": "window", **window, "total": len(starts)}

    summary = await llm.generate(summary_prompt(file_name, windows))
    session.update({"file_name": file_name, "windows": windows, "summary": summary})
    yield {"event": "summary", "text": summary}


async def answer(llm, question: str, session: Dict) -> str:
    reply = await llm.generate(chat_prompt(question, session))
    history = session.setdefault("history", [])
    history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": reply}])
    del history[:-HISTORY_TURNS * 2]
    return reply
