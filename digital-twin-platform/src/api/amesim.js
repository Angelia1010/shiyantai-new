import request from '@/utils/request'

const BASE = '/api/amesim'
// 仿真可能运行较久
const SIMULATION_TIMEOUT = 10 * 60 * 1000

export function initAmesim() {
  return request({ url: `${BASE}/init`, method: 'post' })
}

/** fileName 为 AMESim 模型目录下的 .ame 文件名 */
export function openModel(fileName) {
  return request({ url: `${BASE}/model/open`, method: 'post', data: { filePath: fileName } })
}

export function closeModel() {
  return request({ url: `${BASE}/model/close`, method: 'post', silent: true })
}

export function setComponentParameter(parameter, value) {
  return request({ url: `${BASE}/model/parameters/component`, method: 'put', data: { parameter, value } })
}

export function runSimulation() {
  return request({ url: `${BASE}/simulation/run`, method: 'post', timeout: SIMULATION_TIMEOUT })
}

/** 读取模型目录下的 .data 文件，返回文件文本 */
export function readDataFile(fileName) {
  return request({ url: `${BASE}/simulation/data-file`, method: 'get', params: { fileName } })
}

/** 写入 input.data 一维表格 */
export function writeInputData(values) {
  return request({ url: `${BASE}/simulation/input-data`, method: 'post', data: { data: values } })
}
