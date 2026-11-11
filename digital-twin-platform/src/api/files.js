import request from '@/utils/request'

const BASE = '/api/file'

/** 目录下的数据文件 → { path, files: [文件名] } */
export function listFiles(path) {
  return request({ url: `${BASE}/files`, method: 'get', params: { path } })
}

/** 分页读取 → { sheet, page, page_size, total_rows, has_more, columns: {列名: [值]} } */
export function readFilePage(path, fileName, page, pageSize) {
  return request({ url: `${BASE}/files/page`, method: 'get', params: { path, file_name: fileName, page, page_size: pageSize } })
}

/** 切换监控目录 → { path, latest_seq } */
export function setWatchPath(path) {
  return request({ url: `${BASE}/watch`, method: 'post', data: { path } })
}

/** 取序号 since 之后的文件事件 → { latest_seq, directory, events: [{seq, type, file_name}] } */
export function getWatchEvents(since) {
  return request({ url: `${BASE}/watch/events`, method: 'get', params: { since }, silent: true })
}
