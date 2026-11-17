<template>
  <div class="detail">
    <div class="detail-head">
      <div>
        <span class="detail-name">{{ signal.label }}</span>
        <span class="detail-pos">{{ signal.position }}</span>
        <el-tag :type="TAG[state]" size="mini" effect="plain">{{ STATE_TEXT[state] }}</el-tag>
      </div>
      <div class="detail-compare">{{ compareText }}</div>
    </div>
    <div v-if="signal.findings && signal.findings.length" class="detail-findings">
      <i class="el-icon-warning-outline"></i> {{ signal.findings.join('；') }}
    </div>
    <div ref="chart" :class="['detail-chart', { single: !hasExpected }]"></div>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import {
  STATE_COLOR, STATE_TEXT, deviationLimits, deviationSeries, deviationText, digits, fmt, limitText,
  signalState, valueRange
} from '@/utils/diagnosisCurves'

const TAG = { abnormal: 'danger', warning: 'warning', affected: 'warning', unusable: 'info', normal: 'success' }

export default {
  name: 'SignalDetail',
  props: {
    signal: { type: Object, required: true },
    time: { type: Array, required: true },
    segment: { type: Array, default: null }
  },
  data() {
    return { TAG, STATE_TEXT }
  },
  computed: {
    state() {
      return signalState(this.signal)
    },
    hasExpected() {
      return !!this.signal.expected
    },
    compareText() {
      const s = this.signal
      if (!this.hasExpected) {
        return s.setpoints ? `工况输入，设定档位 ${s.setpoints.join(' / ')} ${s.unit}` : '工况输入（模型按它计算其余信号的正常预期）'
      }
      if (s.expected_mean == null) return `正常范围 ${limitText(s, s.warn)}（该信号自检不可用，未参与对比）`
      return `稳定段 实测 ${fmt(s.mean, s)} / 正常预期 ${fmt(s.expected_mean, s)} ${s.unit}，偏差 ${deviationText(s)}` +
        `（预警 ${limitText(s, s.warn)}，异常 ${limitText(s, s.alarm)}）`
    }
  },
  watch: {
    signal() {
      this.$nextTick(this.render)
    }
  },
  mounted() {
    this.chart = echarts.init(this.$refs.chart)
    this.render()
    window.addEventListener('resize', this.resize)
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.resize)
    if (this.chart) this.chart.dispose()
    this.chart = null
  },
  methods: {
    resize() {
      if (this.chart) this.chart.resize()
    },
    render() {
      if (!this.chart) return
      this.chart.resize()
      const s = this.signal
      const t = this.time
      const color = this.state === 'abnormal' || this.state === 'warning' ? STATE_COLOR[this.state] : '#409eff'
      const d = digits(s)
      const [lo, hi] = valueRange(s)
      const pair = arr => arr.map((v, i) => [t[i], v])
      const two = this.hasExpected
      const grids = two
        ? [{ left: 64, right: 24, top: 36, height: '52%' }, { left: 64, right: 24, top: '72%', bottom: 36 }]
        : [{ left: 64, right: 24, top: 36, bottom: 36 }]
      const xAxis = grids.map((g, i) => ({
        type: 'value', gridIndex: i, min: t[0], max: t[t.length - 1],
        name: i === grids.length - 1 ? '时间（秒）' : '', nameLocation: 'middle', nameGap: 24,
        axisLabel: { show: i === grids.length - 1, formatter: v => Math.round(v) },
        splitLine: { show: false }
      }))
      const yAxis = [{
        type: 'value', gridIndex: 0, min: lo, max: hi, name: s.unit, nameTextStyle: { align: 'right' },
        axisLabel: { formatter: v => v.toFixed(d) }, splitLine: { lineStyle: { color: '#f0f2f5' } }
      }]
      const series = []
      const segArea = this.segment ? {
        silent: true, itemStyle: { color: 'rgba(64, 158, 255, 0.06)' },
        label: { show: true, position: 'insideTop', color: '#909399', fontSize: 11, formatter: '稳定段（判定用）' },
        data: [[{ xAxis: this.segment[0] }, { xAxis: this.segment[1] }]]
      } : null

      if (two) {
        const band = s.band_low.map((v, i) => (v == null || s.band_high[i] == null ? null : s.band_high[i] - v))
        series.push(
          { name: '正常范围下限', type: 'line', data: pair(s.band_low), stack: 'band', symbol: 'none',
            lineStyle: { opacity: 0 }, tooltip: { show: false }, silent: true },
          { name: '正常范围', type: 'line', data: pair(band), stack: 'band', symbol: 'none',
            lineStyle: { opacity: 0 }, areaStyle: { color: 'rgba(144, 147, 153, 0.18)' }, silent: true },
          { name: '正常预期', type: 'line', data: pair(s.expected), symbol: 'none',
            lineStyle: { color: '#909399', type: 'dashed', width: 1.5 }, itemStyle: { color: '#909399' } }
        )
      }
      if (s.raw) {
        series.push({ name: '未平均读数', type: 'line', data: pair(s.raw), symbol: 'none',
          lineStyle: { color: '#c0c4cc', width: 1 }, itemStyle: { color: '#c0c4cc' }, z: 1 })
      }
      const measured = { name: '实测', type: 'line', data: pair(s.values), symbol: 'none', z: 3,
        lineStyle: { color, width: 2 }, itemStyle: { color }, markArea: segArea || undefined }
      if (this.segment && s.mean != null) {
        measured.markLine = { silent: true, symbol: 'none', lineStyle: { color, type: 'solid', width: 1, opacity: 0.7 },
          label: { formatter: `稳定段均值 ${fmt(s.mean, s)}`, color, fontSize: 11, position: 'insideEndTop' },
          data: [[{ coord: [this.segment[0], s.mean] }, { coord: [this.segment[1], s.mean] }]] }
      }
      if (!two && s.setpoints) {
        series.push({ name: '设定档位', type: 'line', data: [], silent: true,
          markLine: { silent: true, symbol: 'none', lineStyle: { color: '#c0c4cc', type: 'dotted' },
            label: { formatter: p => `设定 ${p.value}`, color: '#909399', fontSize: 11 },
            data: s.setpoints.filter(v => v >= lo && v <= hi).map(v => ({ yAxis: v })) } })
      }
      series.push(measured)

      if (two) {
        const dev = deviationSeries(s)
        const lim = deviationLimits(s)
        const absMax = Math.max(lim.alarm * 1.15, ...dev.filter(v => v != null).map(Math.abs))
        yAxis.push({
          type: 'value', gridIndex: 1, min: -absMax, max: absMax, name: `偏差 ${lim.unit}`,
          nameTextStyle: { align: 'right' }, splitNumber: 2,
          axisLabel: { formatter: v => v.toFixed(lim.unit === '%' ? 1 : d) }, splitLine: { show: false }
        })
        const mk = (v, c, label) => ({ yAxis: v, lineStyle: { color: c }, label: { formatter: label, color: c, fontSize: 11 } })
        series.push({
          name: '偏差', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: pair(dev), symbol: 'none',
          lineStyle: { color, width: 1.5 }, itemStyle: { color },
          areaStyle: { color: this.state === 'normal' ? 'rgba(64, 158, 255, 0.08)' : 'rgba(245, 108, 108, 0.12)', origin: 0 },
          markLine: { silent: true, symbol: 'none', lineStyle: { type: 'dashed' }, data: [
            mk(lim.warn, '#e6a23c', '预警'), mk(-lim.warn, '#e6a23c', ''),
            mk(lim.alarm, '#f56c6c', '异常'), mk(-lim.alarm, '#f56c6c', ''),
            { yAxis: 0, lineStyle: { color: '#c0c4cc', type: 'solid' }, label: { show: false } }
          ] }
        })
      }

      this.chart.setOption({
        animation: false,
        legend: { top: 4, right: 24, itemWidth: 18, textStyle: { fontSize: 12 },
          data: (two ? ['实测', '正常预期', '正常范围'] : ['实测']).concat(s.raw ? ['未平均读数'] : []),
          selected: { 未平均读数: false } },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'line', link: [{ xAxisIndex: 'all' }] },
          formatter: items => this.tooltip(items)
        },
        axisPointer: { link: [{ xAxisIndex: 'all' }] },
        grid: grids,
        xAxis,
        yAxis,
        series
      }, true)
    },
    tooltip(items) {
      if (!items.length) return ''
      const s = this.signal
      const i = items[0].dataIndex
      const rows = [`${this.time[i].toFixed(1)} 秒`, `实测（3 秒平均） ${fmt(s.values[i], s)} ${s.unit}`]
      if (s.raw) rows.push(`未平均读数 ${fmt(s.raw[i], s)}`)
      if (s.expected) {
        rows.push(`正常预期 ${fmt(s.expected[i], s)} ${s.unit}`)
        rows.push(`正常范围 ${fmt(s.band_low[i], s)} – ${fmt(s.band_high[i], s)}`)
        const dev = deviationSeries(s)[i]
        if (dev != null) rows.push(`偏差 ${dev >= 0 ? '+' : ''}${dev.toFixed(s.mode === 'absolute' ? digits(s) : 2)}${s.mode === 'absolute' ? ' ' + s.unit : '%'}`)
      }
      return rows.join('<br/>')
    }
  }
}
</script>

<style scoped>
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.detail-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-right: 8px;
}
.detail-pos {
  font-size: 12px;
  color: #909399;
  margin-right: 8px;
}
.detail-compare {
  font-size: 13px;
  color: #606266;
}
.detail-findings {
  margin-top: 6px;
  font-size: 13px;
  color: #f56c6c;
}
.detail-chart {
  width: 100%;
  height: 360px;
  margin-top: 8px;
}
.detail-chart.single {
  height: 260px;
}
</style>
