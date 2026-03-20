import request from '@/utils/request'

export function fetchList(query) {
  return request({
    url: '/db/tasks',
    method: 'get',
    params: query
  })
}

export function downloadFile(taskId) {
  window.location.href = `/db/retrieve_report/${taskId}`;
}

export function fetchArticle(id) {
  return request({
    url: '/vue-element-admin/article/detail',
    method: 'get',
    params: { id }
  })
}


export function stopJob(task_id) {
  return request({
    url: `/db/stopJob`,
    method: 'get',
    params: { task_id }
  })
}

export function startJob(task_id) {
  return request({
    url: `/db/startJob`,
    method: 'get',
    params: { task_id }
  })
}

export function deleteJob(task_id) {
  return request({
    url: `/db/deleteJob`,
    method: 'get',
    params: { task_id }
  })
}

export function fetchReportPreview(taskId) {
  return request({
    url: `/db/report_preview/${taskId}`,
    method: 'get'
  })
}

export function fetchPv(pv) {
  return request({
    url: '/vue-element-admin/article/pv',
    method: 'get',
    params: { pv }
  })
}

export function createArticle(data) {
  return request({
    url: '/vue-element-admin/article/create',
    method: 'post',
    data
  })
}

export function updateArticle(data) {
  return request({
    url: '/vue-element-admin/article/update',
    method: 'post',
    data
  })
}
