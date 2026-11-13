import math

import pytest

from pump_test_bench.app.core import flow_meter
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


def test_report_docx_renders(env):
    from pump_test_bench.tests.test_diagnosis import healthy_frame
    from pump_test_bench.app.diagnosis.engine import diagnose_frame
    task = {"task_id": "t1", "file_name": "x.txt"}
    report = build_report(task, diagnose_frame(healthy_frame()), operator="admin")
    assert report["result"] == "normal" and report["product_info"]["serial"] == "t1"
    content = render_docx(report)
    assert content[:2] == b"PK"  # docx 是 zip 文件
