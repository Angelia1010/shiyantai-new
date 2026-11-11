/**
 * 试验数据特征计算。
 *
 * 文件服务返回的一页数据形如 { columns: { 列名: [值, ...] } }。
 * 这里把每 groupSize 行聚合成一个“特征帧” { 列名: { max, min, avg } }，
 * 工作台（Dashboard）按帧播放，诊断流程用帧的 avg 作为试验数据。
 */

// 工作台展示和诊断关心的试验台测点
export const MONITORED_FIELDS = [
  '燃油泵实际转速', '电传实际转速', '电传扭矩',
  'P1进口压力', 'P17滑油压力', 'P18回油工况模拟供油压力', 'P2低压出口压力', 'P3高压出口压力',
  '供油压力1-1', '供油压力1-2',
  '回油压力1-1', '回油压力1-2', '回油压力2-1', '回油压力2-2',
  '回油流量1-1', '回油流量1-2', '回油流量2-1', '回油流量2-2',
  '供油流量1-1', '供油流量1-2',
  'T20加热出口温度', 'T3进口温度', 'T4高压出口温度', 'T5出口温度',
  '供油温度1-1', '供油温度1-2',
  '回油温度1-1', '回油温度1-2', '回油温度2-1', '回油温度2-2',
  '振动传感器1-1', '振动传感器2-1', '振动传感器3-1'
]

function toNumbers(values) {
  const result = []
  for (const v of values) {
    if (v === null || v === undefined || v === '' || v === 'nan') continue
    const n = Number(v)
    if (!Number.isNaN(n)) result.push(n)
  }
  return result
}

/** 选出要计算的列：优先用约定测点，一个都没有时退回到全部数值列。 */
export function pickFields(columns) {
  const names = Object.keys(columns || {})
  const monitored = MONITORED_FIELDS.filter(f => names.includes(f))
  if (monitored.length) return monitored
  return names.filter(name => toNumbers(columns[name].slice(0, 50)).length > 0)
}

/** 把一页数据切成若干特征帧。 */
export function buildFeatureFrames(columns, fields, groupSize) {
  const size = Math.max(1, groupSize | 0)
  const length = Math.max(0, ...fields.map(f => (columns[f] || []).length))
  const frames = []
  for (let start = 0; start < length; start += size) {
    const frame = {}
    for (const field of fields) {
      const group = toNumbers((columns[field] || []).slice(start, start + size))
      if (!group.length) continue
      let max = -Infinity
      let min = Infinity
      let sum = 0
      for (const v of group) {
        if (v > max) max = v
        if (v < min) min = v
        sum += v
      }
      frame[field] = { max, min, avg: sum / group.length }
    }
    if (Object.keys(frame).length) frames.push(frame)
  }
  return frames
}

/** 特征帧 → 每个变量的 avg 序列 { 变量: [avg, ...] }，用于初步诊断。 */
export function framesToSeries(frames) {
  const series = {}
  for (const frame of frames) {
    for (const [name, stat] of Object.entries(frame)) {
      (series[name] = series[name] || []).push(stat.avg)
    }
  }
  return series
}

export function mean(values) {
  const nums = toNumbers(values || [])
  return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null
}
