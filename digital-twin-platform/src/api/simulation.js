import request from '@/utils/request'

const BASE = '/api/task/simulation'

/**
 * 仿真模型状态：{ config: {model, inputs, outputs, amesim_ready}, table: {created, model, source, is_default,
 * inputs, outputs, calibration: {files, method, columns: [{column, output, bias, std, warn, alarm}]}} | null, job }
 */
export function getSimulationStatus() {
  return request({ url: `${BASE}/status`, method: 'get' })
}

/** 后台重建仿真基准表：path = 正常数据目录（需已登记），model = surrogate | amesim */
export function buildSimulationTable(path, model) {
  return request({ url: `${BASE}/table`, method: 'post', data: { path, model } })
}

/** 删除数据目录下的基准表，恢复随代码提供的默认表 */
export function resetSimulationTable() {
  return request({ url: `${BASE}/table`, method: 'delete' })
}

/** 工况试算：condition = { 电传转速, 进口压力, 油温 } → { expected: [{name, value, unit}], outside } */
export function predictSimulation(condition) {
  return request({ url: `${BASE}/predict`, method: 'post', data: { condition } })
}
