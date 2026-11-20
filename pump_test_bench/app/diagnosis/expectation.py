"""各信号健康时的预期值：由仿真模型（bench.json 的 model）按当前工况给出。

工况取自信号本身（电传转速、供油温度1-2、P1），模型给出两只流量计、P9、P5、P6、回油温度的预期值，
再加上各测点在该工况下的固有偏差（用正常数据标定，见 simulation/calibration.py）。
残差 = 实测/预期 − 1（流量、P5、P6）或 实测 − 预期（P9、温度，见模型输出的 residual）。

模型不可用（未建立、配置改过未重建、被关闭、工况输入的信号不可用）时 available = False，
诊断退化为只比较两只流量计。
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import pandas as pd

from pump_test_bench.app.simulation.calibration import bias_at
from pump_test_bench.app.simulation.condition import DensityFn, condition_of, input_columns
from pump_test_bench.app.simulation.config import residual_mode
from pump_test_bench.app.simulation.table import predict, sensitivity

logger = logging.getLogger(__name__)
DECISIVE, REFERENCE, OFF = "decisive", "reference", "off"


@dataclass(frozen=True)
class Expected:
    column: str
    output: str
    value: float          # 预期读数（已含该测点的固有偏差）
    mode: str             # relative / absolute
    sigma: float          # 健康时的离散（与 mode 同单位）
    kind: str
    unit: str
    component: Optional[str] = None

    def residual(self, measured: float) -> float:
        return measured - self.value if self.mode == "absolute" else measured / self.value - 1


@dataclass
class ModelView:
    available: bool
    model_id: str = ""
    name: str = ""
    mode: str = DECISIVE
    label: str = ""
    table_created: Optional[str] = None
    condition: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    outside: List[str] = field(default_factory=list)
    expected: Dict[str, Expected] = field(default_factory=dict)
    elasticity: Dict[str, float] = field(default_factory=dict)   # 列 → d ln(读数) / d ln(实际流量)

    def get(self, column: str) -> Optional[Expected]:
        return self.expected.get(column) if self.available else None


def _find_model(sims, model_id: str):
    return next(((m, t) for m, t in sims or [] if m["id"] == model_id), (None, None))


def model_view(seg: pd.DataFrame, cfg: Dict, sims, profile: Optional[Dict], density_fn: Optional[DensityFn],
               unusable: Set[str], flow_column: str) -> ModelView:
    """unusable：自检判为不可用的列（作为工况输入时模型不可用，作为输出时不给预期值）。
    flow_column：代表实际流量的输出列（求压力对流量的弹性用）。"""
    model_id = (cfg.get("model") or {}).get("id", "bench")
    mcfg, table = _find_model(sims, model_id)
    if mcfg is None:
        return ModelView(False, model_id, notes=[f"仿真模型 {model_id} 没有可用的基准表（未建立，或配置修改后未重建）"])
    mode = ((profile or {}).get(model_id) or {}).get("mode") or mcfg.get("default_mode", DECISIVE)
    view = ModelView(False, model_id, mcfg["name"], mode, (table.get("model") or {}).get("label", ""),
                     table.get("created"))
    if mode == OFF:
        view.notes.append(f"{mcfg['name']}已在诊断方案中关闭")
        return view
    bad_inputs = [c for c in input_columns(mcfg) if c in unusable]
    if bad_inputs:
        view.notes.append(f"工况信号 {'、'.join(bad_inputs)} 不可用，无法计算模型预期值")
        return view
    cond, notes = condition_of(seg, mcfg, density_fn)
    view.condition, view.notes = cond, notes
    if len(cond) < len(table["inputs"]):
        return view
    try:
        pred, view.outside = predict(table, cond)
    except Exception:
        logger.warning("模型 %s 计算失败", model_id, exc_info=True)
        view.notes.append(f"{mcfg['name']}计算失败")
        return view
    calib = (table.get("calibration") or {}).get("columns", {})
    flow_output = None
    for o in mcfg["outputs"]:
        p, mode_o = pred.get(o["name"]), residual_mode(o)
        if p is None or (mode_o == "relative" and abs(p) < 1e-9):
            continue
        for col in o["columns"]:
            if col == flow_column:
                flow_output = o["name"]
            if col in unusable:
                continue
            c = calib.get(col, {})
            b = bias_at(c, mcfg, cond) if c else 0.0
            value = p + b if mode_o == "absolute" else p * (1 + b)
            view.expected[col] = Expected(col, o["name"], value, mode_o, float(c.get("std") or 0.0), o["kind"],
                                          o.get("unit", ""), o.get("component"))
    driver = mcfg["inputs"][0]["name"]
    if flow_output:
        for o in mcfg["outputs"]:
            if o["kind"] == "pressure" and residual_mode(o) == "relative":
                e = sensitivity(table, cond, o["name"], flow_output, driver)
                for col in o["columns"]:
                    view.elasticity[col] = e if e is not None and 0.1 < e < 3 else 0.8
    view.available = bool(view.expected)
    return view
