"""数据代理模型构建器注册表。

新增一种构建方法（例如基于大模型分析数据、提出公式的构建器）：
1. 新建模块，继承 base.SurrogateBuilder，设置 kind/label/description/options，实现 fit(data) → FitResult；
2. 调用 register() 注册：写在插件模块里，并把模块列入 config/plugins.json 的 modules（不改本仓库代码）；
3. 前端会自动在“计算方式”里列出它，并按 options 生成设置项；交叉验证、误差、异常样本、标定、诊断都无需改动。
详见 docs/扩展指南.md。
"""
from typing import Dict, List

from pump_test_bench.app.simulation.builders.autofit import ROLES, AutoFitBuilder, suggest_roles
from pump_test_bench.app.simulation.builders.base import FitData, FitResult, OptionSpec, SurrogateBuilder
from pump_test_bench.app.simulation.builders.formula_builder import FormulaBuilder

_BUILDERS: Dict[str, SurrogateBuilder] = {}
DEFAULT_METHOD = "autofit"


def register(builder: SurrogateBuilder) -> None:
    if not builder.kind:
        raise ValueError("构建器缺少 kind")
    _BUILDERS[builder.kind] = builder


def _load_plugins() -> None:
    """插件模块（config/plugins.json 的 modules）中也可以注册构建器。"""
    from pump_test_bench.app.diagnosis.plugins import load_plugins
    load_plugins()


def get_builder(kind: str) -> SurrogateBuilder:
    _load_plugins()
    try:
        return _BUILDERS[kind]
    except KeyError:
        raise ValueError(f"未知的计算方式：{kind}（可用：{'、'.join(_BUILDERS)}）") from None


def list_builders() -> List[Dict]:
    _load_plugins()
    return [b.describe() for b in _BUILDERS.values()]


register(AutoFitBuilder())
register(FormulaBuilder())

__all__ = ["DEFAULT_METHOD", "ROLES", "FitData", "FitResult", "OptionSpec", "SurrogateBuilder",
           "get_builder", "list_builders", "register", "suggest_roles"]
