import request from '@/utils/request'

export function startAutoDiagnosis(config) {
  return request({
    url: '/db/auto_diagnosis/start',
    method: 'post',
    data: config
  })
}

export function stopAutoDiagnosis() {
  return request({
    url: '/db/auto_diagnosis/stop',
    method: 'post'
  })
}

export function getDiagnosisStatus() {
  return request({
    url: '/db/auto_diagnosis/status',
    method: 'get'
  })
}

export function getDiagnosisReport(taskId) {
  return request({
    url: `/db/report_preview/${taskId}`,
    method: 'get'
  })
}

export function getTasks(page = 1, pageSize = 10, nameOrCode = '', status = '') {
  return request({
    url: '/db/tasks',
    method: 'get',
    params: { page, pageSize, nameOrCode, status }
  })
}
