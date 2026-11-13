"""内置公式：公式写在后端模型配置文件（config/simulation/*.json）中，用于内置模型（如涡轮流量计的回归公式）。
页面上不显示、也不能选择这种方式（user_selectable = False）；系数可以固定，也可以由正常数据拟合。

输出配置：
    "method": "formula",
    "formula": {
        "expression": "a + b * 质量流量 + c * 密度",
        "coefficients": {"a": {"value": 934.79, "fit": false}, "b": {"value": 13217.85, "fit": false}, ...}
    }
"""
from typing import Dict, List

from pump_test_bench.app.simulation.builders.base import FitData, FitResult, OptionSpec, SurrogateBuilder
from pump_test_bench.app.simulation.formula import Expression, FormulaError, fit_coefficients, is_valid_name, safe_float


def coefficient_table(output: Dict) -> Dict[str, Dict]:
    raw = (output.get("formula") or {}).get("coefficients") or {}
    out = {}
    for name, c in raw.items():
        c = c if isinstance(c, dict) else {"value": c}
        out[name] = {"value": safe_float(c.get("value")) if c.get("value") not in (None, "") else None,
                     "fit": bool(c.get("fit"))}
    return out


class FormulaBuilder(SurrogateBuilder):
    kind = "formula"
    label = "内置公式"
    description = "公式写在后端模型配置文件中（如厂家公式、回归结果）；系数可以固定，也可以由正常数据拟合"
    user_selectable = False
    options = [
        OptionSpec("expression", "公式", "formula", "", help="变量用变量页中的名字，其余名字为系数"),
        OptionSpec("coefficients", "系数", "coefficients", {}),
    ]

    def validate(self, output: Dict, inputs: List[Dict]) -> None:
        f = output.get("formula") or {}
        try:
            expr = Expression(f.get("expression", ""))
        except FormulaError as exc:
            raise ValueError(f"输出“{output['name']}”的公式：{exc}") from None
        variables = [i["name"] for i in inputs]
        table = coefficient_table(output)
        names = expr.coefficient_names(variables)
        for n in names:
            if not is_valid_name(n):
                raise ValueError(f"输出“{output['name']}”的公式中名字“{n}”不合法")
            c = table.get(n)
            if c is None or (c["value"] is None and not c["fit"]):
                raise ValueError(f"输出“{output['name']}”的公式中“{n}”不是变量，请在系数表中给出它的值或勾选“由数据拟合”")
        # 只保留公式里用到的系数
        output["formula"] = {"expression": expr.text,
                             "coefficients": {n: {"value": table[n]["value"] if table[n]["value"] is not None else 1.0,
                                                  "fit": table[n]["fit"]} for n in names}}

    def fit(self, data: FitData) -> FitResult:
        f = data.output.get("formula") or {}
        expr = Expression(f.get("expression", ""))
        table = coefficient_table(data.output)
        coefs = {n: (c["value"] if c["value"] is not None else 1.0) for n, c in table.items()}
        expr.check(list(data.variables), coefs)
        free = [n for n, c in table.items() if c["fit"] and n in expr.names]
        fitted, info = fit_coefficients(expr, data.variables, data.y, coefs, free)
        info.update({"fitted": free, "fixed": [n for n in coefs if n not in free]})
        if free and not info["converged"]:
            info["note"] = "系数拟合未完全收敛，结果可用但建议检查初值或公式形式"
        return FitResult(expr.text, {n: fitted[n] for n in expr.names if n in fitted}, info)
