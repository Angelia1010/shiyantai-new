# -*- coding: utf-8 -*-
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from datetime import datetime
import os
import base64
from io import BytesIO


class FuelPumpDiagnosisReporter:
    def __init__(self, template_path=None):
        """
        初始化伺服燃油泵诊断报告生成器
        :param template_path: 自定义模板路径（可选）
        """
        self.template = template_path
        self.styles = {
            'title': {'font': '微软雅黑', 'size': 16, 'bold': True, 'color': (0, 0, 0)},
            'header': {'font': '微软雅黑', 'size': 12, 'bold': True, 'color': (0, 0, 0)},
            'normal_text': {'font': '微软雅黑', 'size': 10.5}
        }

    def generate_report(self, product_info, indicators, diagnosis, repair_advice, output_dir=None):
        """
        生成诊断报告
        :param product_info: 产品信息字典
            - name: 产品名称
            - date: 出厂日期
            - serial: 产品编号
            - diag_date: 诊断日期
            - operator: 操作人员
            - system: 试验系统
        :param indicators: 异常指标列表，每个指标应包含：
            - name: 指标名称
            - reference: 指标类型
            - value: 诊断值
        :param diagnosis: 诊断信息字典
            - location: 故障定位
            - analysis: 故障成因初步分析
        :param repair_advice: 维修建议
        :param output_dir: 输出目录路径
        :return: 生成的报告文件路径
        """
        doc = Document(self.template) if self.template else Document()
        self._setup_document_styles(doc)
        self._add_product_info(doc, product_info)
        self._add_indicators(doc, indicators)
        self._add_diagnosis(doc, diagnosis)
        self._add_repair_advice(doc, repair_advice)
        #return self._save_document(doc, output_dir)
        return self.save_document_as_base64(doc)

    def _setup_document_styles(self, doc):
        """配置文档默认样式"""
        styles = doc.styles
        normal_style = styles['Normal']
        normal_style.font.name = '微软雅黑'
        normal_style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        normal_style.font.size = Pt(self.styles['normal_text']['size'])

    def _add_product_info(self, doc, product_info):
        """添加产品信息部分"""
        # 添加标题
        title_para = doc.add_paragraph()
        title_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        title_run = title_para.add_run("试验台诊断报告\n")
        title_run.font.size = Pt(self.styles['title']['size'])
        title_run.bold = self.styles['title']['bold']
        
        # 添加产品信息表格
        table = doc.add_table(rows=6, cols=2)
        table.style = 'LightShading-Accent1'
        
        # 设置表格宽度
        for row in table.rows:
            for idx, cell in enumerate(row.cells):
                if idx == 0:
                    cell.width = Inches(1.5)
                else:
                    cell.width = Inches(3.5)
        
        # 填充产品信息
        cells = table._cells
        cells[0].text = "产品名称:"
        cells[1].text = product_info.get('name', '')
        cells[2].text = "出厂日期:"
        cells[3].text = product_info.get('date', '')
        cells[4].text = "产品编号:"
        cells[5].text = product_info.get('serial', '')
        cells[6].text = "诊断日期:"
        cells[7].text = product_info.get('diag_date', '')
        cells[8].text = "操作人员:"
        cells[9].text = product_info.get('operator', '')
        cells[10].text = "试验系统:"
        cells[11].text = product_info.get('system', '')
        
        doc.add_paragraph("\n")  # 添加空行分隔

    def _add_indicators(self, doc, indicators):
        """添加异常性能指标部分"""
        # 添加标题
        heading = doc.add_paragraph()
        heading.add_run("一、异常性能指标摘要").font.size = Pt(self.styles['header']['size'])
        heading.runs[0].bold = self.styles['header']['bold']
        
        # 添加指标表格
        if indicators:
            table = doc.add_table(rows=len(indicators)+1, cols=3)
            table.style = 'LightGrid-Accent1'
            
            # 设置表头
            hdr = table.rows[0].cells
            hdr[0].text = "指标名称"
            hdr[1].text = "指标类型"
            hdr[2].text = "指标值"
            
            # 填充指标数据
            for idx, indicator in enumerate(indicators, 1):
                row = table.rows[idx].cells
                row[0].text = indicator.get('name', '')
                row[1].text = str(indicator.get('reference', ''))
                row[2].text = str(indicator.get('value', ''))
        
        doc.add_paragraph("\n")  # 添加空行分隔

    def _add_diagnosis(self, doc, diagnosis):
        """添加初步诊断意见部分"""
        # 添加标题
        heading = doc.add_paragraph()
        heading.add_run("二、初步诊断意见").font.size = Pt(self.styles['header']['size'])
        heading.runs[0].bold = self.styles['header']['bold']
        
        # 添加诊断内容
        if diagnosis:
            doc.add_paragraph("故障类型:", style='ListBullet')
            doc.add_paragraph(diagnosis.get('fault_name', ''))

            doc.add_paragraph("故障定位:", style='ListBullet')
            doc.add_paragraph(diagnosis.get('location', ''))
            
            doc.add_paragraph("故障成因初步分析:", style='ListBullet')
            doc.add_paragraph(diagnosis.get('analysis', ''))
        
        doc.add_paragraph("\n")  # 添加空行分隔

    def _add_repair_advice(self, doc, repair_advice):
        """添加维修建议部分"""
        # 添加标题
        heading = doc.add_paragraph()
        heading.add_run("三、维修建议").font.size = Pt(self.styles['header']['size'])
        heading.runs[0].bold = self.styles['header']['bold']
        
        # 添加维修建议内容
        doc.add_paragraph(repair_advice)
        
        # 添加签名行
        doc.add_paragraph("\n\n")
        doc.add_paragraph("操作人员签名:_________________")
        doc.add_paragraph("联系方式:_________________（电话）")

    def _save_document(self, doc, output_dir):
        """保存文档"""
        if not output_dir:
            output_dir = os.path.join(os.getcwd(), "fuel_pump_reports")
        os.makedirs(output_dir, exist_ok=True)

        filename = f"FuelPump_Diagnosis_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        filepath = os.path.join(output_dir, filename)
        doc.save(filepath)
        return filepath

    def save_document_as_base64(self, doc):
        """
        将生成的Word文档保存为Base64编码
        :param doc: 要保存的Word文档对象
        :return: Base64编码的字符串
        """
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode('utf-8')


# 测试样例
if __name__ == "__main__":
    # 构造测试数据
    product_info = {
        'name': '伺服燃油泵-A型',
        'date': '2023-05-15',
        'serial': 'FP-2023-0521',
        'diag_date': '2024-03-20',
        'operator': '张三',
        'system': '燃油系统测试台-2号'
    }
    
    indicators = [
        {'name': '供油压力', 'reference': '3.5-4.2 MPa', 'value': '2.8 MPa'},
        {'name': '流量稳定性', 'reference': '±2%', 'value': '±5%'},
        {'name': '响应时间', 'reference': '<0.1s', 'value': '0.15s'},
        {'name': '工作温度', 'reference': '40-80°C', 'value': '92°C'}
    ]
    
    diagnosis = {
        'location': '主泵阀组密封件',
        'analysis': '长期高温工作导致密封件老化，密封性能下降，造成压力不足和流量波动'
    }
    
    repair_advice = "1. 更换主泵阀组密封件\n2. 检查冷却系统工作状态\n3. 更换液压油并清洗系统"

    # 生成报告
    reporter = FuelPumpDiagnosisReporter()
    report_path = reporter.generate_report(
        product_info=product_info,
        indicators=indicators,
        diagnosis=diagnosis,
        repair_advice=repair_advice
    )
    
    print(f"报告已生成，保存路径: {report_path}")