/** 诊断报告的展示辅助。报告结构见后端 pump_test_bench/app/core/report.py 与 app/diagnosis/engine.py。 */

export const RESULT_LABELS = {
  normal: '正常',
  warning: '预警',
  abnormal: '异常',
  inconclusive: '无法判定'
}

/** Element UI 标签颜色 */
export const RESULT_TAG = {
  normal: 'success',
  warning: 'warning',
  abnormal: 'danger',
  inconclusive: 'info'
}

export const SEVERITY_LABELS = { info: '提示', notice: '注意', warning: '预警', abnormal: '异常' }

export function resultLabel(result) {
  return RESULT_LABELS[result] || '诊断中'
}

/** 报告 → 工作台/结果页使用的摘要。 */
export function summarizeReport(taskId, fileName, report) {
  const findings = report.findings || []
  const decisive = findings.filter(f => f.severity === 'warning' || f.severity === 'abnormal')
  return {
    taskId,
    fileName,
    result: report.result,
    statusText: resultLabel(report.result),
    summary: report.summary || '',
    timestamp: (report.product_info && report.product_info.diag_date) || new Date().toLocaleString(),
    condition: report.condition || {},
    diagnosis: report.diagnosis || {},
    indicators: report.indicators || [],
    findings,
    causes: report.causes || [],
    history: report.history || null,
    loops: report.loops || [],
    repairAdvice: report.repair_advice || '',
    // 三维模型中需要告警闪烁的部件（异常优先）
    alarmComponents: [...new Set(decisive
      .slice().sort((a, b) => (a.severity === 'abnormal' ? -1 : 0) - (b.severity === 'abnormal' ? -1 : 0))
      .map(f => f.component).filter(Boolean))]
  }
}
