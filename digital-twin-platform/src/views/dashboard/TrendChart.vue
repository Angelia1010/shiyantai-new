<template>
  <div ref="chart" class="trend-chart" />
</template>

<script>
import * as echarts from 'echarts'

const PALETTE = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#06b6d4']

export default {
  name: 'TrendChart',
  props: {
    // [{ name, data: [数值] }]
    series: { type: Array, default: () => [] },
    unit: { type: String, default: '' }
  },
  watch: {
    series() {
      this.render()
    }
  },
  mounted() {
    this.chart = echarts.init(this.$refs.chart)
    this.render()
    this.resizeObserver = new ResizeObserver(() => this.chart && this.chart.resize())
    this.resizeObserver.observe(this.$refs.chart)
  },
  beforeDestroy() {
    this.resizeObserver.disconnect()
    this.chart.dispose()
    this.chart = null
  },
  methods: {
    render() {
      if (!this.chart) return
      const length = Math.max(0, ...this.series.map(s => s.data.length))
      this.chart.setOption({
        color: PALETTE,
        animation: false,
        grid: { left: 48, right: 16, top: 30, bottom: 24 },
        legend: { top: 0, right: 8, textStyle: { color: '#9fb0c6', fontSize: 11 }, itemWidth: 14, itemHeight: 2 },
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(8,13,22,0.92)',
          borderColor: 'rgba(120,150,190,0.3)',
          textStyle: { color: '#e6edf6', fontSize: 12 },
          valueFormatter: v => (typeof v === 'number' ? `${v.toPrecision(4)} ${this.unit}` : v)
        },
        xAxis: {
          type: 'category',
          data: Array.from({ length }, (_, i) => i - length + 1),
          axisLine: { lineStyle: { color: '#2a3a52' } },
          axisLabel: { color: '#6b7a90', fontSize: 10 },
          axisTick: { show: false }
        },
        yAxis: {
          type: 'value',
          scale: true,
          name: this.unit,
          nameTextStyle: { color: '#6b7a90', fontSize: 10 },
          axisLabel: { color: '#6b7a90', fontSize: 10 },
          splitLine: { lineStyle: { color: 'rgba(120,150,190,0.1)' } }
        },
        series: this.series.map(s => ({
          name: s.name,
          type: 'line',
          data: s.data,
          showSymbol: false,
          smooth: true,
          lineStyle: { width: 1.6 }
        }))
      }, true)
    }
  }
}
</script>

<style scoped>
.trend-chart {
  width: 100%;
  height: 100%;
}
</style>
