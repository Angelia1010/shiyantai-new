"""诊断报告：组装报告数据，并生成 Word 文档。

报告数据（存库、供前端展示）在诊断结果（见 pump_test_bench/app/diagnosis/engine.py）基础上
加上 product_info::

    {
      "result": "normal" | "warning" | "abnormal" | "inconclusive",
      "summary": "一句话结论",
      "product_info": {...},
      "condition": {...}, "segment": {...},
      "causes": [{name, severity, location, target, component, explanation, evidence, alternatives, advice}],
      "findings": [{category, severity, title, detail, target, label, component, value, threshold}],
      "history": {...}?   # 历次诊断的长期漂移检查（见 pump_test_bench/app/diagnosis/history.py）
      "loops": [...], "indicators": [{name, reference, value, abnormal?}],
      "diagnosis": {fault_name, location, analysis}, "repair_advice": str,
      "algorithm": {version, config, baseline}, "simulation": {...}?
    }
"""
from datetime import datetime
from io import BytesIO
from typing import Dict

from docx import Document
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

FONT = "微软雅黑"
RESULT_TEXT = {"normal": "正常", "warning": "预警", "abnormal": "异常", "inconclusive": "无法判定"}
RESULT_COLOR = {"normal": RGBColor(0x16, 0xA3, 0x4A), "warning": RGBColor(0xD9, 0x77, 0x06),
                "abnormal": RGBColor(0xDC, 0x26, 0x26), "inconclusive": RGBColor(0x6B, 0x72, 0x80)}
SEVERITY_TEXT = {"info": "提示", "notice": "注意", "warning": "预警", "abnormal": "异常"}


def build_report(task: Dict, body: Dict, operator: str) -> Dict:
    return {
        **body,
        "product_info": {
            "name": "试验台诊断报告",
            "serial": task["task_id"],
            "file_name": task["file_name"],
            "diag_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "operator": operator,
            "system": "标准试验台",
        },
    }


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

    _heading(doc, "一、诊断结论")
    result = report.get("result", "")
    p = doc.add_paragraph()
    run = p.add_run(f"{RESULT_TEXT.get(result, result)}　")
    run.bold = True
    run.font.size = Pt(14)
    if result in RESULT_COLOR:
        run.font.color.rgb = RESULT_COLOR[result]
    p.add_run(report.get("summary", ""))
    condition = report.get("condition") or {}
    segment = report.get("segment") or {}
    doc.add_paragraph(f"试验工况：{condition.get('label', '—')}")
    if segment:
        doc.add_paragraph(
            f"分析数据段：{segment.get('start_s', 0):.1f}–{segment.get('end_s', 0):.1f} 秒，共 {segment.get('rows', 0)} 行"
            if segment.get("found") else f"分析数据段：未识别到稳定段，使用全部 {segment.get('rows', 0)} 行数据")

    _heading(doc, "二、原因分析")
    causes = report.get("causes") or []
    if causes:
        for i, c in enumerate(causes, 1):
            p = doc.add_paragraph()
            r = p.add_run(f"{i}. [{SEVERITY_TEXT.get(c.get('severity'), '')}] {c.get('name', '')}")
            r.bold = True
            doc.add_paragraph(c.get("explanation", ""))
            for e in c.get("evidence") or []:
                doc.add_paragraph(f"依据：{e}", style="List Bullet")
            if c.get("alternatives"):
                doc.add_paragraph("其他可能：" + "；".join(c["alternatives"]), style="List Bullet")
    else:
        diagnosis = report.get("diagnosis") or {}
        doc.add_paragraph(str(diagnosis.get("analysis", "")))
    history = report.get("history") or {}
    for item in history.get("findings") or []:
        doc.add_paragraph(f"历史趋势：{item.get('detail', '')}", style="List Bullet")

    _heading(doc, "三、诊断发现（检查项）")
    shown = [f for f in report.get("findings") or [] if f.get("severity") != "info"]
    if shown:
        table = doc.add_table(rows=len(shown) + 1, cols=4)
        table.style = "Light Grid Accent 1"
        for cell, text in zip(table.rows[0].cells, ("级别", "问题", "对象", "说明")):
            cell.text = text
        for row, f in zip(table.rows[1:], shown):
            row.cells[0].text = SEVERITY_TEXT.get(f.get("severity"), "")
            row.cells[1].text = f.get("title", "")
            row.cells[2].text = f.get("label", "")
            row.cells[3].text = f.get("detail", "")
    else:
        doc.add_paragraph("未发现需要关注的问题。")

    _heading(doc, "四、检测明细")
    indicators = report.get("indicators") or []
    if indicators:
        table = doc.add_table(rows=len(indicators) + 1, cols=3)
        table.style = "Light Grid Accent 1"
        for cell, text in zip(table.rows[0].cells, ("项目", "判定标准 / 来源", "结果")):
            cell.text = text
        for row, item in zip(table.rows[1:], indicators):
            value = str(item.get("value", ""))
            if item.get("abnormal"):
                value += "（超限）"
            row.cells[0].text = str(item.get("name", ""))
            row.cells[1].text = str(item.get("reference", ""))
            row.cells[2].text = value

    _heading(doc, "五、处理建议")
    doc.add_paragraph(str(report.get("repair_advice", "")))

    algo = report.get("algorithm") or {}
    if algo:
        base = algo.get("baseline") or {}
        note = doc.add_paragraph()
        r = note.add_run(
            f"诊断算法 {algo.get('version', '')}，配置 {algo.get('config', '')}，"
            + (f"健康基准：{base.get('source', '')}（{base.get('files', '')} 个文件，{base.get('created', '')}）"
               if base else "未使用健康基准"))
        r.font.size = Pt(8)
        r.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
    doc.add_paragraph("")
    doc.add_paragraph("操作人员签名：_________________")

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
