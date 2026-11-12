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

/** 新建仿真模型（配置结构同 pump_test_bench/config/simulation/*.json） */
export function createModel(config) {
  return request({ url: `${BASE}/models`, method: 'post', data: config })
}

/** 修改仿真模型配置；改了输入、输出后需要重建基准表 */
export function updateModel(modelId, config) {
  return request({ url: `${BASE}/models/${encodeURIComponent(modelId)}`, method: 'put', data: config })
}

/** 删除自定义模型 / 恢复内置模型的默认配置 */
export function deleteModel(modelId) {
  return request({ url: `${BASE}/models/${encodeURIComponent(modelId)}`, method: 'delete' })
}

/** 可选的测点列（试验台导出文件的表头） */
export function getColumns() {
  return request({ url: `${BASE}/columns`, method: 'get' })
}

export const ENGINE_LABELS = { surrogate: '数据代理模型', amesim: 'AMESim 模型' }
export const KIND_LABELS = { flow: '流量', pressure: '压力', temperature: '温度', torque: '扭矩', speed: '转速', other: '其他' }
export const MEANING_LABELS = {
  pump: '实际流量变化（被试泵出力，再看压力是否同步）',
  reference: '参考量偏差（如质量流量计、燃油密度）',
  input: '模型输入测点偏差'
}
