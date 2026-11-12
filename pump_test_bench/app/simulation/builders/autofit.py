"""自动拟合：按变量角色确定公式结构，用正常数据最小二乘拟合，结果写成多项式公式。

为什么按角色定结构，而不是让算法在数据里挑项：
正常数据通常只有几个油温段（2026-11 数据为 4 段 × 15 个文件）。让算法自由挑项（逐步回归等）时，
它分不清“真规律”和“这批数据的巧合”，换一个油温就不准（嵌套交叉验证中压力误差反而变大）；
高斯过程等黑箱方法在数据少时外推更差，且给不出公式。按角色定结构不依赖数据挑选，结果稳定，
2026-11 数据上留一油温段交叉验证的平均误差由二次响应面的 1.49% 降到 0.91%。

角色（变量配置 role，可在页面上改；auto 时按数据建议）：
- main 主变量（决定工况，如电传转速）：一次到 max_degree 次（默认 3，泵的流量-转速关系是弯的）；
- secondary 次变量（如电机转速）：一次、二次；
- environment 环境变量（如油温、密度）：只用一次项。油温段很少，平方项到没见过的油温会外推出错；
- off 不使用（在数据中几乎不变的变量自动设为 off，否则无法拟合出它的影响）。
另外加所有使用中的变量两两相乘的交叉项。数据不够时依次降低主变量次数、次变量次数、去掉交叉项。
"""
import itertools
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from pump_test_bench.app.simulation.builders.base import FitData, FitResult, OptionSpec, SurrogateBuilder
from pump_test_bench.app.simulation.formula import expand_standardized, polynomial_expression

ROLES = {"auto": "自动", "main": "主变量", "secondary": "次变量", "environment": "环境变量", "off": "不使用"}
ROLE_DEGREE = {"main": 3, "secondary": 2, "environment": 1}
_ENV_HINTS = ("温", "密度", "黏度", "粘度", "density", "viscosity", "temp")


def _near_constant(x: np.ndarray) -> bool:
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return True
    scale = max(abs(float(np.mean(x))), float(np.std(x)), 1e-12)
    return float(np.ptp(x)) / scale < 0.01


def suggest_roles(inputs: Sequence[Dict], variables: Dict[str, np.ndarray],
                  ys: Sequence[np.ndarray]) -> Dict[str, str]:
    """按数据建议各变量的角色（只改 role 为 auto 或未设置的变量）。"""
    roles: Dict[str, str] = {}
    candidates = []
    for spec in inputs:
        name, role = spec["name"], spec.get("role") or "auto"
        x = variables.get(name)
        if role != "auto":
            roles[name] = role
        elif x is None or _near_constant(x):
            roles[name] = "off"
        elif spec.get("derived") in ("density", "viscosity") or any(h in name for h in _ENV_HINTS):
            roles[name] = "environment"
        else:
            candidates.append(name)
    if candidates:
        def influence(name: str) -> float:
            x = variables[name]
            vals = []
            for y in ys:
                ok = np.isfinite(y) & np.isfinite(x)
                if ok.sum() > 3 and np.std(y[ok]) > 0 and np.std(x[ok]) > 0:
                    vals.append(abs(np.corrcoef(x[ok], y[ok])[0, 1]))
            return float(np.mean(vals)) if vals else 0.0
        has_main = any(r == "main" for r in roles.values())
        ranked = sorted(candidates, key=influence, reverse=True)
        for k, name in enumerate(ranked):
            roles[name] = "main" if (k == 0 and not has_main) else "secondary"
    return roles


def structure(roles: Dict[str, str], degrees: Dict[str, int], interactions: bool = True) -> List[Tuple[int, ...]]:
    """项的次数组合（不含常数项），按 roles 中变量的顺序；degrees：{角色: 最高次数}。"""
    names = list(roles)
    used = [i for i, n in enumerate(names) if roles[n] != "off"]
    terms: List[Tuple[int, ...]] = []
    for i in used:
        for p in range(1, degrees.get(roles[names[i]], 1) + 1):
            e = [0] * len(names)
            e[i] = p
            terms.append(tuple(e))
    if interactions:
        for i, j in itertools.combinations(used, 2):
            e = [0] * len(names)
            e[i] = e[j] = 1
            terms.append(tuple(e))
    return terms


class AutoFitBuilder(SurrogateBuilder):
    kind = "autofit"
    label = "自动拟合"
    description = "按变量角色确定公式结构（主变量最高三次、次变量二次、环境变量一次，加交叉项），用正常数据拟合；结果可转为自定义公式"
    options = [
        OptionSpec("max_degree", "主变量最高次数", "number", 3, min=1, max=4, help="泵的流量-转速关系一般需要 3 次"),
        OptionSpec("interactions", "交叉项", "select", True,
                   choices=[{"value": True, "label": "使用"}, {"value": False, "label": "不使用"}]),
        OptionSpec("ridge", "正则强度", "number", 1e-4, min=0, max=1,
                   help="项之间相关时防止系数乱跳；一般不用改"),
    ]

    @staticmethod
    def _opts(output: Dict) -> Dict:
        o = output.get("autofit") or {}
        return {"max_degree": int(o.get("max_degree") or 3), "interactions": o.get("interactions", True) not in (False, "false"),
                "ridge": float(o.get("ridge") if o.get("ridge") not in (None, "") else 1e-4)}

    def validate(self, output: Dict, inputs: List[Dict]) -> None:
        o = self._opts(output)
        if not 1 <= o["max_degree"] <= 4:
            raise ValueError(f"输出“{output['name']}”：主变量最高次数应为 1–4")
        if o["ridge"] < 0:
            raise ValueError(f"输出“{output['name']}”：正则强度不能为负")
        output["autofit"] = o

    def fit(self, data: FitData, roles: Optional[Dict[str, str]] = None) -> FitResult:
        opts = self._opts(data.output)
        names = [i["name"] for i in data.inputs]
        roles = roles or suggest_roles(data.inputs, data.variables, [data.y])
        roles = {n: roles.get(n, "off") for n in names}
        for n in names:  # 在这批数据里不变的变量无法拟合出影响
            if roles[n] != "off" and _near_constant(data.variables[n]):
                roles[n] = "off"
        y = np.asarray(data.y, dtype=float)
        if np.std(y) <= 1e-12 * max(1.0, abs(float(np.mean(y)))) or all(r == "off" for r in roles.values()):
            return FitResult("k0", {"k0": float(np.mean(y))},
                             {"roles": roles, "terms": 0, "note": "输出在正常数据中不变，或没有可用的变量：按固定值比较"})
        X = np.column_stack([data.variables[n] for n in names]).astype(float)
        centers = X.mean(axis=0)
        scales = np.where(X.std(axis=0) > 0, X.std(axis=0), 1.0)
        Z = (X - centers) / scales

        degrees = {**ROLE_DEGREE, "main": opts["max_degree"]}
        inter = opts["interactions"]
        while True:
            terms = structure(roles, degrees, inter)
            if len(terms) + 4 <= len(y):
                break
            if degrees["main"] > 2:
                degrees["main"] -= 1
            elif degrees["secondary"] > 1:
                degrees["secondary"] = 1
            elif inter:
                inter = False
            elif degrees["main"] > 1:
                degrees["main"] = 1
            else:
                break
        notes = []
        if degrees != {**ROLE_DEGREE, "main": opts["max_degree"]} or inter != opts["interactions"]:
            notes.append(f"数据较少（{len(y)} 个工况），已简化结构：主变量 {degrees['main']} 次、次变量 {degrees['secondary']} 次"
                         + ("" if inter else "、无交叉项"))
        degree = degrees["main"]

        F = np.column_stack([np.ones(len(y))] + [np.prod(Z ** np.array(e), axis=1) for e in terms])
        lam = opts["ridge"] * len(y)
        P = np.eye(F.shape[1])
        P[0, 0] = 0.0  # 常数项不加正则
        coef = np.linalg.solve(F.T @ F + lam * P, F.T @ y)
        poly = {tuple([0] * len(names)): float(coef[0])}
        poly.update({e: float(c) for e, c in zip(terms, coef[1:])})
        raw = expand_standardized(poly, centers, scales)
        expr, coefs = polynomial_expression(raw, names)
        info = {"roles": roles, "terms": len(terms) + 1, "degree": degree}
        if notes:
            info["note"] = "；".join(notes)
        return FitResult(expr, coefs, info)
