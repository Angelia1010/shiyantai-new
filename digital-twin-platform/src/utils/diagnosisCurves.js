/**
 * 诊断结果页的信号曲线与管路示意图用到的纯函数（不依赖 Vue / ECharts，便于单独测试）。
 *
 * 数据来自诊断报告的 curves（后端 pump_test_bench/app/diagnosis/series.py）：
 *   { time: [秒], segment: [起, 止] | null,
 *     signals: [{ column, key, label, unit, kind, severity, usable, affected, mean, values,
 *                 mode, expected, band_low, band_high, warn, alarm, residual, setpoints, fingerprint }] }
 */

/** 管路示意图上各信号的位置：沿主油路从左到右（增压泵 → 被试泵 → 油箱），电传转速画在被试泵上方 */
export const SCHEMATIC_ORDER = [
  'control_pressure', 'supply_temperature', 'supply_flow', 'inlet_pressure',
  'speed', 'outlet_pressure', 'return_temperature', 'return_flow', 'back_pressure'
]

export const SHORT_NAMES = {
  control_pressure: 'P9 控制腔',
  supply_temperature: '供油温度',
  supply_flow: '供油流量',
  inlet_pressure: 'P1 进口',
  speed: '电传转速',
  outlet_pressure: 'P5 低压',
  return_temperature: '回油温度',
  return_flow: '回油流量',
  back_pressure: 'P6 定压'
}

/** 信号状态：abnormal / warning / affected（受故障影响但本身不是故障点）/ unusable / normal */
export function signalState(s) {
  if (!s) return 'normal'
  if (s.severity === 'abnormal') return 'abnormal'
  if (s.severity === 'warning') return 'warning'
  if (!s.usable) return 'unusable'
  if (s.affected) return 'affected'
  return 'normal'
}

export const STATE_TEXT = {
  abnormal: '异常', warning: '预警', affected: '受影响', unusable: '不可用', normal: '正常'
}

export const STATE_COLOR = {
  abnormal: '#f56c6c', warning: '#e6a23c', affected: '#d4880f', unusable: '#909399', normal: '#67c23a'
}

/** 测量值的显示位数 */
export function digits(s) {
  if (s.unit === 'MPa') return 3
  if (s.unit === 'rpm') return 0
  return 1
}

export function fmt(v, s) {
  return v == null || !Number.isFinite(v) ? '—' : v.toFixed(digits(s))
}

/** 稳定段偏差的文字：相对值显示百分比，绝对值带单位 */
export function deviationText(s, value = s.residual) {
  if (value == null || !Number.isFinite(value)) return ''
  // 先按显示位数取整再定符号，避免出现 “-0.0”
  if (s.mode === 'absolute') {
    const v = Number(value.toFixed(s.unit === 'MPa' ? 3 : 1))
    return `${v >= 0 ? '+' : ''}${v.toFixed(s.unit === 'MPa' ? 3 : 1)} ${s.unit}`
  }
  const v = Number((value * 100).toFixed(1))
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

export function limitText(s, value) {
  if (value == null) return ''
  return s.mode === 'absolute' ? `±${value.toFixed(s.unit === 'MPa' ? 3 : 1)} ${s.unit}` : `±${(value * 100).toFixed(1)}%`
}

/** 每个时刻实测相对正常预期的偏差（相对值 → %，绝对值 → 原单位） */
export function deviationSeries(s) {
  if (!s.expected) return []
  return s.values.map((v, i) => {
    const e = s.expected[i]
    if (v == null || e == null) return null
    return s.mode === 'absolute' ? v - e : (v / e - 1) * 100
  })
}

/** 偏差图上的预警 / 异常线（与 deviationSeries 同单位） */
export function deviationLimits(s) {
  if (s.warn == null) return null
  const k = s.mode === 'absolute' ? 1 : 100
  return { warn: s.warn * k, alarm: s.alarm * k, unit: s.mode === 'absolute' ? s.unit : '%' }
}

function finite(list) {
  return list.filter(v => v != null && Number.isFinite(v))
}

/** 纵轴的最小跨度：读数几乎不变时不把微小波动放大成“大起大落” */
const MIN_SPAN = { MPa: 0.01, '℃': 2, rpm: 50, 'L/h': 5 }

/** 纵轴范围：包住实测、正常范围，留 8% 边距；全平时按量级给一个最小跨度 */
export function valueRange(s) {
  const all = finite([].concat(s.values, s.band_low || [], s.band_high || []))
  if (!all.length) return [0, 1]
  let lo = Math.min(...all)
  let hi = Math.max(...all)
  const minSpan = Math.max(Math.abs(hi) * 0.02, MIN_SPAN[s.unit] || 0.5)
  if (hi - lo < minSpan) {
    const mid = (hi + lo) / 2
    lo = mid - minSpan / 2
    hi = mid + minSpan / 2
  }
  const pad = (hi - lo) * 0.08
  return [lo - pad, hi + pad]
}

/**
 * 小图（迷你曲线）的 SVG 路径。
 * 返回 { measured, expected, band, segment: {x, w} | null }，坐标在 0..w × 0..h 内。
 */
export function sparkPaths(s, time, segment, w, h) {
  const n = s.values.length
  if (!n) return { measured: '', expected: '', band: '', segment: null }
  const t0 = time[0]
  const t1 = time[n - 1] > t0 ? time[n - 1] : t0 + 1
  const [lo, hi] = valueRange(s)
  const x = i => ((time[i] - t0) / (t1 - t0)) * w
  const y = v => h - ((v - lo) / (hi - lo)) * h
  const line = arr => {
    let d = ''
    let pen = false
    arr.forEach((v, i) => {
      if (v == null || !Number.isFinite(v)) {
        pen = false
        return
      }
      d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`
      pen = true
    })
    return d
  }
  let band = ''
  if (s.band_low && s.band_high) {
    const idx = s.band_low.map((v, i) => i).filter(i => s.band_low[i] != null && s.band_high[i] != null)
    if (idx.length > 1) {
      band = idx.map((i, k) => `${k ? 'L' : 'M'}${x(i).toFixed(1)} ${y(s.band_high[i]).toFixed(1)}`).join('') +
        idx.slice().reverse().map(i => `L${x(i).toFixed(1)} ${y(s.band_low[i]).toFixed(1)}`).join('') + 'Z'
    }
  }
  let seg = null
  if (segment && (segment[0] > t0 + 0.01 || segment[1] < t1 - 0.01)) {
    const a = Math.max(0, ((segment[0] - t0) / (t1 - t0)) * w)
    const b = Math.min(w, ((segment[1] - t0) / (t1 - t0)) * w)
    seg = { x: a, w: Math.max(0, b - a) }
  }
  return { measured: line(s.values), expected: s.expected ? line(s.expected) : '', band, segment: seg }
}

/** 按示意图顺序排列信号（报告里没有的信号跳过） */
export function orderedSignals(curves) {
  const list = (curves && curves.signals) || []
  const byKey = {}
  list.forEach(s => { byKey[s.key] = s })
  const ordered = SCHEMATIC_ORDER.map(k => byKey[k]).filter(Boolean)
  return ordered.concat(list.filter(s => !SCHEMATIC_ORDER.includes(s.key)))
}

/** 默认展开的信号：最严重的那个（都正常时取第一个有模型预期的） */
export function defaultSignal(curves) {
  const list = orderedSignals(curves)
  const rank = { abnormal: 4, warning: 3, affected: 2, unusable: 1, normal: 0 }
  let best = null
  list.forEach(s => {
    if (!best || rank[signalState(s)] > rank[signalState(best)]) best = s
  })
  if (best && signalState(best) === 'normal') best = list.find(s => s.expected) || best
  return best ? best.column : null
}

/** 偏差指纹的正常波动范围（± 倍数） */
export const PRINT_NORMAL = 2

/**
 * 偏差指纹：参与故障隔离的信号，实测偏差与“最可能的解释”应有的偏差，都除以该信号健康时的正常波动 σ
 * （±PRINT_NORMAL 以内算正常波动）。故障隔离是把各信号放在一起判断的，单个信号偏差不大也能构成明确的指纹；
 * 不同故障在各信号上的偏差组合不同，对照指纹即可看出为什么判为这种故障。
 * 返回 [{ label, column, measured, fitted, state }]
 */
export function fingerprint(curves) {
  return orderedSignals(curves)
    .filter(s => s.fingerprint && s.fingerprint.sigma)
    .map(s => ({
      label: SHORT_NAMES[s.key] || s.label,
      column: s.column,
      measured: s.fingerprint.value / s.fingerprint.sigma,
      fitted: s.fingerprint.fitted / s.fingerprint.sigma,
      state: signalState(s)
    }))
}
