"""从试验数据（稳定段）取出模型输入（工况）与各测点均值。"""
from typing import Dict, List, Optional, Tuple

import pandas as pd


def _mean(seg: pd.DataFrame, col: str) -> Optional[float]:
    if col not in seg.columns:
        return None
    values = pd.to_numeric(seg[col], errors="coerce").dropna()
    return float(values.mean()) if len(values) else None


def condition_of(seg: pd.DataFrame, cfg: Dict) -> Tuple[Dict[str, float], List[str]]:
    """返回 (工况 {输入名: 值}, 说明)。主测点无效（缺失或超出 valid 范围）时用备用测点；都无效则缺该输入。"""
    cond: Dict[str, float] = {}
    notes: List[str] = []
    for spec in cfg["inputs"]:
        lo, hi = spec.get("valid", [float("-inf"), float("inf")])
        for i, col in enumerate([spec["column"]] + spec.get("fallback_columns", [])):
            value = _mean(seg, col)
            if value is not None and lo <= value <= hi:
                cond[spec["name"]] = value
                if i:
                    notes.append(f"{spec['column']} 读数无效，{spec['name']}改用 {col}")
                break
        else:
            notes.append(f"缺少有效的{spec['name']}（{spec['column']}）")
    return cond, notes


def measured_means(seg: pd.DataFrame, cfg: Dict) -> Dict[str, float]:
    """各输出测点列的均值 {列: 值}。"""
    out = {}
    for o in cfg["outputs"]:
        for col in o["columns"]:
            value = _mean(seg, col)
            if value is not None:
                out[col] = value
    return out
