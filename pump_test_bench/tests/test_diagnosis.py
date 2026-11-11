"""诊断算法：用合成的健康数据 + 故障注入检验检出与定位。"""
import numpy as np
import pandas as pd
import pytest

from pump_test_bench.app.diagnosis import faults
from pump_test_bench.app.diagnosis.baseline import build_baseline
from pump_test_bench.app.diagnosis.config import load_config
from pump_test_bench.app.diagnosis.engine import diagnose_frame

METERS = ["回油流量1-1", "回油流量1-2", "供油流量1-1", "供油流量1-2", "齿轮流量计"]


def healthy_frame(seconds=30, flow=300.0, temp=30.0, seed=0, biases=None, ramp_s=0.0) -> pd.DataFrame:
    """模拟试验台 100 Hz 记录的一个稳定工况；ramp_s>0 时开头有一段流量爬升。"""
    rng = np.random.default_rng(seed)
    n = int(seconds * 100)
    t = np.arange(n) / 100
    level = np.where(t < ramp_s, flow * (0.5 + 0.5 * t / max(ramp_s, 1e-9)), flow)
    cfg = load_config()
    rho = cfg["fuel"]["rho15"] + cfg["fuel"]["slope"] * (temp - 15)
    biases = biases or {}
    data = {"时间": [f"10:{int(s // 60):02d}:{s % 60:06.3f}" for s in t]}
    for col in METERS:
        data[col] = np.round(level * (1 + biases.get(col, 0.0)) * (1 + rng.normal(0, 0.003, n)), 3)
    data["回油质量流量2"] = np.round(level * rho / 1000 * (1 + rng.normal(0, 0.002, n)), 3)
    data["供油温度1-1"] = np.round(temp + rng.normal(0, 0.05, n), 3)
    data["回油流量2-1"] = np.zeros(n)
    data["回油流量2-2"] = np.zeros(n)
    data["回油质量流量1"] = np.round(rng.normal(7, 3, n), 3)  # 没有流量的支路：零点附近
    data["电传实际转速"] = np.full(n, 2010.0)
    data["燃油泵实际转速"] = np.full(n, 1000.0)
    return pd.DataFrame(data)


def decisive(body):
    return [f for f in body["findings"] if f["severity"] in ("warning", "abnormal")]


def test_healthy_data_is_normal():
    body = diagnose_frame(healthy_frame())
    assert body["result"] == "normal", decisive(body)
    assert body["segment"]["found"] and body["segment"]["duration_s"] > 25
    assert body["condition"]["流量"] == pytest.approx(300, rel=0.01)
    main = body["loops"][0]
    assert main["mass"]["severity"] == "info" and abs(main["mass"]["deviation"]) < 0.01


def test_meter_drift_is_located():
    cfg = load_config()
    body = diagnose_frame(faults.drift(healthy_frame(), "回油流量1-2", -0.05), cfg=cfg)
    assert body["result"] == "abnormal"
    found = decisive(body)
    assert {f["target"] for f in found} == {"回油流量1-2"}
    assert found[0]["component"] == "回油流量计2" and found[0]["category"] == "redundancy"


def test_stuck_meter():
    body = diagnose_frame(faults.stuck(healthy_frame(), "回油流量1-1"))
    assert body["result"] == "abnormal"
    assert {(f["category"], f["target"]) for f in decisive(body)} == {("sensor", "回油流量1-1")}


def test_leak_is_not_blamed_on_single_meters():
    df = faults.leak(healthy_frame(), ["回油流量1-1", "回油流量1-2", "回油质量流量2"], 0.04)
    body = diagnose_frame(df)
    cats = {f["category"] for f in decisive(body)}
    assert cats == {"balance"}, decisive(body)
    assert body["loops"][0]["balance"]["corrected"] == pytest.approx(0.04, abs=0.006)


def test_mass_meter_drift():
    body = diagnose_frame(faults.drift(healthy_frame(), "回油质量流量2", 0.04))
    assert {(f["category"], f["target"]) for f in decisive(body)} == {("mass_volume", "回油质量流量2")}


def test_noise_and_spikes_are_warnings():
    body = diagnose_frame(faults.noise(healthy_frame(), "回油流量1-2", 0.05))
    assert body["result"] == "warning" and {f["category"] for f in decisive(body)} == {"noise"}
    body = diagnose_frame(faults.spikes(healthy_frame(), "回油流量1-1"))
    assert "spike" in {f["category"] for f in decisive(body)}


def test_broken_temperature_sensor():
    df = healthy_frame()
    df["供油温度1-1"] = 157.6  # 断线时常见的满量程读数
    body = diagnose_frame(df)
    found = decisive(body)
    assert any(f["category"] == "sensor" and f["target"] == "供油温度1-1" for f in found)
    assert any(f["category"] == "mass_volume" and f["severity"] == "notice" for f in body["findings"])


def test_no_flow_is_inconclusive_and_unknown_columns_are_errors():
    df = healthy_frame()
    for col in METERS + ["回油质量流量2"]:
        df[col] = 0.0
    assert diagnose_frame(df)["result"] == "inconclusive"
    df["回油质量流量2"] = 230.0  # 体积流量计都是 0，质量流量计却有读数：零点/接线问题
    assert {f["category"] for f in decisive(diagnose_frame(df))} == {"zero"}
    with pytest.raises(ValueError, match="流量计列"):
        diagnose_frame(pd.DataFrame({"压力": [1.0, 2.0]}))


def test_steady_segment_skips_ramp():
    body = diagnose_frame(healthy_frame(seconds=40, ramp_s=8))
    assert body["result"] == "normal"
    assert body["segment"]["start_s"] >= 7.5


def test_baseline_removes_fixed_meter_bias(tmp_path):
    # 某只表天生偏高 2.5%：没有基准时会预警；用健康数据建基准后扣除，判为正常
    biased = {"回油流量1-2": 0.025}
    files = []
    for i, (flow, temp) in enumerate([(150, 20), (300, 25), (450, 30), (200, 35), (350, 40), (500, 45)]):
        path = tmp_path / f"h{i}.csv"
        healthy_frame(flow=flow, temp=temp, seed=i, biases=biased).to_csv(path, index=False)
        files.append(path)
    base, skipped = build_baseline(files)
    assert not skipped and base["files"] == 6
    assert base["meters"]["回油流量1-2"]["bias"] == pytest.approx(0.025, abs=0.004)
    assert base["density"]["slope"] == pytest.approx(load_config()["fuel"]["slope"], abs=0.1)

    df = healthy_frame(flow=320, temp=32, seed=99, biases=biased)
    assert diagnose_frame(df)["result"] == "warning"
    assert diagnose_frame(df, baseline=base)["result"] == "normal"
    # 扣除固有偏差后，再漂移 3% 仍能查出来
    drifted = diagnose_frame(faults.drift(df, "回油流量1-2", 0.03), baseline=base)
    assert drifted["result"] == "abnormal" and {f["target"] for f in decisive(drifted)} == {"回油流量1-2"}
