"""诊断算法：在真实的正常数据上按故障机理注入故障（tools/generate_fault_data），检验检出、定位与原因。"""
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pump_test_bench.app.diagnosis import faults
from pump_test_bench.app.diagnosis.baseline import load_baseline
from pump_test_bench.app.diagnosis.config import load_config
from pump_test_bench.app.diagnosis.engine import diagnose_frame
from pump_test_bench.tools import generate_fault_data as gen

HEALTHY = Path(__file__).resolve().parents[2] / "标准台性能录取数据" / "标准台性能录取数据"
REAL = HEALTHY / "36-38摄氏度" / "S4975-P0.15.txt"
S, R = gen.SUPPLY, gen.RETURN
COLUMNS = gen.FLOWS + [gen.MASS, gen.P1, gen.P5, gen.P6, gen.P9, gen.T_SUPPLY, gen.T_RETURN]


@lru_cache(maxsize=8)
def _read(path: Path) -> pd.DataFrame:
    from pump_test_bench.app.core.data_reader import read_table
    return read_table(path)[1]


def healthy_frame(file: str = "36-38摄氏度/S4975-P0.15.txt", seed: int = 0) -> pd.DataFrame:
    """一个真实的正常数据文件（副本）。"""
    return _read(HEALTHY / file).copy()


def _real():
    return healthy_frame()


def _inject(df, fn, prof="const", at=0.4, **kw):
    """按 tools/generate_fault_data 的故障模型注入。"""
    t = np.arange(len(df)) / 100
    cols = {c: pd.to_numeric(df[c]).to_numpy(dtype=float) for c in COLUMNS}
    out = df.copy()
    for c, v in fn(cols, gen.profile(prof, t, at), np.random.default_rng(0), **kw).items():
        out[c] = np.round(v, 3)
    return out


def diagnose(df, **kw):
    return diagnose_frame(df, baseline=load_baseline(), **kw)


def decisive(body):
    return [f for f in body["findings"] if f["severity"] in ("warning", "abnormal")]


def names(body):
    return [c["name"] for c in body["causes"]]


# ---------------------------------------------------------------- 正常数据
def test_healthy_file_is_normal():
    body = diagnose(_real())
    assert body["result"] == "normal", decisive(body)
    assert body["segment"]["found"] and body["segment"]["duration_s"] > 25
    assert body["condition"]["电传"] == 2000 and body["condition"]["P1"] == pytest.approx(0.15, abs=0.005)
    assert body["loops"][0]["isolation"]["explanation"] == "各信号都正常"
    model = body["models"][0]
    assert model["available"] and all(abs(r["residual"]) < r["warn"] for r in model["rows"])
    assert {s["column"] for s in body["signals"]} == {s["column"] for s in load_config()["signals"]}


def test_only_diagnosis_signals_are_used():
    """不在 9 个诊断信号中的测点（如已损坏的 T6、其他流量计）不影响诊断。"""
    df = _real()
    df["供油流量1-1"] = 0.0
    df["T6循环管路温度"] = 157.595
    body = diagnose(df)
    assert body["result"] == "normal" and not any(f["target"] in ("供油流量1-1", "T6循环管路温度") for f in body["findings"])


def test_report_curves_for_result_page():
    """结果页画图用的信号曲线：正常数据都在正常范围内；故障信号跑出范围，受影响的信号有标记。"""
    body = diagnose(_real())
    curves = body["curves"]
    n = len(curves["time"])
    assert 30 <= n <= 300 and curves["segment"] is not None
    by_key = {s["key"]: s for s in curves["signals"]}
    assert set(by_key) == {s["key"] for s in load_config()["signals"]}
    for key in ("supply_flow", "return_flow", "outlet_pressure", "back_pressure", "control_pressure",
                "return_temperature"):
        s = by_key[key]
        assert len(s["values"]) == len(s["expected"]) == len(s["band_low"]) == n
        inside = [lo <= v <= hi for v, lo, hi in zip(s["values"], s["band_low"], s["band_high"])
                  if None not in (v, lo, hi)]
        assert sum(inside) / len(inside) > 0.9, key
        assert s["severity"] == "info" and not s.get("affected")
    for key in ("speed", "supply_temperature", "inlet_pressure"):   # 工况输入没有模型预期
        assert "expected" not in by_key[key]
    assert by_key["inlet_pressure"]["setpoints"]

    leak = {s["key"]: s for s in diagnose(_inject(_real(), gen.leak, ratio=0.04))["curves"]["signals"]}
    ret = leak["return_flow"]
    assert ret["affected"] and ret["residual"] < -0.02
    assert ret["values"][-1] < ret["band_low"][-1]            # 注入之后跑出正常范围下限
    assert not leak["supply_flow"].get("affected")


# ---------------------------------------------------------------- 流量计
def test_meter_drift_located_and_confirmed_by_turbine_model():
    body = diagnose(_inject(_real(), gen.k_factor, col=R, ratio=-0.04))
    assert body["result"] == "abnormal" and names(body) == ["回油流量1-2 计量偏差"]
    cause = body["causes"][0]
    assert cause["confidence"] > 0.8 and "涡轮流量计模型复核" in cause["explanation"]
    turbine = body["loops"][0]["isolation"]["turbine"]
    assert [t["meter"] for t in turbine] == [R] and turbine[0]["verdict"] in ("支持", "无明显影响")
    assert turbine[0]["probability_after"] >= turbine[0]["probability_before"]
    assert turbine[0]["residual"] == pytest.approx(-0.04, abs=0.01)


def test_leak_is_told_apart_from_return_meter_by_pressures():
    leak = diagnose(_inject(_real(), gen.leak, ratio=0.04))
    assert names(leak) == ["供回油之间泄漏"] and leak["causes"][0]["confidence"] > 0.8
    meter = diagnose(_inject(_real(), gen.k_factor, col=R, ratio=-0.04))
    assert names(meter) == ["回油流量1-2 计量偏差"]


def test_two_meters_common_mode():
    body = diagnose(_inject(_real(), gen.k_factor_many, names=gen.FLOWS, ratio=-0.05))
    assert body["result"] == "abnormal" and names(body) == ["两只流量计同时偏低"]


def test_mid_test_step_is_judged_on_data_after_the_change():
    body = diagnose(_inject(_real(), gen.k_factor, "step", 0.5, col=R, ratio=-0.04))
    assert body["result"] == "abnormal" and names(body) == ["回油流量1-2 计量偏差（中途突变）"]
    change = body["loops"][0]["isolation"]["change"]
    assert change["kind"] == "step" and change["onset_s"] == pytest.approx(body["segment"]["duration_s"] / 2, abs=3)


def test_gradual_wear_is_reported_as_developing():
    body = diagnose(_inject(_real(), gen.k_factor, "ramp", col=R, ratio=-0.08))
    assert names(body)[0] == "回油流量1-2 计量偏差（正在发展）"


# ---------------------------------------------------------------- 系统与管路
def test_pump_output_drop_and_model_modes():
    df = _inject(_real(), gen.pump_wear, ratio=0.08)
    body = diagnose(df)
    assert body["result"] == "abnormal" and names(body) == ["被试泵出力低于预期"]
    assert any("电传转速信号偏高" in a for a in body["causes"][0]["alternatives"])
    from pump_test_bench.app.diagnosis.settings import profile
    ref = diagnose(df, profile=profile({"bench": {"mode": "reference"}}, saved={}))
    assert ref["result"] == "normal" and any(f.get("reference_only") for f in ref["findings"])
    off = diagnose(df, profile=profile({"bench": {"mode": "off"}}, saved={}))
    assert not off["models"][0]["available"] and any(f["title"] == "没有模型参照" for f in off["findings"])


def test_return_resistance_and_pressure_sensor():
    clog = diagnose(_inject(_real(), gen.return_resistance, dp=0.02))
    assert names(clog) == ["回油管路阻力增大"]
    p5 = diagnose(_inject(_real(), gen.pressure_offset, col=gen.P5, offset=0.012))
    assert names(p5) == ["P5低压压力 传感器偏差"]


def test_supply_section_and_setpoint():
    clog = diagnose(_inject(_real(), gen.supply_clog, dp=0.06))
    assert names(clog) == ["供油段压差异常"] and "阻力增大" in clog["causes"][0]["explanation"]
    assert any("P9" in a for a in clog["causes"][0]["alternatives"])
    p1 = diagnose(_inject(_real(), gen.inlet_sensor_drift, offset=0.05))
    assert names(p1) == ["供油段压差异常"] and "P1进口压力 传感器偏高" in p1["causes"][0]["explanation"]
    off = diagnose(_inject(_real(), gen.inlet_off_setpoint, offset=-0.015))
    assert names(off) == ["P1进口压力 偏离设定值"]


def test_temperature_rise():
    body = diagnose(_inject(_real(), gen.temp_offset, col=gen.T_RETURN, offset=7.0))
    assert names(body) == ["温升异常"] and body["causes"][0]["alternatives"]


# ---------------------------------------------------------------- 单信号自检
def test_sensor_faults_are_excluded_from_comparison():
    frozen = diagnose(_inject(_real(), gen.freeze, "step", col=R))
    assert names(frozen) == ["回油流量1-2 流量计读数冻结"]
    dropout = diagnose(_inject(_real(), gen.drop_zero, "step", 0.5, col=S))
    assert names(dropout) == ["供油流量1-2 流量计信号中断"] and dropout["segment"]["duration_s"] > 25
    broken = diagnose(_inject(_real(), gen.temp_open, "step", 0.3, col=gen.T_RETURN))
    assert names(broken) == ["回油温度1-1 温度传感器故障"]


def test_noise_and_spikes_are_warnings():
    noisy = diagnose(_inject(_real(), gen.emi_noise, col=R, ratio=0.04))
    assert noisy["result"] == "warning" and names(noisy) == ["回油流量1-2 读数波动过大"]
    spiky = diagnose(_inject(_real(), gen.pulse_loss, col=S, ratio=0.01))
    assert spiky["result"] == "warning" and names(spiky) == ["供油流量1-2 读数毛刺"]


# ---------------------------------------------------------------- 无法判定与退化
def test_no_flow_is_inconclusive_and_missing_columns_are_errors():
    df = _real()
    df[S] = 0.0
    df[R] = 0.0
    body = diagnose(df)
    assert body["result"] == "inconclusive" and body["summary"] == "无法判定：没有流量"
    with pytest.raises(ValueError, match="流量计列"):
        diagnose(_real().drop(columns=[S, R]))


def test_no_steady_segment_is_inconclusive():
    """工况来回调整（流量每 3 秒在 ±3% 之间切换，各信号按物理关系跟着变）：找不到稳定段，没有明确故障 → 无法判定。"""
    df = _real()
    t = np.arange(len(df)) / 100
    k = np.where((t // 3) % 2 == 0, 1.03, 0.97)
    for c in gen.FLOWS + [gen.MASS]:
        df[c] = pd.to_numeric(df[c]) * k
    for c in (gen.P5, gen.P6):
        df[c] = pd.to_numeric(df[c]) * k ** gen.OUTLET_EXP
    body = diagnose(df)
    assert not body["segment"]["found"]
    assert body["result"] == "inconclusive" and body["summary"] == "无法判定：没有稳定工况"


def test_without_model_only_two_meters_are_compared():
    healthy = diagnose(_real(), sims=None)
    assert healthy["result"] == "normal" and any(f["title"] == "没有模型参照" for f in healthy["findings"])
    body = diagnose(_inject(_real(), gen.k_factor, col=R, ratio=-0.05), sims=None)
    assert body["result"] == "abnormal" and names(body) == ["两只流量计不一致"]


# ---------------------------------------------------------------- 历史与基准
def test_consistent_long_term_drift_becomes_warning():
    from pump_test_bench.app.diagnosis.history import analyze_history, apply_history
    cfg = load_config()
    reports = [diagnose(faults.drift(_real(), S, -0.0013 * i), cfg=cfg) for i in range(12)]
    current = reports[-1]
    assert current["result"] == "normal"
    hist = analyze_history(current, reports[:-1], cfg)
    assert [(f["category"], f["severity"], f["target"]) for f in hist["findings"]] == [("drift", "warning", S)]
    apply_history(current, hist)
    assert current["result"] == "warning" and "长期漂移" in current["causes"][0]["name"]


def test_baseline_estimates_noise_levels():
    from pump_test_bench.app.diagnosis.baseline import build_baseline
    files = sorted((HEALTHY / "36-38摄氏度").glob("*.txt"))
    baseline, _ = build_baseline(files)
    sigma = baseline["isolation"]["sigma"]
    assert set(sigma) == {S, R, gen.P5, gen.P6, "实际流量"} and all(0 < v < 0.03 for v in sigma.values())
    assert set(baseline["turbine"]) == {S, R} and baseline["pair"]["std"] < 0.01


# ---------------------------------------------------------------- 仿真模型与扩展
def test_amesim_model_adapter_with_fake_client():
    """AMESim 适配：按配置设置参数、运行、取末段稳态均值（用假客户端，不需要 AMESim）。"""
    from pump_test_bench.app.simulation.config import load_model_cfg
    from pump_test_bench.app.simulation.models import AmesimModel

    class Fake:
        def __init__(self):
            self.calls = []

        def __getattr__(self, name):
            def call(*args):
                self.calls.append((name,) + args)
                if name == "get_simulation_results":
                    rows = [{"时间(s)": t, **{k: (100.0 if t >= 15 else 0.0) for k in args[0]}} for t in range(21)]
                    return {"data": rows}
                return {}
            return call

    cfg = json_copy(load_model_cfg("bench"))
    cfg["amesim"]["model_file"] = "pump.ame"
    cfg["amesim"]["variables"] = {"系统流量": "qout@pump01"}
    cfg["amesim"]["parameters"] = [p for p in cfg["amesim"]["parameters"] if "待填写" not in str(p)]
    fake = Fake()
    out = AmesimModel(cfg, fake).run({"电传转速": 1980, "进口压力": 0.15, "油温": 36})
    assert out == {"系统流量": 100.0}  # 末 5 秒稳态
    names = [c[0] for c in fake.calls]
    assert names[:2] == ["init_api", "open_model"] and "run_simulation" in names
    assert ("set_comp_parameter", "ordiam@flowcontrol01", "7") in fake.calls  # 1980 rpm → 2000 档
    assert any(c[0] == "write_input_data" and c[1][0] == 1980 for c in fake.calls)


def json_copy(d):
    import json
    return json.loads(json.dumps(d))


def test_diagnosis_plugins_extend_without_engine_changes():
    """扩展插件：分析器的发现参与结论与原因；推理器（如大模型智能体）给出独立意见；插件出错不影响诊断。"""
    from pump_test_bench.app.core.report import build_report, render_docx
    from pump_test_bench.app.diagnosis import plugins
    from pump_test_bench.app.diagnosis.checks import WARNING, finding

    class VibrationCheck(plugins.Analyzer):
        name, label = "test_vibration", "振动检查（测试）"

        def analyze(self, ctx):
            means = ctx.segment_means()
            assert "电传实际转速" in means and ctx.sims  # 插件能拿到稳定段数据与仿真模型
            return [finding("vibration", WARNING, "振动偏大", "振动传感器1-1 偏大（测试）", "振动传感器1-1", "振动传感器1-1")]

    class Agent(plugins.Reasoner):
        name, label = "test_agent", "智能体（测试）"

        def review(self, report, ctx):
            bench = next(c for c, _ in ctx.sims if c["id"] == "bench")
            cond = {i["name"]: 1 for i in bench["inputs"]}
            assert ctx.model_expected("bench", {**cond, "电传转速": 2000, "进口压力": 0.15, "油温": 36})
            return {"title": "综合判断", "summary": f"规则结论：{report['summary']}", "suggestions": ["复查振动"]}

    class Broken(plugins.Reasoner):
        name, label = "test_broken", "出错的插件"

        def review(self, report, ctx):
            raise RuntimeError("服务不可用")

    for p in (VibrationCheck(), Agent(), Broken()):
        (plugins.register_analyzer if isinstance(p, plugins.Analyzer) else plugins.register_reasoner)(p)
    try:
        body = diagnose_frame(_real())
        assert body["result"] == "warning"
        assert any(c["name"].startswith("振动传感器1-1") for c in body["causes"])
        reviews = {r["name"]: r for r in body["reviews"]}
        assert reviews["test_agent"]["status"] == "done" and reviews["test_agent"]["summary"].startswith("规则结论：预警")
        assert reviews["test_broken"]["status"] == "error" and "服务不可用" in reviews["test_broken"]["error"]
        report = build_report({"task_id": "t", "file_name": "a.txt", "mode": "manual"}, body, operator="tester")
        assert render_docx(report)
    finally:
        for n in ("test_vibration", "test_agent", "test_broken"):
            plugins.unregister(n)
    assert "reviews" not in diagnose_frame(_real())


def test_builtin_formula_fits_coefficients_from_data():
    """后端配置的内置公式：系数可由正常数据拟合（如涡轮流量计 K 系数）。"""
    from pump_test_bench.app.simulation.calibration import collect_samples
    from pump_test_bench.app.simulation.config import validate_model
    from pump_test_bench.app.simulation.surrogate import fit_model
    from pump_test_bench.tests.conftest import REPO_ROOT
    cfg = validate_model({
        "id": "turb_k", "name": "涡轮（K 拟合）", "engine": {"type": "surrogate"},
        "active_if": [{"column": "回油流量1-1", "min": 20}],
        "inputs": [{"name": "m", "column": "回油质量流量2", "scale": 1 / 3600, "unit": "kg/s"},
                   {"name": "rho", "derived": "density", "temperature_column": "回油温度1-1", "unit": "kg/m³"}],
        "outputs": [{"name": "f", "unit": "Hz", "kind": "flow", "columns": ["回油流量1-1转速", "回油流量1-2转速"],
                     "method": "formula", "formula": {"expression": "(m * 3600 / rho * 1000 - q0) / K", "coefficients": {
                         "q0": {"value": 0, "fit": False}, "K": {"value": 0.3, "fit": True}}}}],
    })
    files = sorted((REPO_ROOT / "标准台性能录取数据" / "标准台性能录取数据" / "36-38摄氏度").glob("*.txt"))
    out = fit_model(collect_samples(files, cfg), cfg)["outputs"]["f"]
    assert out["coefficients"]["K"] == pytest.approx(0.3049, rel=0.01)
    assert out["assessment"]["cv_error"] < 0.005
    with pytest.raises(ValueError, match="系数表"):
        validate_model({**cfg, "outputs": [{**cfg["outputs"][0], "formula": {"expression": "a * m"}}]})
