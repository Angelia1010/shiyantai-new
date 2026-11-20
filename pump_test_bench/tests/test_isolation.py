"""故障隔离与变点检测：纯算法单元测试（不读数据文件）。"""
import numpy as np
import pytest

from pump_test_bench.app.diagnosis import changepoint, hypotheses as hy, isolation as iso

S, R, P5, P6 = "供油流量1-2", "回油流量1-2", "P5低压压力", "P6定压压力"
E = 0.8   # 压力对流量的弹性
SIGMA = {S: 0.0025, R: 0.0025, P5: 0.009, P6: 0.009, hy.ANCHOR: 0.006}


def _isolate(dev, turbine=None):
    obs = [iso.Observation(S, dev.get(S, 0.0), SIGMA[S]), iso.Observation(R, dev.get(R, 0.0), SIGMA[R]),
           iso.Observation(P5, dev.get(P5, 0.0), SIGMA[P5], E), iso.Observation(P6, dev.get(P6, 0.0), SIGMA[P6], E),
           iso.Observation(hy.ANCHOR, 0.0, SIGMA[hy.ANCHOR])]
    layout = hy.Layout(S, R, {P5: E, P6: E}, {})
    for col, value in (turbine or {}).items():
        key = hy.turbine_key(col)
        obs.append(iso.Observation(key, value, 0.005 / np.sqrt(0.3), 0.0))
        layout.turbine[col] = key
    pool = hy.catalog(layout, [o.key for o in obs], 9.0, 3.0)
    return iso.isolate(obs, pool)


def _kinds(result):
    return sorted(c.kind for c in result.best.causes)


@pytest.mark.parametrize("dev, kinds", [
    ({}, []),
    ({R: -0.03}, [hy.METER]),
    ({S: 0.03}, [hy.METER]),
    ({R: -0.03, P5: -0.024, P6: -0.024}, [hy.LEAK]),                          # 回油少了，压力随之降低
    ({S: -0.05, R: -0.05, P5: -0.04, P6: -0.04}, [hy.FLOW_CHANGE]),          # 实际流量变了，各信号一致
    ({S: -0.03, R: -0.03}, [hy.METERS_COMMON]),                                # 两表同偏，压力不变
    ({P5: 0.06, P6: 0.06}, [hy.RETURN_RESISTANCE]),                            # 流量不变，背压升高
    ({P5: 0.06}, [hy.PRESSURE_SENSOR]),
    ({S: 0.03, P6: -0.06}, [hy.METER, hy.PRESSURE_SENSOR]),                    # 两处独立故障
])
def test_isolation_picks_simplest_consistent_explanation(dev, kinds):
    assert _kinds(_isolate(dev)) == kinds


def test_flow_change_magnitude_and_sign():
    best = _isolate({S: -0.05, R: -0.05, P5: -0.04, P6: -0.04}).best
    cause = best.causes[0]
    assert cause.kind == hy.FLOW_CHANGE and best.magnitude(cause) == pytest.approx(0.05, abs=0.005)  # 锚点偏高 = 实际流量偏低
    assert "实际流量比模型预期低" in hy.describe_fit(best, {})


def test_turbine_evidence_shifts_meter_vs_leak():
    """回油表偏低 2%、压力只降了一点：只看主信号时泄漏与单表偏离难分；涡轮模型复核让结论更明确。"""
    dev = {R: -0.02, P5: -0.008, P6: -0.008}

    def p_meter(r):
        return r.probability_of(lambda f: hy.involves(f, R))

    base = _isolate(dev)
    assert p_meter(_isolate(dev, {R: -0.02})) > p_meter(base)       # 涡轮模型也说这只表少计 → 更像表的问题
    assert p_meter(_isolate(dev, {R: 0.0})) < p_meter(base)         # 涡轮模型说这只表准 → 更像泄漏


def test_ambiguity_is_reported_as_alternatives():
    result = _isolate({R: -0.02, P5: -0.008, P6: -0.008})
    assert result.alternatives(0.05) and abs(sum(f.probability for f in result.ranked) - 1) < 1e-9


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
    assert changepoint.detect(t, {"A": 0.01 * np.sin(t / 4), "B": noise["B"]}, scale) is None
