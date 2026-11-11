import request from '@/utils/request'
import { downloadWithAuth } from '@/utils/download'

const BASE = '/api/task'

/** 任务列表：{ page, page_size, keyword, status, start_time, end_time } → { items, total } */
export function listTasks(params) {
  return request({ url: `${BASE}/tasks`, method: 'get', params })
}

/** 为一个数据文件创建诊断任务。mode: realtime | file */
export function createTask(path, fileName, mode) {
  return request({ url: `${BASE}/tasks`, method: 'post', data: { path, file_name: fileName, mode } })
}

export function getTask(taskId) {
  return request({ url: `${BASE}/tasks/${encodeURIComponent(taskId)}`, method: 'get' })
}

export function deleteTasks(taskIds) {
  return request({ url: `${BASE}/tasks/delete`, method: 'post', data: { task_ids: taskIds } })
}

/** 流量计精确诊断，返回报告。 */
export function diagnoseTask(taskId, density) {
  return request({ url: `${BASE}/tasks/${encodeURIComponent(taskId)}/diagnose`, method: 'post', data: { density } })
}

/**
 * 初步诊断（试验数据 vs 仿真数据）。异常时后端会接着做精确诊断。
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
