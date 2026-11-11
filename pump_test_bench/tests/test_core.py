import math

import pandas as pd
import pytest

from pump_test_bench.app.core import flow_meter, preliminary
from pump_test_bench.app.core.data_reader import read_page, read_table
from pump_test_bench.app.core.report import build_report, render_docx
from pump_test_bench.tests.conftest import SAMPLE_TXT, SAMPLE_XLSX


def test_theoretical_flow_uses_blade_frequency():
    # f = 6·Y/(2π)，Y=2π rad/s 时 f=6 Hz
    assert flow_meter.theoretical_flow(2 * math.pi) == pytest.approx(0.304921 * 6 + 0.210230)


def test_read_txt_and_excel_pages(sample_dir):
    sheet, df = read_table(sample_dir / SAMPLE_TXT)
    assert sheet == "data"
    assert "燃油泵实际转速" in df.columns
    assert df["燃油泵实际转速"].dtype.kind == "f"

    page0 = read_page(sample_dir / SAMPLE_XLSX, 0, 500)
    page1 = read_page(sample_dir / SAMPLE_XLSX, 1, 500)
    assert page0["has_more"] is True and page1["has_more"] is False
    assert page0["total_rows"] == len(page0["columns"]["回油流量1-1"]) + len(page1["columns"]["回油流量1-1"])
    # NaN 被转换成 None，可以直接序列化为 JSON
    assert page0["columns"]["燃油泵实际转速"][0] is None


def test_flow_meter_diagnosis_on_sample(sample_dir):
    body = flow_meter.diagnose_flow_meters(sample_dir / SAMPLE_XLSX, density=850)
    assert body["result"] in (flow_meter.RESULT_NORMAL, flow_meter.RESULT_ABNORMAL)
    names = [i["name"] for i in body["indicators"]]
    assert "回路1流量计 理论流量" in names and "回路2流量计 理论流量" in names


def _write_xlsx(path, columns):
    pd.DataFrame(columns).to_excel(path, index=False)
    return path


def test_each_loop_uses_its_own_mass_flow_column(env):
    # 只有质量流量1：只诊断回路1，不会再因为读不到质量流量2而崩溃
    path = _write_xlsx(env / "only1.xlsx", {"回油质量流量1": [180.0, 180.0], "回油流量1-1": [50.0, 52.0]})
    body = flow_meter.diagnose_flow_meters(path, density=820)
    names = [i["name"] for i in body["indicators"]]
    assert any(n.startswith("回路1流量计") for n in names)
    assert not any(n.startswith("回路2流量计") for n in names)


def test_flow_meter_abnormal_and_inconclusive(env):
    q = flow_meter.theoretical_flow(flow_meter.simulated_speed(180 / 3600, 820))
    ok = _write_xlsx(env / "ok.xlsx", {"回油质量流量1": [180.0], "回油流量1-1": [q]})
    assert flow_meter.diagnose_flow_meters(ok, 820)["result"] == "normal"

    bad = _write_xlsx(env / "bad.xlsx", {"回油质量流量1": [180.0], "回油流量1-1": [q * 2]})
    body = flow_meter.diagnose_flow_meters(bad, 820)
    assert body["result"] == "abnormal"
    assert body["diagnosis"]["location"] == "回路1流量计"

    missing = _write_xlsx(env / "missing.xlsx", {"回油质量流量1": [180.0]})
    assert flow_meter.diagnose_flow_meters(missing, 820)["result"] == "inconclusive"


def test_flow_meter_without_mass_flow_columns_is_a_clear_error(env):
    path = _write_xlsx(env / "none.xlsx", {"压力": [1.0]})
    with pytest.raises(ValueError, match="回油质量流量1"):
        flow_meter.diagnose_flow_meters(path)


def test_density_falls_back_to_file_column(env):
    path = _write_xlsx(env / "d.xlsx", {"回油质量流量1": [180.0], "回油流量1-1": [50.0], "介质密度": [800.0]})
    body = flow_meter.diagnose_flow_meters(path)
    assert body["indicators"][0] == {"name": "介质密度", "reference": "文件", "value": "800.0 kg/m³"}


def test_preliminary_compare():
    exp = {"a": [1.0, 1.0], "b": [10.0], "c": [5.0], "d": [2.0], "e": [3.0]}
    sim = {"a": [1.0], "b": [20.0], "c": [10.0], "d": [4.0], "e": [6.0], "only_sim": [1.0]}
    result = preliminary.compare(exp, sim, threshold=0.15, exceeded_limit=3)
    assert result["total_compared"] == 5
    assert result["exceeded_count"] == 4
    assert result["is_abnormal"] is True
    assert preliminary.compare(exp, sim, exceeded_limit=4)["is_abnormal"] is False
    with pytest.raises(ValueError):
        preliminary.compare([], sim)


def test_report_docx_renders(env):
    task = {"task_id": "t1", "file_name": "x.xlsx"}
    body = preliminary.normal_report_body(preliminary.compare({"a": [1.0]}, {"a": [1.0]}))
    report = build_report(task, body, operator="admin")
    content = render_docx(report)
    assert content[:2] == b"PK"  # docx 是 zip 文件
