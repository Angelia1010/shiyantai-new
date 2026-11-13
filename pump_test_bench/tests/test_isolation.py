"""故障隔离、变点检测与历史漂移：纯算法单元测试 + 真实数据上的典型场景。"""
import numpy as np
import pandas as pd
import pytest

from pump_test_bench.app.diagnosis import changepoint, isolation as iso
from pump_test_bench.app.diagnosis.engine import diagnose_frame
from pump_test_bench.tests.test_diagnosis import METERS, _real, decisive, healthy_frame

SIGMA = 0.003
LAYOUT = {"R1": (iso.RETURN, iso.VOLUME), "R2": (iso.RETURN, iso.VOLUME), "S1": (iso.SUPPLY, iso.VOLUME),
          "S2": (iso.SUPPLY, iso.VOLUME), "G": (iso.SUPPLY, iso.VOLUME), "M": (iso.RETURN, iso.MASS)}


def _isolate(deviations, anchor=None):
    obs = [iso.Observation(k, side, kind, deviations.get(k, 0.0), SIGMA) for k, (side, kind) in LAYOUT.items()]
    if anchor is not None:
        obs.append(iso.Observation("model", iso.SUPPLY, iso.ANCHOR, anchor, 0.006))
    return iso.isolate(obs)


def _kinds(result):
    return sorted(c.kind for c in result.best.causes)


@pytest.mark.parametrize("deviations, anchor, kinds", [
    ({}, 0.0, []),
    ({"R2": -0.03}, None, [iso.METER]),
    ({"S1": -0.03, "R1": -0.03}, None, [iso.METER, iso.METER]),          # 两只表同时坏：不会把好表也拖下水
    ({"R1": -0.03, "R2": -0.03, "M": -0.03}, 0.0, [iso.LEAK]),
    ({"S1": 0.03, "S2": 0.03, "G": 0.03}, 0.0, [iso.SUPPLY_GROUP]),       # 有模型参照：供油侧整体偏高 ≠ 泄漏
    ({"R1": -0.03, "R2": -0.03}, None, [iso.RETURN_GROUP]),
    ({"R1": 0.04, "R2": 0.04, "M": -0.02}, None, [iso.AERATION]),
    ({k: -0.02 for k in ("R1", "R2", "S1", "S2", "G")}, 0.0, [iso.VOLUME_GROUP]),
    ({k: -0.08 for k in LAYOUT}, 0.0, [iso.METER]),                       # 所有表一致偏低、模型预期不变：实际流量变了
])
def test_isolation_picks_simplest_consistent_explanation(deviations, anchor, kinds):
    result = _isolate(deviations, anchor)
    assert _kinds(result) == kinds
    for cause in result.best.causes:
        if cause.kind == iso.METER and cause.keys == ("model",):
            assert result.best.magnitude(cause) == pytest.approx(0.08, abs=0.002)


def test_isolation_reports_ambiguity_without_anchor():
    """没有模型参照时，供油侧整体偏高与泄漏在流量计上表现相同：取更常见的泄漏，并给出另一种解释的概率。"""
    result = _isolate({"S1": 0.03, "S2": 0.03, "G": 0.03})
    assert _kinds(result) == [iso.LEAK]
    alt = result.alternatives()
    assert alt and alt[0].causes[0].kind == iso.SUPPLY_GROUP and 0.05 < alt[0].probability < result.best.probability


def test_changepoint_step_ramp_and_noise():
    rng = np.random.default_rng(0)
    t = np.arange(40.0)
    noise = {k: rng.normal(0, 0.002, 40) for k in ("A", "B")}
    scale = {"A": 0.015, "B": 0.015}
    step = changepoint.detect(t, {"A": noise["A"] + np.where(t >= 20, -0.03, 0), "B": noise["B"]}, scale)
    assert step.kind == changepoint.STEP and step.onset_s == pytest.approx(20, abs=1)
    assert set(step.shifts) == {"A"} and step.shifts["A"] == pytest.approx(-0.03, abs=0.003)
    ramp = changepoint.detect(t, {"A": noise["A"] + np.maximum(t - 10, 0) * -0.002, "B": noise["B"]}, scale)
    assert ramp.kind == changepoint.RAMP and ramp.onset_s == pytest.approx(10, abs=3)
    assert changepoint.detect(t, noise, scale) is None
    # 缓慢游走（变化与残差同一量级）不算变化
    wander = 0.01 * np.sin(t / 4)
    assert changepoint.detect(t, {"A": wander, "B": noise["B"]}, scale) is None


def _scaled(df, cols, ratio, start=0.0):
    out = df.copy()
    g = (np.arange(len(df)) >= int(len(df) * start)).astype(float)
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce") * (1 + ratio * g)
    return out


def test_mid_test_step_is_judged_on_data_after_the_change():
    body = diagnose_frame(_scaled(healthy_frame(seconds=40), ["回油流量1-2"], -0.05, start=0.5))
    assert body["result"] == "abnormal"
    assert {f["target"] for f in decisive(body)} == {"回油流量1-2"}
    assert body["causes"][0]["name"].endswith("（中途突变）")
    change = body["loops"][0]["isolation"]["change"]
    assert change["kind"] == "step" and change["onset_s"] == pytest.approx(20, abs=2)


def test_two_bad_meters_do_not_implicate_good_ones():
    body = diagnose_frame(_scaled(healthy_frame(), ["回油流量1-1", "供油流量1-1"], -0.03))
    assert {f["target"] for f in decisive(body)} == {"回油流量1-1", "供油流量1-1"}
    good = [m for m in body["loops"][0]["meters"] if m["column"] not in ("回油流量1-1", "供油流量1-1")]
    assert all(abs(m["corrected"]) < 0.005 for m in good)


def test_supply_side_bias_is_not_called_leak_with_model():
    df = _scaled(_real(), ["供油流量1-1", "供油流量1-2", "齿轮流量计"], 0.03)
    body = diagnose_frame(df)
    assert body["causes"][0]["name"] == "供油侧流量计整体偏高"
    assert not any(f["category"] == "balance" for f in decisive(body))
    # 不用模型时两者无法区分：判为泄漏，并把“供油侧整体偏高”作为其他可能列出
    no_model = diagnose_frame(df, sims=None)
    assert no_model["causes"][0]["name"] == "供回油之间泄漏"
    assert any("供油侧流量计整体偏高" in a for a in no_model["causes"][0]["alternatives"])


def test_common_mode_volume_bias_is_not_blamed_on_mass_meter():
    body = diagnose_frame(_scaled(_real(), METERS, -0.025))
    assert body["causes"][0]["name"] == "体积流量计整体偏低"
    assert body["causes"][0]["confidence"] > 0.5


def test_no_steady_segment_is_inconclusive():
    df = healthy_frame(seconds=30)
    ramp = np.linspace(0.5, 1.5, len(df))
    for c in METERS + ["回油质量流量2"]:
        df[c] = df[c] * ramp
    body = diagnose_frame(df)
    assert body["result"] == "inconclusive" and body["summary"] == "无法判定：没有稳定工况"
    assert any(f["category"] == "segment" for f in body["findings"])


def test_consistent_long_term_drift_becomes_warning():
    from pump_test_bench.app.diagnosis import faults
    from pump_test_bench.app.diagnosis.config import load_config
    from pump_test_bench.app.diagnosis.history import analyze_history, apply_history
    cfg = load_config()
    reports = [diagnose_frame(faults.drift(healthy_frame(seed=i), "回油流量1-2", -0.0017 * i), cfg=cfg)
               for i in range(12)]
    current = reports[-1]
    assert current["result"] == "normal"
    hist = analyze_history(current, reports[:-1], cfg)
    assert [(f["category"], f["severity"]) for f in hist["findings"]] == [("drift", "warning")]
    apply_history(current, hist)
    assert current["result"] == "warning" and "长期漂移" in current["causes"][0]["name"]
    # 来回波动、没有一致方向的偏差：只作注意
    jitter = [diagnose_frame(faults.drift(healthy_frame(seed=i), "回油流量1-2", 0.012 * (-1) ** i), cfg=cfg)
              for i in range(12)]
    assert all(f["severity"] != "warning" for f in analyze_history(jitter[-1], jitter[:-1], cfg)["findings"])
