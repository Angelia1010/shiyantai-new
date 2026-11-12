<template>
  <div class="fit-result">
    <el-alert v-if="result.error" type="error" :closable="false" :title="result.error" />
    <template v-else>
      <div class="formula-line">
        <el-tag size="mini" :type="result.method === 'formula' ? 'warning' : ''">{{ METHOD_LABELS[result.method] || result.method }}</el-tag>
        <code class="formula">{{ result.display }}</code>
      </div>
      <div class="metrics">
        <div class="metric">
          <div class="muted">换油温段的误差
            <el-tooltip content="留一温度组交叉验证：用其余油温段的数据建模，预测这一段；阈值按它定" placement="top"><i class="el-icon-question" /></el-tooltip>
          </div>
          <b>{{ err(a.cv_error) }}</b>
        </div>
        <div class="metric">
          <div class="muted">用平均值的误差</div>
          <b>{{ err(a.const_error) }}</b>
        </div>
        <div class="metric">
          <div class="muted">建模数据上的误差</div>
          <b>{{ err(a.fit_error) }}</b>
        </div>
        <div class="metric">
          <div class="muted">各油温段</div>
          <span v-for="(e, g) in a.per_group" :key="g" class="group-err" :title="g">{{ shortGroup(g) }} {{ err(e) }}</span>
        </div>
      </div>
      <div v-if="fittedCoefs.length" class="coef-line">
        由数据拟合的系数：
        <span v-for="c in fittedCoefs" :key="c.name" class="coef"><code>{{ c.name }}</code> = {{ c.value }}</span>
        <el-button v-if="adoptable" type="text" size="mini" @click="$emit('adopt', result.coefficients)">采用拟合值并改为固定</el-button>
      </div>
      <div v-if="result.info && result.info.roles && result.method === 'autofit'" class="muted small">
        变量角色：<span v-for="(r, n) in result.info.roles" :key="n" class="role">{{ n }}·{{ ROLE_LABELS[r] || r }}</span>
        <span v-if="result.info.terms">；共 {{ result.info.terms }} 项</span>
      </div>
      <div v-if="result.info && result.info.note" class="muted small">{{ result.info.note }}</div>
      <el-alert v-for="(s, k) in a.suggestions" :key="k" class="note" type="warning" :closable="false" :title="s" show-icon />
      <div v-if="a.outliers && a.outliers.length" class="outliers">
        <div class="muted small">
          可疑样本（偏离其他样本较多，可能是工况不稳或数据有问题）：
          <el-tooltip content="勾选后可排除，排除的文件不参与建模与标定；是否排除由你判断" placement="top"><i class="el-icon-question" /></el-tooltip>
        </div>
        <el-checkbox-group v-if="selectable" v-model="picked" @change="$emit('pick', picked)">
          <el-checkbox v-for="o in a.outliers" :key="o.key" :label="o.key">
            {{ o.key }}（偏差 {{ err(o.residual, true) }}）
          </el-checkbox>
        </el-checkbox-group>
        <ul v-else class="small">
          <li v-for="o in a.outliers" :key="o.key">{{ o.key }}（偏差 {{ err(o.residual, true) }}）</li>
        </ul>
      </div>
      <el-row v-if="a.points && a.points.length" :gutter="12" class="charts">
        <el-col :span="12"><div ref="scatter" class="chart" /></el-col>
        <el-col :span="12">
          <div class="chart-head">
            残差随
            <el-select v-model="xVar" size="mini" style="width: 120px" @change="drawResidual">
              <el-option v-for="v in variableNames" :key="v" :label="v" :value="v" />
            </el-select>
            变化
          </div>
          <div ref="residual" class="chart short" />
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import { METHOD_LABELS, ROLE_LABELS } from '@/api/simulation'

const PALETTE = ['#2563eb', '#16a34a', '#d97706', '#dc2626', '#7c3aed', '#0891b2']

export default {
  name: 'FitResult',
  props: {
    result: { type: Object, required: true },
    adoptable: { type: Boolean, default: false },
    selectable: { type: Boolean, default: false }
  },
  data() {
    return { METHOD_LABELS, ROLE_LABELS, xVar: '', picked: [] }
  },
  computed: {
    a() {
      return this.result.assessment || {}
    },
    fittedCoefs() {
      const names = (this.result.info && this.result.info.fitted) || []
      return names.map(n => ({ name: n, value: Number(this.result.coefficients[n]).toPrecision(7) }))
    },
    variableNames() {
      const p = (this.a.points || [])[0]
      return p ? Object.keys(p.x) : []
    },
    groups() {
      return [...new Set((this.a.points || []).map(p => p.group))]
    }
  },
  watch: {
    result() {
      this.$nextTick(this.draw)
    }
  },
  mounted() {
    this.charts = []
    this.draw()
    window.addEventListener('resize', this.resize)
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.resize)
    this.charts.forEach(c => c.dispose())
  },
  methods: {
    err(v, signed = false) {
      if (v === null || v === undefined) return '—'
      const sign = signed && v > 0 ? '+' : ''
      if (this.a.mode === 'absolute') return `${sign}${Number(v).toPrecision(3)} ${this.a.unit || ''}`
      return `${sign}${(v * 100).toFixed(2)}%`
    },
    shortGroup(g) {
      const m = String(g).match(/\d+\s*-\s*\d+/)
      return m ? `${m[0]}℃` : g
    },
    chart(ref) {
      const el = this.$refs[ref]
      if (!el) return null
      let c = echarts.getInstanceByDom(el)
      if (!c) {
        c = echarts.init(el)
        this.charts.push(c)
      }
      return c
    },
    draw() {
      if (!this.a.points || !this.a.points.length) return
      if (!this.xVar || !this.variableNames.includes(this.xVar)) this.xVar = this.variableNames[0]
      const c = this.chart('scatter')
      if (c) {
        const pts = this.a.points.filter(p => p.cv !== null)
        const all = pts.flatMap(p => [p.measured, p.cv])
        const lo = Math.min(...all)
        const hi = Math.max(...all)
        c.setOption({
          title: { text: '实测 vs 模型（换油温段预测）', textStyle: { fontSize: 12, fontWeight: 'normal' } },
          grid: { left: 52, right: 12, top: 30, bottom: 30 },
          tooltip: { formatter: p => p.data[2] || '' },
          legend: { bottom: 0, itemWidth: 8, textStyle: { fontSize: 10 }, show: false },
          xAxis: { type: 'value', name: '模型', min: lo, max: hi, scale: true, nameGap: 4, splitLine: { show: false } },
          yAxis: { type: 'value', name: '实测', min: lo, max: hi, scale: true, splitLine: { lineStyle: { color: '#f0f0f0' } } },
          series: [
            { type: 'line', data: [[lo, lo], [hi, hi]], showSymbol: false, lineStyle: { color: '#cbd5e1', type: 'dashed' }, silent: true },
            ...this.groups.map((g, k) => ({
              type: 'scatter', name: g, symbolSize: 6, itemStyle: { color: PALETTE[k % PALETTE.length] },
              data: pts.filter(p => p.group === g).map(p => [p.cv, p.measured, p.key])
            }))
          ]
        }, true)
      }
      this.drawResidual()
    },
    drawResidual() {
      const c = this.chart('residual')
      if (!c || !this.xVar) return
      const rel = this.a.mode !== 'absolute'
      const pts = this.a.points.filter(p => p.cv !== null)
      c.setOption({
        grid: { left: 52, right: 12, top: 10, bottom: 30 },
        tooltip: { formatter: p => p.data[2] || '' },
        xAxis: { type: 'value', scale: true, name: this.xVar, nameGap: 4, splitLine: { show: false } },
        yAxis: { type: 'value', name: rel ? '%' : (this.a.unit || ''), splitLine: { lineStyle: { color: '#f0f0f0' } } },
        series: this.groups.map((g, k) => ({
          type: 'scatter', symbolSize: 6, itemStyle: { color: PALETTE[k % PALETTE.length] },
          data: pts.filter(p => p.group === g).map(p => {
            const r = rel ? (p.measured / p.cv - 1) * 100 : p.measured - p.cv
            return [p.x[this.xVar], r, p.key]
          })
        }))
      }, true)
    },
    resize() {
      this.charts.forEach(c => c.resize())
    }
  }
}
</script>

<style scoped>
.formula-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}
.formula {
  font-family: Menlo, Consolas, monospace;
  font-size: 12px;
  word-break: break-all;
  background: #f8fafc;
  padding: 4px 8px;
  border-radius: 4px;
  flex: 1;
}
.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-bottom: 6px;
}
.metric b {
  font-size: 15px;
}
.group-err {
  display: inline-block;
  margin-right: 8px;
  font-size: 12px;
}
.coef-line {
  font-size: 12px;
  margin-bottom: 4px;
}
.coef {
  margin-right: 10px;
}
.role {
  margin-right: 8px;
}
.note {
  margin-top: 6px;
}
.outliers {
  margin-top: 6px;
}
.charts {
  margin-top: 8px;
}
.chart {
  height: 240px;
}
.chart.short {
  height: 216px;
}
.chart-head {
  font-size: 12px;
  color: #606266;
  height: 24px;
}
.muted {
  color: #909399;
}
.small {
  font-size: 12px;
  line-height: 1.8;
}
</style>
