"""数据代理模型的通用流程：整理数据 → 各输出用构建器拟合 → 留一组交叉验证 → 误差评估、异常样本、建议。

与构建器（builders/）解耦：构建器只负责“给数据、出公式”，这里负责让任何构建器的结果都能被同样地检验和使用。
结果（“模型产物”）是 kind = "formula" 的表：每个输出一条公式和系数，诊断时直接计算（见 table.predict）。
"""
from datetime import datetime
from typing import Callable, Dict, List, Optional

import numpy as np

from pump_test_bench.app.simulation.builders import DEFAULT_METHOD, FitData, FitResult, get_builder, suggest_roles
from pump_test_bench.app.simulation.config import residual_mode, signature
from pump_test_bench.app.simulation.formula import Expression, format_expression

OUTLIER_Z = 4.0          # 稳健 z 分数超过此值的样本列为可疑
NO_RELATION_RATIO = 0.9  # 交叉验证误差不比“用平均值”好 10% 以上时，判为与变量无明显关系


# --------------------------------------------------------------------------- 数据
def sample_key(s: Dict) -> str:
    return f"{s.get('group', '')}/{s['file']}"


def prepare(samples: List[Dict], cfg: Dict) -> Dict:
    """→ {"variables": {名: 数组}, "groups", "files", "keys", "samples"}，只保留输入齐全的样本。"""
    names = [i["name"] for i in cfg["inputs"]]
    usable = [s for s in samples if all(n in s["condition"] for n in names)]
    return {
        "variables": {n: np.array([s["condition"][n] for s in usable], dtype=float) for n in names},
        "groups": np.array([s.get("group", "") for s in usable]),
        "files": [s["file"] for s in usable],
        "keys": [sample_key(s) for s in usable],
        "samples": usable,
    }


def output_values(data: Dict, name: str) -> np.ndarray:
    return np.array([np.nan if s["outputs"].get(name) is None else s["outputs"][name] for s in data["samples"]], dtype=float)


def resolve_roles(cfg: Dict, data: Dict) -> Dict[str, str]:
    """变量角色：配置里写明的照用，auto 按数据建议（看所有自动拟合输出）。"""
    ys = [output_values(data, o["name"]) for o in cfg["outputs"] if o.get("method", DEFAULT_METHOD) == "autofit"]
    return suggest_roles(cfg["inputs"], data["variables"], ys or [output_values(data, cfg["outputs"][0]["name"])])


def _fit_data(cfg: Dict, output: Dict, data: Dict, mask: Optional[np.ndarray] = None) -> FitData:
    y = output_values(data, output["name"])
    ok = np.isfinite(y) if mask is None else (np.isfinite(y) & mask)
    return FitData({k: v[ok] for k, v in data["variables"].items()}, y[ok], data["groups"][ok], output, cfg["inputs"],
                   [f for f, m in zip(data["keys"], ok) if m])


def fit_output(cfg: Dict, output: Dict, data: Dict, roles: Dict[str, str], mask: Optional[np.ndarray] = None,
               refit: Optional[Dict] = None) -> FitResult:
    fd = _fit_data(cfg, output, data, mask)
    if fd.n == 0:
        raise ValueError(f"输出“{output['name']}”在正常数据中没有读数")
    if refit:  # 交叉验证时按构建器给出的方式只重估系数
        o = {**output, "method": refit.get("method", "formula"), "formula": refit}
        return get_builder(o["method"]).fit(FitData(fd.variables, fd.y, fd.groups, o, fd.inputs, fd.files))
    builder = get_builder(output.get("method", DEFAULT_METHOD))
    if output.get("method", DEFAULT_METHOD) == "autofit":
        return builder.fit(fd, roles=roles)
    return builder.fit(fd)


def predict_values(fit: FitResult, variables: Dict[str, np.ndarray]) -> np.ndarray:
    return Expression(fit.expression).evaluate({**fit.coefficients, **variables})


def _has_free(output: Dict, fit: FitResult) -> bool:
    """该输出的结果是否由数据拟合得到（决定标定离散是否需要交叉验证残差）。"""
    if output.get("method", DEFAULT_METHOD) != "formula":
        return True
    return bool(fit.info.get("fitted"))


# --------------------------------------------------------------------------- 评估
def _err(y: np.ndarray, p: np.ndarray, mode: str) -> Optional[float]:
    ok = np.isfinite(y) & np.isfinite(p)
    if not ok.any():
        return None
    r = (y[ok] - p[ok]) if mode == "absolute" else (y[ok] - p[ok]) / np.where(np.abs(p[ok]) > 1e-12, p[ok], np.nan)
    r = r[np.isfinite(r)]
    return float(np.sqrt(np.mean(r ** 2))) if len(r) else None


def _resid(y: np.ndarray, p: np.ndarray, mode: str) -> np.ndarray:
    with np.errstate(all="ignore"):
        return (y - p) if mode == "absolute" else (y - p) / np.where(np.abs(p) > 1e-12, p, np.nan)


def assess(output: Dict, data: Dict, fit: FitResult, cv_pred: np.ndarray) -> Dict:
    """误差、与常数模型比较、各组误差、异常样本、建议。"""
    mode = residual_mode(output)
    y = output_values(data, output["name"])
    pred = predict_values(fit, data["variables"])
    pred = np.broadcast_to(pred, y.shape).astype(float)
    groups = data["groups"]
    ok = np.isfinite(y)
    # 常数模型（留一组的平均值）作为参照
    const = np.full_like(y, np.nan)
    for g in np.unique(groups):
        te, tr = (groups == g) & ok, (groups != g) & ok
        const[te] = np.mean(y[tr]) if tr.any() else np.mean(y[ok])
    cv_err, const_err = _err(y, cv_pred, mode), _err(y, const, mode)
    per_group = {str(g): _err(y[groups == g], cv_pred[groups == g], mode) for g in np.unique(groups)}

    constant = bool(ok.sum() > 1 and np.ptp(y[ok]) <= 1e-9 * max(1.0, abs(float(np.mean(y[ok])))))
    suggestions = []
    if constant:
        suggestions.append("该输出在正常数据中恒定，按固定值比较；偏离固定值即报")
    elif cv_err is not None and const_err and cv_err >= NO_RELATION_RATIO * const_err:
        suggestions.append("与变量无明显关系（模型不比用平均值准），建议移除该输出或设为“补充依据”")
    worst = max(((g, e) for g, e in per_group.items() if e is not None), key=lambda t: t[1], default=None)
    if worst and cv_err and worst[1] > 2 * cv_err and len(per_group) > 2:
        suggestions.append(f"在“{worst[0]}”的误差明显偏大，这段工况的规律可能不同，或该组数据有问题")

    r = _resid(y, cv_pred, mode)
    rr = r[np.isfinite(r)]
    if not _has_free(output, fit) and len(rr) and not constant:
        bias = float(np.mean(rr))
        big = abs(bias) > 0.05 if mode == "relative" else (const_err and abs(bias) > 0.5 * const_err)
        if big:
            text = f"{bias * 100:+.1f}%" if mode == "relative" else f"{bias:+.4g} {output.get('unit', '')}"
            suggestions.append(f"公式与现场平均相差 {text}：诊断时会作为固有偏差扣除，但请核对公式、系数和单位"
                               "（如流量计 K 系数、质量流量单位），或把部分系数改为“由数据拟合”")

    # 异常样本：先去掉残差随预期值的平滑变化（固有偏差），再看稳健 z 分数
    outliers = []
    fin = np.isfinite(r) & np.isfinite(cv_pred)
    if fin.sum() >= 8:
        pv = cv_pred[fin]
        A = np.column_stack([np.ones(fin.sum()), pv, pv ** 2]) if np.ptp(pv) > 0 else np.ones((fin.sum(), 1))
        coef, *_ = np.linalg.lstsq(A, r[fin], rcond=None)
        detr = np.full_like(r, np.nan)
        detr[fin] = r[fin] - A @ coef
        dd = detr[fin]
        med = float(np.median(dd))
        mad = float(np.median(np.abs(dd - med))) * 1.4826
        if mad > 0:
            for k, v in enumerate(detr):
                if np.isfinite(v) and abs(v - med) / mad > OUTLIER_Z:
                    outliers.append({"key": data["keys"][k], "residual": float(r[k]), "z": float(abs(v - med) / mad)})

    points = [{"key": data["keys"][k], "group": str(groups[k]), "measured": float(y[k]),
               "fitted": float(pred[k]) if np.isfinite(pred[k]) else None,
               "cv": float(cv_pred[k]) if np.isfinite(cv_pred[k]) else None,
               "x": {n: float(v[k]) for n, v in data["variables"].items()}}
              for k in range(len(y)) if np.isfinite(y[k])]
    return {"mode": mode, "unit": output.get("unit", ""), "cv_error": cv_err, "fit_error": _err(y, pred, mode),
            "const_error": const_err, "per_group": per_group, "constant": constant,
            "suggestions": suggestions, "outliers": outliers, "points": points}


def cross_validate(cfg: Dict, output: Dict, data: Dict, roles: Dict[str, str], fit: FitResult) -> np.ndarray:
    """留一组交叉验证的预测值；只有一组时退化为留一文件。没有拟合系数的公式不需要交叉验证。"""
    y = output_values(data, output["name"])
    if not _has_free(output, fit):
        return np.broadcast_to(predict_values(fit, data["variables"]), y.shape).astype(float)
    groups = data["groups"]
    folds = [groups == g for g in np.unique(groups)]
    if len(folds) < 2:
        folds = [np.arange(len(y)) == k for k in range(len(y))]
    pred = np.full(len(y), np.nan)
    for te in folds:
        try:
            part = fit_output(cfg, output, data, roles, mask=~te, refit=fit.refit)
        except ValueError:
            continue
        sub = {k: v[te] for k, v in data["variables"].items()}
        pred[te] = np.broadcast_to(predict_values(part, sub), (int(te.sum()),))
    return pred


# --------------------------------------------------------------------------- 整个模型
def input_ranges(data: Dict) -> Dict[str, List[float]]:
    return {n: [float(np.min(v)), float(np.max(v))] for n, v in data["variables"].items() if len(v)}


def fit_model(samples: List[Dict], cfg: Dict, outputs: Optional[List[str]] = None,
              progress: Optional[Callable[[str, int, int], None]] = None) -> Dict:
    """拟合并评估模型的各输出（预览与建立共用）。返回 {"roles", "ranges", "outputs": {名: {...}}, "data"}。"""
    say = progress or (lambda *_: None)
    data = prepare(samples, cfg)
    if not data["samples"]:
        raise ValueError("正常数据中没有输入齐全的工况")
    uses_roles = any(o.get("method", DEFAULT_METHOD) == "autofit" for o in cfg["outputs"])
    roles = resolve_roles(cfg, data) if uses_roles else {}
    result: Dict[str, Dict] = {}
    targets = [o for o in cfg["outputs"] if outputs is None or o["name"] in outputs]
    for k, o in enumerate(targets):
        say(f"拟合 {o['name']}", k, len(targets))
        try:
            fit = fit_output(cfg, o, data, roles)
        except ValueError as exc:
            result[o["name"]] = {"error": str(exc), "method": o.get("method", DEFAULT_METHOD)}
            continue
        cv = cross_validate(cfg, o, data, roles, fit)
        result[o["name"]] = {
            "method": o.get("method", DEFAULT_METHOD), "expression": fit.expression,
            "coefficients": fit.coefficients, "display": format_expression(fit.expression, fit.coefficients),
            "info": fit.info, "refit": fit.refit, "fitted_from_data": _has_free(o, fit),
            "assessment": assess(o, data, fit, cv), "_cv": cv,
        }
    return {"roles": roles, "ranges": input_ranges(data), "outputs": result, "data": data}


def formula_table(cfg: Dict, fitted: Dict, source: str = "") -> Dict:
    """拟合结果 → 模型产物（kind = formula），诊断时直接按公式计算。"""
    ranges = fitted["ranges"]
    formulas = {}
    for name, r in fitted["outputs"].items():
        if "error" in r:
            continue
        a = r["assessment"]
        formulas[name] = {
            "method": r["method"], "expression": r["expression"], "coefficients": r["coefficients"],
            "display": r["display"], "info": r["info"], "fitted_from_data": r["fitted_from_data"],
            "assessment": {k: a[k] for k in ("mode", "unit", "cv_error", "fit_error", "const_error", "per_group",
                                            "constant", "suggestions", "outliers")},
        }
    labels = {"autofit": "自动拟合", "formula": "自定义公式"}
    methods = sorted({labels.get(f["method"], f["method"]) for f in formulas.values()})
    return {
        "version": 3,
        "kind": "formula",
        "model_id": cfg["id"],
        "model_name": cfg["name"],
        "signature": signature(cfg),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": {"type": "surrogate", "label": "数据代理模型（" + "+".join(methods) + "）"},
        "roles": fitted["roles"],
        "inputs": [{"name": s["name"], "unit": s.get("unit", ""), "range": ranges.get(s["name"]),
                    "grid": _display_grid(ranges.get(s["name"])), "role": fitted["roles"].get(s["name"]),
                    "source": _source_text(s)} for s in cfg["inputs"]],
        "outputs": [{k: o[k] for k in ("name", "unit", "kind", "columns", "residual") if k in o} for o in cfg["outputs"]
                    if o["name"] in formulas],
        "formulas": formulas,
        "source": source,
    }


def _display_grid(rng: Optional[List[float]]) -> List[float]:
    if not rng:
        return []
    lo, hi = rng
    return [lo, (lo + hi) / 2, hi] if hi > lo else [lo]


def _source_text(s: Dict) -> str:
    if s.get("derived") == "density":
        return f"由 {s.get('temperature_column')} 算密度"
    if s.get("derived") == "viscosity":
        return f"由 {s.get('temperature_column')} 算黏度"
    if s.get("constant") is not None and not s.get("column") and not s.get("columns"):
        return f"常数 {s['constant']}"
    src = s.get("column") or "、".join(s.get("columns", []))
    if s.get("scale", 1) != 1 or s.get("offset", 0):
        src += f"（×{s.get('scale', 1):g}" + (f" {s['offset']:+g}" if s.get("offset") else "") + "）"
    return src
