import request from '@/utils/request'

const BASE = '/api/file'

/** 目录下的数据文件 → { path, files: [相对路径] }。recursive 为 true 时包含子目录。 */
export function listFiles(path, recursive = false) {
  return request({ url: `${BASE}/files`, method: 'get', params: { path, recursive: recursive ? 1 : 0 } })
}

/** 分页读取 → { sheet, page, page_size, total_rows, has_more, columns: {列名: [值]} }。fileName 可带子目录 */
export function readFilePage(path, fileName, page, pageSize) {
  return request({ url: `${BASE}/files/page`, method: 'get', params: { path, file_name: fileName, page, page_size: pageSize } })
}

/**
 * 设置监控目录（后端保存，服务重启后自动恢复）→ 实时监控状态 + latest_event_seq。
 * silent 为 true 时出错不弹全局提示（由调用方自己显示）。
 */
export function setWatchPath(path, silent = false) {
  return request({ url: `${BASE}/watch`, method: 'post', data: { path }, silent })
}

/** 序号 since 之后的“文件写完”事件 → { latest_seq, directory, events: [{seq, type, file_name}] } */
export function getWatchEvents(since) {
  return request({ url: `${BASE}/watch/events`, method: 'get', params: { since }, silent: true })
}

/** 实时监控状态 → { path, state: off|waiting|live, file, file_rows, updated_at, latest_seq, ... } */
export function getLiveStatus() {
  return request({ url: `${BASE}/live/status`, method: 'get', silent: true })
}

/** 序号 since 之后的实时特征帧 → { latest_seq, state, file, path, frames: [{seq, time, file, rows, stats}] } */
export function getLiveFrames(since, limit = 300) {
  return request({ url: `${BASE}/live/frames`, method: 'get', params: { since, limit }, silent: true })
}
