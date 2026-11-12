"""诊断插件：在现有诊断流程上扩展新的分析方法，而不改动诊断引擎。

两种插件：
- Analyzer（分析器）：在得出结论之前运行，返回“发现”（与内置检查同一格式，见 checks.finding），
  这些发现和内置检查的发现一起参与结论与原因推断。适合新增一类检查（如振动频谱、基于规则库的检查）。
- Reasoner（推理器）：在结论得出之后运行，读取完整报告与数据，给出独立的分析意见（report["reviews"]），
  不改变规则引擎的结论。适合大模型智能体：它可以阅读报告、调用 ctx 提供的数据与仿真模型，写出综合分析、
  追问方向和处理建议；与规则结论并列展示，由人判断。

加载方式（不改代码）：在 pump_test_bench/config/plugins.json 中列出模块，或设置环境变量 DIAGNOSIS_PLUGINS
（逗号分隔的模块名）。模块被导入时调用 register_analyzer / register_reasoner 注册自己。
插件出错不影响诊断：错误会被记录，并在报告中注明该插件未能完成。详见 docs/扩展指南.md。
"""
import importlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)
PLUGINS_CONFIG = Path(__file__).resolve().parents[2] / "config" / "plugins.json"


@dataclass
class DiagnosisContext:
    """插件能看到的一次诊断的全部信息（只读使用）。"""
    df: pd.DataFrame                      # 整个数据文件
    segment: pd.DataFrame                 # 稳定段
    cfg: Dict                             # 诊断配置（config/bench.json）
    analysis: Dict                        # 内置检查的结果（loops、findings、models、condition…）
    baseline: Optional[Dict] = None       # 健康基准
    density: Optional[float] = None       # 燃油 20 ℃ 密度
    sims: List = field(default_factory=list)       # [(模型配置, 模型产物)]
    profile: Dict = field(default_factory=dict)    # 诊断方案
    options: Dict = field(default_factory=dict)    # 该插件在 plugins.json 中的选项

    def segment_means(self) -> Dict[str, float]:
        """稳定段各数值列的均值。"""
        means = self.segment.apply(pd.to_numeric, errors="coerce").mean(numeric_only=True)
        return {k: float(v) for k, v in means.items() if pd.notna(v)}

    def model_expected(self, model_id: str, condition: Dict[str, float]) -> Dict[str, float]:
        """用某个仿真模型算任意工况下的预期值（智能体做“如果……会怎样”的推演时使用）。"""
        from pump_test_bench.app.simulation.table import predict
        for mcfg, table in self.sims:
            if mcfg["id"] == model_id:
                return predict(table, condition)[0]
        raise KeyError(f"没有可用的仿真模型：{model_id}")


class Analyzer:
    """分析器基类：实现 analyze()，返回发现列表（checks.finding(...)）。"""
    name = ""
    label = ""

    def analyze(self, ctx: DiagnosisContext) -> List[Dict]:
        raise NotImplementedError


class Reasoner:
    """推理器基类：实现 review()，返回一条分析意见：
    {"title": 标题, "summary": 一句话结论, "details": 正文（可多段）, "confidence": 0–1 或 None,
     "suggestions": [建议...], "references": [依据...]}；不适用时返回 None。"""
    name = ""
    label = ""
    timeout_s = 120.0   # 超时后不再等待（报告中注明）

    def review(self, report: Dict, ctx: DiagnosisContext) -> Optional[Dict]:
        raise NotImplementedError


_analyzers: Dict[str, Analyzer] = {}
_reasoners: Dict[str, Reasoner] = {}
_loaded = False
_load_lock = threading.Lock()


def register_analyzer(plugin: Analyzer) -> None:
    if not plugin.name:
        raise ValueError("分析器缺少 name")
    _analyzers[plugin.name] = plugin


def register_reasoner(plugin: Reasoner) -> None:
    if not plugin.name:
        raise ValueError("推理器缺少 name")
    _reasoners[plugin.name] = plugin


def unregister(name: str) -> None:
    _analyzers.pop(name, None)
    _reasoners.pop(name, None)


def plugin_config() -> Dict:
    if not PLUGINS_CONFIG.exists():
        return {}
    try:
        return json.loads(PLUGINS_CONFIG.read_text(encoding="utf-8"))
    except ValueError:
        logger.warning("插件配置格式错误：%s", PLUGINS_CONFIG)
        return {}


def load_plugins() -> None:
    """导入 plugins.json 与环境变量 DIAGNOSIS_PLUGINS 中列出的模块（只导入一次）。"""
    global _loaded
    with _load_lock:
        if _loaded:
            return
        modules = list(plugin_config().get("modules") or [])
        modules += [m.strip() for m in os.environ.get("DIAGNOSIS_PLUGINS", "").split(",") if m.strip()]
        for mod in dict.fromkeys(modules):
            try:
                importlib.import_module(mod)
                logger.info("已加载诊断插件模块：%s", mod)
            except Exception:
                logger.exception("加载诊断插件模块失败：%s", mod)
        _loaded = True


def _enabled(name: str) -> bool:
    return name not in set(plugin_config().get("disabled") or [])


def _options(name: str) -> Dict:
    return (plugin_config().get("options") or {}).get(name, {})


def list_plugins() -> List[Dict]:
    load_plugins()
    return ([{"name": p.name, "label": p.label, "type": "analyzer", "enabled": _enabled(p.name)} for p in _analyzers.values()]
            + [{"name": p.name, "label": p.label, "type": "reasoner", "enabled": _enabled(p.name)} for p in _reasoners.values()])


def run_analyzers(ctx: DiagnosisContext) -> List[Dict]:
    from pump_test_bench.app.diagnosis.checks import NOTICE, finding
    load_plugins()
    out: List[Dict] = []
    for p in list(_analyzers.values()):
        if not _enabled(p.name):
            continue
        ctx.options = _options(p.name)
        try:
            found = p.analyze(ctx) or []
            for f in found:
                f.setdefault("plugin", p.name)
            out += found
        except Exception as exc:
            logger.exception("诊断插件 %s 出错", p.name)
            out.append(finding("plugin", NOTICE, "扩展分析未完成", f"{p.label or p.name} 出错：{exc}", p.name,
                               p.label or p.name))
    return out


def run_reasoners(report: Dict, ctx: DiagnosisContext) -> List[Dict]:
    """依次运行推理器；每个都在独立线程中带超时运行，出错或超时只记录在结果中。"""
    load_plugins()
    reviews: List[Dict] = []
    for p in list(_reasoners.values()):
        if not _enabled(p.name):
            continue
        ctx.options = _options(p.name)
        box: Dict = {}

        def work(plugin=p):
            try:
                box["result"] = plugin.review(report, ctx)
            except Exception as exc:  # 返回给报告
                logger.exception("诊断推理插件 %s 出错", plugin.name)
                box["error"] = str(exc)

        started = time.time()
        t = threading.Thread(target=work, name=f"reasoner-{p.name}", daemon=True)
        t.start()
        t.join(float(ctx.options.get("timeout_s", p.timeout_s)))
        item = {"name": p.name, "label": p.label or p.name, "elapsed_s": round(time.time() - started, 2)}
        if t.is_alive():
            item.update(status="timeout", error=f"超过 {ctx.options.get('timeout_s', p.timeout_s)} 秒未完成")
        elif "error" in box:
            item.update(status="error", error=box["error"])
        elif box.get("result"):
            item.update(status="done", **box["result"])
        else:
            continue
        reviews.append(item)
    return reviews
