import request from '@/utils/request'

const BASE = '/api/task/simulation'

/**
 * 仿真模型列表与状态：{ models: [{ id, name, description, components, engine, engines, inputs, outputs, rules, media,
 *   table: {created, model, source, is_default, inputs, outputs, calibration: {files, method, columns}} | null,
 *   setting: {mode, sigma_warn, sigma_alarm} }], job, modes }
 */
export function getSimulationStatus() {
  return request({ url: `${BASE}/status`, method: 'get' })
}

/** 后台重建某个模型的基准表：path = 正常数据目录，engine = surrogate | formula | amesim */
export function buildModelTable(modelId, path, engine) {
  return request({ url: `${BASE}/models/${encodeURIComponent(modelId)}/table`, method: 'post', data: { path, engine } })
}

/** 删除该模型重建的基准表，恢复随代码提供的默认表 */
export function resetModelTable(modelId) {
  return request({ url: `${BASE}/models/${encodeURIComponent(modelId)}/table`, method: 'delete' })
}

/** 工况试算：condition = { 输入名: 值 } → { expected: [{name, value, unit}], outside } */
export function predictModel(modelId, condition) {
  return request({ url: `${BASE}/models/${encodeURIComponent(modelId)}/predict`, method: 'post', data: { condition } })
}

/** 保存诊断方案：models = { 模型 id: { mode: decisive|reference|off, sigma_warn, sigma_alarm } } */
export function saveDiagnosisProfile(models) {
  return request({ url: `${BASE}/profile`, method: 'put', data: { models } })
}

export const MODE_LABELS = { decisive: '参与结论', reference: '仅作参考', off: '关闭' }
export const MODE_TAG = { decisive: 'success', reference: 'warning', off: 'info' }
