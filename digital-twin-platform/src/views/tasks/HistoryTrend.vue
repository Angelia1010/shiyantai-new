<template>
  <div class="history-trend">
    <div class="toolbar">
      <el-radio-group v-model="view" size="small" @change="render">
        <el-radio-button label="meters">流量计偏差</el-radio-button>
        <el-radio-button label="balance">供回油平衡</el-radio-button>
        <el-radio-button label="mass">质量计 vs 流量</el-radio-button>
      </el-radio-group>
      <div class="filters">
        <el-select v-model="source" size="small" style="width: 170px" @change="load">
          <el-option label="试验台实时 / 自动诊断" value="live" />
          <el-option label="手动选择的文件" value="file" />
          <el-option label="全部" value="all" />
        </el-select>
        <el-select v-model="days" size="small" style="width: 110px" @change="load">
          <el-option label="近 30 天" :value="30" />
          <el-option label="近 90 天" :value="90" />
          <el-option label="近 1 年" :value="365" />
        </el-select>
      </div>
    </div>
    <div class="hint">{{ hint }}</div>
    <div v-show="items.length" ref="chart" class="chart" />
    <el-empty v-if="!loading && !items.length" description="这段时间没有诊断记录" :image-size="90" />
  </div>
</template>

<script>
import * as echarts from 'echarts'
import { getDiagnosisHistory } from '@/api/tasks'
import { resultLabel } from '@/utils/report'

// 判定阈值（扣除固有偏差后）：有健康基准时的下限，见 pump_test_bench/config/bench.json
const WARN = 1.5
const ALARM = 2.5
const PALETTE = ['#2563eb', '#0891b2', '#7c3aed', '#db2777', '#ea580c', '#65a30d']
const GREY = '#9ca3af'

const HINTS = {
  meters: '每只流量计扣除固有偏差后、相对其余流量计的偏差。单次超过 ±1.5% 预警、±2.5% 异常；一条线持续往一个方向走，就是长期漂移。',
  balance: '供油流量比回油流量多出的百分比（扣除固有偏差）。持续为正且变大：缓慢发展的泄漏；为负：回油侧多计（夹气等）。',
  mass: '质量流量计换算成体积后与体积流量计的偏差，按流量画。点沿“小流量偏差大、大流量偏差小”的曲线分布是零点漂移；各流量偏差差不多是标定漂移。'
}

function fmtTime(ms) {
  const d = new Date(ms)
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function refLines(values) {
  return {
    silent: true,
    symbol: 'none',
    lineStyle: { color: GREY, type: 'dashed', width: 1 },
    label: { color: '#6b7280', fontSize: 11, formatter: '{b}' },
    data: values.map(([v, name]) => ({ yAxis: v, name }))
  }
}

export default {
  name: 'HistoryTrend',
  data() {
    return { view: 'meters', source: 'live', days: 90, items: [], loading: false }
  },
  computed: {
    hint() {
      const n = this.items.length
      return n ? `共 ${n} 次诊断。${HINTS[this.view]}` : ''
    }
  },
  mounted() {
    this.chart = echarts.init(this.$refs.chart)
    window.addEventListener('resize', this.resize)
    this.load()
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.resize)
    if (this.chart) this.chart.dispose()
  },
  methods: {
    resize() {
      if (this.chart) this.chart.resize()
    },
    async load() {
      this.loading = true
      try {
        const res = await getDiagnosisHistory(this.days, this.source)
        this.items = res.items || []
      } finally {
        this.loading = false
      }
      this.$nextTick(() => {
        this.resize()
        this.render()
      })
    },
    tooltipHead(it) {
      return `${fmtTime(it.time)}　${it.file_name}<br/>流量 ${it.flow ? it.flow.toFixed(0) : '—'} L/h　` +
        `油温 ${it.temperature != null ? it.temperature : '—'} ℃　结论：${resultLabel(it.result)}`
    },
    render() {
      if (!this.chart || !this.items.length) return
      const option = this.view === 'mass' ? this.massOption() : this.timeOption()
      this.chart.setOption(option, true)
    },
    timeOption() {
      const items = this.items
      const x = items.map(it => fmtTime(it.time))
      let series
      if (this.view === 'meters') {
        const cols = [...new Set(items.flatMap(it => Object.keys(it.meters || {})))]
        series = cols.map((col, i) => ({
          name: (((items.find(it => it.labels && it.labels[col]) || {}).labels) || {})[col] || col,
          type: 'line',
          showSymbol: items.length < 60,
          symbolSize: 5,
          connectNulls: true,
          lineStyle: { width: 1.6 },
          color: PALETTE[i % PALETTE.length],
          data: items.map(it => (it.meters && it.meters[col] != null ? +(it.meters[col] * 100).toFixed(3) : null)),
          markLine: i === 0 ? refLines([[WARN, '预警'], [-WARN, '预警'], [ALARM, '异常'], [-ALARM, '异常']]) : undefined
        }))
      } else {
        series = [{
          name: '供油 − 回油',
          type: 'line',
          showSymbol: items.length < 60,
          symbolSize: 5,
          connectNulls: true,
          color: PALETTE[0],
          data: items.map(it => (it.balance != null ? +(it.balance * 100).toFixed(3) : null)),
          markLine: refLines([[1.5, '预警'], [-1.5, '预警'], [3, '异常'], [-3, '异常']])
        }]
      }
      return {
        grid: { left: 56, right: 70, top: 40, bottom: 56 },
        legend: { top: 0, textStyle: { color: '#4b5563' } },
        tooltip: {
          trigger: 'axis',
          formatter: params => {
            const it = items[params[0].dataIndex]
            return this.tooltipHead(it) + '<br/>' + params
              .filter(p => p.value != null)
              .map(p => `${p.marker}${p.seriesName}：${p.value > 0 ? '+' : ''}${p.value.toFixed(2)}%`).join('<br/>')
          }
        },
        dataZoom: items.length > 40 ? [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 8 }] : [],
        xAxis: { type: 'category', data: x, axisLabel: { color: '#6b7280', fontSize: 11 }, axisLine: { lineStyle: { color: '#d1d5db' } } },
        yAxis: {
          type: 'value',
          name: '偏差（%）',
          nameTextStyle: { color: '#6b7280' },
          axisLabel: { color: '#6b7280', formatter: v => `${v > 0 ? '+' : ''}${v}` },
          splitLine: { lineStyle: { color: '#f0f0f0' } }
        },
        series
      }
    },
    massOption() {
      const pts = this.items.filter(it => it.mass && it.mass.deviation != null && it.flow)
      const data = pts.map(it => ({ value: [+it.flow.toFixed(1), +(it.mass.deviation * 100).toFixed(3)], it }))
      return {
        grid: { left: 56, right: 70, top: 30, bottom: 50 },
        tooltip: {
          trigger: 'item',
          formatter: p => `${this.tooltipHead(p.data.it)}<br/>质量-体积偏差：${p.value[1] > 0 ? '+' : ''}${p.value[1].toFixed(2)}%`
        },
        xAxis: {
          type: 'value', name: '流量（L/h）', nameLocation: 'middle', nameGap: 28, scale: true,
          nameTextStyle: { color: '#6b7280' }, axisLabel: { color: '#6b7280' }, splitLine: { show: false }
        },
        yAxis: {
          type: 'value', name: '偏差（%）', nameTextStyle: { color: '#6b7280' },
          axisLabel: { color: '#6b7280', formatter: v => `${v > 0 ? '+' : ''}${v}` },
          splitLine: { lineStyle: { color: '#f0f0f0' } }
        },
        series: [{
          type: 'scatter',
          symbolSize: 8,
          // 最近的点用强调色，较早的点灰色，看得出变化方向
          itemStyle: { color: p => (p.dataIndex >= data.length - 5 ? PALETTE[0] : GREY), opacity: 0.85 },
          data,
          markLine: refLines([[1.5, '预警'], [-1.5, '预警'], [3, '异常'], [-3, '异常']])
        }]
      }
    }
  }
}
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.filters {
  display: flex;
  gap: 8px;
}
.hint {
  margin: 10px 0 4px;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.6;
}
.chart {
  width: 100%;
  height: 420px;
}
</style>
