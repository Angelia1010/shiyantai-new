"""诊断算法：用合成的健康数据 + 故障注入检验检出与定位。"""
from pathlib import Path

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
    cats = {f["category"] for f in decisive(body) if not f["category"].startswith("model")}
    assert cats == {"balance"}, decisive(body)
    assert body["loops"][0]["balance"]["corrected"] == pytest.approx(0.04, abs=0.006)
    # 涡轮流量计模型发现供油侧高于理论流量：并入泄漏这一个原因
    assert [c["name"] for c in body["causes"]] == ["供回油之间泄漏"]


def test_mass_meter_drift():
    body = diagnose_frame(faults.drift(healthy_frame(), "回油质量流量2", 0.04))
    found = {(f["category"], f["target"]) for f in decisive(body)}
    assert found - {("model_reference", "预期体积流量")} == {("mass_volume", "回油质量流量2")}
    # 涡轮流量计模型的“参考量偏差”与质量-体积校核指向同一原因
    assert [c["name"] for c in body["causes"]] == ["回油质量流量计2 零点或标定漂移"]


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
    # 只看健康基准的作用（仿真模型按真实数据标定，这只合成表的偏差与真实表不同，会被模型报出）
    assert diagnose_frame(df, sims=None)["result"] == "warning"
    assert diagnose_frame(df, baseline=base, sims=None)["result"] == "normal"
    # 扣除固有偏差后，再漂移 3% 仍能查出来
    drifted = diagnose_frame(faults.drift(df, "回油流量1-2", 0.03), baseline=base, sims=None)
    assert drifted["result"] == "abnormal" and {f["target"] for f in decisive(drifted)} == {"回油流量1-2"}


# ---------------------------------------------------------------- 物理故障模型（tools/generate_fault_data）
from pump_test_bench.tools import generate_fault_data as gen  # noqa: E402


def _inject(df, fn, prof="const", at=0.4, **kw):
    t = np.arange(len(df)) / 100
    cols = {c: pd.to_numeric(df[c]).to_numpy(dtype=float) for c in METERS + ["回油质量流量2", "供油温度1-1"]}
    out = df.copy()
    for c, v in fn(cols, gen.profile(prof, t, at), np.random.default_rng(0), **kw).items():
        out[c] = np.round(v, 3)
    return out


def test_partial_freeze_detected():
    body = diagnose_frame(_inject(healthy_frame(), gen.freeze, "step", col="回油流量1-1"))
    assert body["result"] == "abnormal"
    assert any(f["category"] == "frozen" and f["target"] == "回油流量1-1" for f in decisive(body))


def test_dropout_detected():
    body = diagnose_frame(_inject(healthy_frame(), gen.drop_zero, "step", 0.5, col="供油流量1-1"))
    found = decisive(body)
    assert body["result"] == "abnormal"
    assert {f["category"] for f in found} == {"dropout"}


def test_gradual_wear_reports_trend():
    body = diagnose_frame(_inject(healthy_frame(), gen.k_factor, "ramp", col="回油流量1-1", ratio=-0.08))
    cats = {(f["category"], f["target"]) for f in decisive(body)}
    assert ("trend", "回油流量1-1") in cats


def test_return_more_than_supply_is_not_called_leak():
    body = diagnose_frame(_inject(healthy_frame(), gen.aeration, ratio=0.04))
    assert any(f["category"] == "aeration" for f in decisive(body))
    assert not any(f["category"] == "balance" for f in decisive(body))


def test_temperature_pair_mismatch():
    df = healthy_frame()
    df["供油温度1-2"] = df["供油温度1-1"]
    body = diagnose_frame(_inject(df, gen.temp_offset, col="供油温度1-1", offset=8.0))
    assert any(f["category"] == "temperature" and f["severity"] == "abnormal" for f in decisive(body))


def test_long_term_drift_from_history():
    from pump_test_bench.app.diagnosis.history import analyze_history
    cfg = load_config()
    reports = [diagnose_frame(faults.drift(healthy_frame(seed=i), "回油流量1-2", -0.0017 * i), cfg=cfg)
               for i in range(12)]
    assert all(r["result"] == "normal" for r in reports)  # 每次都没超阈值
    hist = analyze_history(reports[-1], reports[:-1], cfg)
    assert [f["target"] for f in hist["findings"]] == ["回油流量1-2"]


def test_causes_merge_symptoms():
    body = diagnose_frame(_inject(healthy_frame(), gen.leak, "ramp", ratio=0.06))
    assert body["causes"][0]["name"].startswith("供回油之间泄漏") and len(body["causes"]) == 1
    body = diagnose_frame(_inject(healthy_frame(), gen.leak, ratio=0.04))
    # 两只回油表同时偏低而质量流量计正常：不是泄漏
    df = faults.drift(faults.drift(healthy_frame(), "回油流量1-1", -0.04), "回油流量1-2", -0.04)
    names = [c["name"] for c in diagnose_frame(df)["causes"]]
    assert names[0] == "两只回油流量计同时偏低", names


# ---------------------------------------------------------------- 仿真模型（默认基准表：正常数据的代理模型）
REAL = Path(__file__).resolve().parents[2] / "标准台性能录取数据" / "标准台性能录取数据" / "36-38摄氏度" / "S4975-P0.15.txt"


def _real():
    from pump_test_bench.app.core.data_reader import read_table
    return read_table(REAL)[1].copy()


def test_model_check_on_healthy_file():
    body = diagnose_frame(_real())
    assert body["result"] == "normal"
    assert [m["id"] for m in body["models"]] == ["bench", "turbine", "thermal"]
    for model in body["models"]:
        assert model["available"] and model["group"] is None, model["id"]
        assert all(abs(r["residual"]) < r["warn"] for r in model["rows"]), model["id"]


def test_pump_wear_found_only_by_model():
    df = _real()
    t = np.arange(len(df)) / 100
    cols = {c: pd.to_numeric(df[c]).to_numpy(dtype=float) for c in gen.PUMP_COLUMNS}
    for c, v in gen.pump_wear(cols, gen.profile("const", t), None, ratio=0.08).items():
        df[c] = v
    assert diagnose_frame(df, sims=None)["result"] == "normal"  # 各表一致，互校看不出
    body = diagnose_frame(df)
    assert body["result"] == "abnormal" and body["causes"][0]["name"] == "被试泵出力低于预期"
    bench = next(m for m in body["models"] if m["id"] == "bench")
    assert bench["group"]["pressures_follow"] is True
    # 涡轮流量计模型：质量流量也同比例减少，各表与公式一致，不应报
    turbine = next(m for m in body["models"] if m["id"] == "turbine")
    assert turbine["group"] is None
    # 诊断方案：泵-管路模型设为“仅作参考”时不影响结论
    from pump_test_bench.app.diagnosis.settings import profile
    ref = diagnose_frame(df, profile=profile({"bench": {"mode": "reference"}}, saved={}))
    assert ref["result"] == "normal"
    assert any(f.get("reference_only") for f in ref["findings"])
    off = diagnose_frame(df, profile=profile({"bench": {"mode": "off"}}, saved={}))
    assert "bench" not in [m["id"] for m in off["models"]]


def test_pressure_sensor_drift_found_by_model():
    df = _real()
    df["P5低压压力"] = pd.to_numeric(df["P5低压压力"]) + 0.02
    body = diagnose_frame(df)
    assert body["causes"][0]["name"] == "P5低压压力 压力测点偏离"


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


def test_turbine_model_reference_shift_on_mass_meter_fault():
    """质量流量计偏 +5%：各涡轮表相对公式一致偏低 → 判为参考量偏差，并入质量流量计的原因。"""
    df = _real()
    df["回油质量流量2"] = pd.to_numeric(df["回油质量流量2"]) * 1.05
    body = diagnose_frame(df)
    turbine = next(m for m in body["models"] if m["id"] == "turbine")
    assert turbine["group"]["meaning"] == "reference"
    assert len(body["causes"]) == 1 and "回油质量流量计2" in body["causes"][0]["name"]
    assert any("涡轮流量计模型" in e for e in body["causes"][0]["evidence"])


def test_thermal_model_input_sensor_shift():
    """汇流温度传感器偏 +7 ℃：温控链路模型的各温度一致偏低 → 判为模型输入测点偏差。"""
    df = _real()
    df["T9冷热油汇流后温度"] = pd.to_numeric(df["T9冷热油汇流后温度"]) + 7
    assert diagnose_frame(df, sims=None)["result"] == "normal"
    body = diagnose_frame(df)
    assert body["result"] != "normal"
    assert body["causes"][0]["name"] == "T9冷热油汇流后温度 测点偏差"
