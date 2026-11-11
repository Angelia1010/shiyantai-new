/** 诊断报告的展示辅助。报告结构见后端 pump_test_bench/app/core/report.py。 */

export const RESULT_LABELS = {
  normal: '正常',
  abnormal: '异常',
  inconclusive: '无法判定'
}

export function resultLabel(result) {
  return RESULT_LABELS[result] || '诊断中'
}

/** 报告 → 工作台/结果页使用的摘要。 */
export function summarizeReport(taskId, fileName, report) {
  return {
    taskId,
    fileName,
    result: report.result,
    statusText: resultLabel(report.result),
    timestamp: new Date().toLocaleString(),
    diagnosis: report.diagnosis || {},
    indicators: report.indicators || [],
    repairAdvice: report.repair_advice || '',
    isPreliminary: !!report.is_preliminary
  }
}
