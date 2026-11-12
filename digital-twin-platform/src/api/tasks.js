import request from '@/utils/request'
import { downloadWithAuth } from '@/utils/download'

const BASE = '/api/task'

/** 任务列表：{ page, page_size, keyword, status, start_time, end_time, mode } → { items, total } */
export function listTasks(params) {
  return request({ url: `${BASE}/tasks`, method: 'get', params })
}

/** 为一个数据文件创建诊断任务。mode: file | realtime（auto 由后端自动诊断创建） */
export function createTask(path, fileName, mode) {
  return request({ url: `${BASE}/tasks`, method: 'post', data: { path, file_name: fileName, mode } })
}

export function getTask(taskId) {
  return request({ url: `${BASE}/tasks/${encodeURIComponent(taskId)}`, method: 'get' })
}

export function deleteTasks(taskIds) {
  return request({ url: `${BASE}/tasks/delete`, method: 'post', data: { task_ids: taskIds } })
}

/** 诊断（流量计互校、质量-体积校核、传感器自检），返回报告。density = 当前燃油 20 ℃ 密度，留空时用诊断设置里的值 */
export function diagnoseTask(taskId, density) {
  return request({ url: `${BASE}/tasks/${encodeURIComponent(taskId)}/diagnose`, method: 'post', data: { density } })
}

/**
 * 诊断并附上与 AMESim 仿真数据的对比（对比结果作为辅助证据写入报告）。
 * data: { experiment_data: {变量: [数值]}, simulation_data: {变量: [数值]}, threshold?, exceeded_limit?, density? }
 * 返回 { preliminary, report }
 */
export function preliminaryDiagnose(taskId, data) {
  return request({ url: `${BASE}/tasks/${encodeURIComponent(taskId)}/preliminary`, method: 'post', data })
}

export function getReport(taskId) {
  return request({ url: `${BASE}/tasks/${encodeURIComponent(taskId)}/report`, method: 'get' })
}

export function downloadReport(taskId) {
  return downloadWithAuth(`${BASE}/tasks/${encodeURIComponent(taskId)}/report.docx`, `${taskId}_诊断报告.docx`)
}

export function saveLogs(source, logs) {
  return request({ url: `${BASE}/logs`, method: 'post', data: { source, logs }, silent: true })
}

/** 诊断设置：{ fuel_density_20: 当前燃油 20 ℃ 密度 kg/m³ | null, fuel_note } */
export function getDiagnosisSettings() {
  return request({ url: `${BASE}/diagnosis/settings`, method: 'get' })
}

export function saveDiagnosisSettings(data) {
  return request({ url: `${BASE}/diagnosis/settings`, method: 'put', data })
}

/**
 * 历次诊断的关键指标（趋势图）。source: live（试验台实时/自动诊断）| file（手动选择文件）| all
 * 返回 { items: [{ task_id, file_name, mode, time, result, flow, temperature, meters: {列: 偏差}, labels, balance, mass }] }
 */
export function getDiagnosisHistory(days = 90, source = 'live') {
  return request({ url: `${BASE}/diagnosis/history`, method: 'get', params: { days, source } })
}
