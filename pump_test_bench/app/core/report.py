"""诊断报告：组装报告数据，并生成 Word 文档。

报告数据（存库、供前端展示）::

    {
      "result": "normal" | "abnormal" | "inconclusive",
      "is_preliminary": bool,
      "product_info": {...},
      "indicators": [{"name", "reference", "value", "abnormal"?}],
      "diagnosis": {"fault_name", "location", "analysis"},
      "repair_advice": str,
      "preliminary": {...}            # 做过初步诊断时附带
    }
"""
from datetime import datetime
from io import BytesIO
from typing import Dict, Optional

from docx import Document
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

FONT = "微软雅黑"


def build_report(task: Dict, body: Dict, operator: str, preliminary: Optional[Dict] = None) -> Dict:
    today = datetime.now().strftime("%Y-%m-%d")
    report = {
        "result": body["result"],
        "is_preliminary": preliminary is not None and not preliminary.get("is_abnormal"),
        "product_info": {
            "name": "试验台故障诊断报告",
            "serial": task["task_id"],
            "file_name": task["file_name"],
            "diag_date": today,
            "operator": operator,
            "system": "标准试验台",
        },
        "indicators": body["indicators"],
        "diagnosis": body["diagnosis"],
        "repair_advice": body["repair_advice"],
    }
    if preliminary is not None:
        report["preliminary"] = preliminary
    return report


def _heading(doc, text: str) -> None:
    run = doc.add_paragraph().add_run(text)
    run.font.size = Pt(12)
    run.bold = True


def render_docx(report: Dict) -> bytes:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.font.size = Pt(10.5)

    title = doc.add_paragraph()
    title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    title_run = title.add_run("试验台诊断报告")
    title_run.font.size = Pt(16)
    title_run.bold = True

    info = report["product_info"]
    rows = [
        ("报告名称", info.get("name", "")),
        ("任务编号", info.get("serial", "")),
        ("数据文件", info.get("file_name", "")),
        ("诊断日期", info.get("diag_date", "")),
        ("操作人员", info.get("operator", "")),
        ("试验系统", info.get("system", "")),
    ]
    table = doc.add_table(rows=len(rows), cols=2)
    table.style = "Light Shading Accent 1"
    for row, (label, value) in zip(table.rows, rows):
        row.cells[0].width = Inches(1.5)
        row.cells[1].width = Inches(4.5)
        row.cells[0].text = f"{label}:"
        row.cells[1].text = str(value)

    _heading(doc, "一、性能指标")
    indicators = report.get("indicators") or []
    if indicators:
        table = doc.add_table(rows=len(indicators) + 1, cols=3)
        table.style = "Light Grid Accent 1"
        for cell, text in zip(table.rows[0].cells, ("指标名称", "参考", "指标值")):
            cell.text = text
        for row, item in zip(table.rows[1:], indicators):
            value = str(item.get("value", ""))
            if item.get("abnormal"):
                value += "（超限）"
            row.cells[0].text = str(item.get("name", ""))
            row.cells[1].text = str(item.get("reference", ""))
            row.cells[2].text = value

    _heading(doc, "二、诊断意见")
    diagnosis = report.get("diagnosis") or {}
    for label, key in (("故障类型", "fault_name"), ("故障定位", "location"), ("成因分析", "analysis")):
        doc.add_paragraph(f"{label}：", style="List Bullet")
        doc.add_paragraph(str(diagnosis.get(key, "")))

    _heading(doc, "三、维修建议")
    doc.add_paragraph(str(report.get("repair_advice", "")))
    doc.add_paragraph("")
    doc.add_paragraph("操作人员签名：_________________")

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
