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

/** 后台重建某个模型的基准表：path = 正常数据目录，engine = surrogate | amesim */
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

/** 删除模型（内置模型删除后可恢复）；restore = true 时只放弃对内置模型配置的修改 */
export function deleteModel(modelId, restore = false) {
  return request({ url: `${BASE}/models/${encodeURIComponent(modelId)}`, method: 'delete', params: restore ? { restore: 1 } : {} })
}

/** 恢复已删除的内置模型 */
export function restoreBuiltinModel(modelId) {
  return request({ url: `${BASE}/models/${encodeURIComponent(modelId)}/restore`, method: 'post' })
}

/** 可选的测点列（试验台导出文件的表头） */
export function getColumns() {
  return request({ url: `${BASE}/columns`, method: 'get' })
}

export const ENGINE_LABELS = { surrogate: '数据拟合', amesim: '仿真（AMESim）' }
export const KIND_LABELS = { flow: '流量', pressure: '压力', temperature: '温度', torque: '扭矩', speed: '转速', other: '其他' }
export const MEANING_LABELS = {
  pump: '实际流量变化（被试泵出力，再看压力是否同步）',
  reference: '参考量偏差（如质量流量计、燃油密度）',
  input: '模型输入测点偏差'
}

/** 预览拟合（不保存）：config = 编辑中的模型配置，path = 正常数据目录，outputs = 只看这些输出（可省略） */
export function previewModel(config, path, outputs) {
  return request({ url: `${BASE}/preview`, method: 'post', data: { config, path, outputs }, timeout: 120000 })
}

/** 派生测点（如涡轮转速 Hz = 回油流量 × scale + offset） */
export function getDerived() {
  return request({ url: `${BASE}/derived`, method: 'get' })
}

export function saveDerived(items) {
  return request({ url: `${BASE}/derived`, method: 'put', data: { items } })
}

// 各输出的计算方式：页面上新建只能“数据拟合”；内置模型的公式写在后端配置文件中，页面上不显示
export const METHOD_LABELS = { autofit: '数据拟合', formula: '内置模型' }
export const ROLE_LABELS = { auto: '自动', main: '主变量', secondary: '次变量', environment: '环境变量', off: '不使用' }
