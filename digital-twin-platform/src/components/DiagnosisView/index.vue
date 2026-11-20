<template>
  <div :class="['diagnosis-view', { dark }]">
    <!-- 1. 结论 -->
    <div :class="['conclusion', report.result]">
      <el-tag :type="RESULT_TAG[report.result] || 'info'" size="medium" effect="dark">{{ resultLabel(report.result) }}</el-tag>
      <span class="conclusion-text">{{ headline }}</span>
      <span v-if="turbineVerdict" class="conclusion-sub">涡轮流量计复核：{{ turbineVerdict }}</span>
      <span class="conclusion-meta">
        {{ (report.condition || {}).label }}
        <template v-if="segmentText"> · {{ segmentText }}</template>
      </span>
    </div>

    <!-- 2. 管路示意图 -->
    <section class="block">
      <div class="block-head">
        <span>管路示意图</span>
        <span class="block-sub">9 个诊断信号的位置与状态，数值为稳定段均值，下方为相对正常预期的偏差</span>
      </div>
      <pipeline-schematic :curves="curves" :causes="report.causes || []" :selected="selected" @select="select" />
    </section>

    <!-- 3. 信号曲线 -->
    <section class="block">
      <div class="block-head">
        <span>信号曲线</span>
        <span class="block-sub">
          <i class="key measured"></i>实测（3 秒平均）
          <i class="key expected"></i>正常预期（模型按当时工况计算）
          <i class="key band"></i>正常范围
          <i class="key seg"></i>稳定段
        </span>
      </div>
      <div class="spark-grid">
        <signal-spark
          v-for="s in signals"
          :key="s.column"
          :signal="s"
          :time="curves.time"
          :segment="curves.segment"
          :selected="s.column === selected"
          @select="select"
        />
      </div>
      <div v-if="selectedSignal" ref="detail" class="detail-wrap">
        <signal-detail :signal="selectedSignal" :time="curves.time" :segment="curves.segment" :dark="dark" />
      </div>
    </section>

    <!-- 4. 原因 | 指纹 + 涡轮 -->
    <el-row :gutter="16" class="block-row">
      <el-col :xs="24" :md="13">
        <section class="block">
          <div class="block-head"><span>原因分析</span></div>
          <cause-list :causes="report.causes || []" :history="report.history" :dark="dark" />
        </section>
      </el-col>
      <el-col :xs="24" :md="11">
        <section v-if="prints.length" class="block">
          <div class="block-head">
            <span>偏差指纹</span>
            <span class="block-sub">各信号偏差是正常波动的多少倍，灰带内为正常波动</span>
          </div>
          <div ref="print" class="print-chart" :style="{ height: printHeight + 'px' }"></div>
          <div class="print-note">实心为实测偏差，空心为“{{ isolationText }}”应有的偏差，两者吻合说明这一解释与数据一致。</div>
        </section>
        <section v-if="turbine.length" class="block">
          <div class="block-head">
            <span>涡轮流量计二级诊断</span>
            <span class="block-sub">怀疑流量计时，用涡轮流量计模型复核叶轮转速</span>
          </div>
          <div v-for="tb in turbine" :key="tb.meter" class="turbine">
            <div class="turbine-name">{{ tb.label }}</div>
            <div class="turbine-row"><span>模型应有转速</span><b>{{ tb.expected_hz.toFixed(1) }} Hz</b></div>
            <div class="turbine-row"><span>实测转速</span><b>{{ tb.measured_hz.toFixed(1) }} Hz</b></div>
            <div class="turbine-row"><span>偏差</span><b>{{ (tb.residual * 100).toFixed(2) }}%</b></div>
            <div class="turbine-row">
              <span>“该表偏离”的可能性</span>
              <b>{{ pct(tb.probability_before) }} → {{ pct(tb.probability_after) }}</b>
            </div>
            <div class="turbine-row">
              <span>复核结论</span>
              <el-tag :type="VERDICT_TAG[tb.verdict] || 'info'" size="mini" :effect="dark ? 'dark' : 'light'">{{ tb.verdict }}</el-tag>
            </div>
          </div>
        </section>
      </el-col>
    </el-row>

    <!-- 5. 其余明细（默认折叠） -->
    <el-collapse class="block more">
      <el-collapse-item v-if="shownFindings.length" :title="`检查项明细（${shownFindings.length}）`" name="findings">
        <div v-for="(f, i) in shownFindings" :key="i" class="finding">
          <el-tag :type="SEVERITY_TAG[f.severity]" size="mini">{{ SEVERITY_LABELS[f.severity] }}</el-tag>
          <span class="finding-title">{{ f.title }}</span>
          <div class="finding-detail">{{ f.detail }}</div>
        </div>
      </el-collapse-item>
      <el-collapse-item v-if="models.length" title="仿真模型对比（稳定段均值）" name="models">
        <model-compare :models="models" :dark="dark" />
      </el-collapse-item>
      <el-collapse-item v-if="advice" title="处理建议" name="advice">
        <div class="advice">{{ advice }}</div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import { RESULT_TAG, SEVERITY_LABELS, resultLabel } from '@/utils/report'
import { PRINT_NORMAL, STATE_COLOR, defaultSignal, fingerprint, orderedSignals } from '@/utils/diagnosisCurves'
import CauseList from '@/components/CauseList'
import ModelCompare from '@/components/ModelCompare'
import PipelineSchematic from './PipelineSchematic'
import SignalSpark from './SignalSpark'
import SignalDetail from './SignalDetail'

const SEVERITY_TAG = { info: 'info', notice: 'info', warning: 'warning', abnormal: 'danger' }
const VERDICT_TAG = { 支持: 'danger', 不支持: 'success', 无明显影响: 'info' }

export default {
  name: 'DiagnosisView',
  components: { CauseList, ModelCompare, PipelineSchematic, SignalSpark, SignalDetail },
  props: {
    // 后端诊断报告（含 curves）
    report: { type: Object, required: true },
    // 暗色主题（工作台大屏）
    dark: { type: Boolean, default: false }
  },
  data() {
    return { selected: null, RESULT_TAG, SEVERITY_TAG, SEVERITY_LABELS, VERDICT_TAG }
  },
  computed: {
    curves() {
      return this.report.curves
    },
    signals() {
      return orderedSignals(this.curves)
    },
    selectedSignal() {
      return this.signals.find(s => s.column === this.selected) || null
    },
    headline() {
      const s = this.report.summary || ''
      return s.replace(/^(正常|预警|异常|无法判定)：/, '')
    },
    segmentText() {
      const seg = this.report.segment
      if (!seg) return ''
      return seg.found ? `稳定段 ${seg.start_s.toFixed(0)}–${seg.end_s.toFixed(0)} 秒` : '未识别到稳定段'
    },
    isolation() {
      const loop = (this.report.loops || []).find(l => l.active)
      return (loop && loop.isolation) || null
    },
    isolationText() {
      return (this.isolation && this.isolation.explanation) || '最可能的解释'
    },
    turbine() {
      return ((this.isolation && this.isolation.turbine) || []).filter(t => t.available)
    },
    turbineVerdict() {
      return this.turbine.map(t => `${t.label} ${t.verdict}`).join('；')
    },
    prints() {
      return fingerprint(this.curves)
    },
    printHeight() {
      return 40 + this.prints.length * 34
    },
    shownFindings() {
      return (this.report.findings || []).filter(f => f.severity !== 'info')
    },
    models() {
      return this.report.models || []
    },
    advice() {
      return this.report.repair_advice || ''
    }
  },
  watch: {
    dark() {
      this.$nextTick(this.renderPrint)
    },
    report: {
      handler() {
        this.selected = defaultSignal(this.curves)
        this.$nextTick(this.renderPrint)
      },
      immediate: true
    }
  },
  mounted() {
    this.renderPrint()
    window.addEventListener('resize', this.resize)
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.resize)
    if (this.printChart) this.printChart.dispose()
    this.printChart = null
  },
  methods: {
    resultLabel,
    pct(v) {
      return v == null ? '—' : `${Math.round(v * 100)}%`
    },
    select(column) {
      this.selected = column
      this.$nextTick(() => {
        const el = this.$refs.detail
        if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      })
    },
    resize() {
      if (this.printChart) this.printChart.resize()
    },
    renderPrint() {
      const el = this.$refs.print
      if (!el) return
      if (!this.printChart || this.printChart.getDom() !== el) {
        if (this.printChart) this.printChart.dispose()
        this.printChart = echarts.init(el)
        this.printChart.on('click', p => {
          const row = this.prints[p.dataIndex]
          if (row) this.select(row.column)
        })
      }
      const rows = this.prints
      const c = this.dark
        ? { text: '#c7d2e0', split: 'rgba(148, 163, 184, 0.12)', band: 'rgba(148, 163, 184, 0.14)', zero: '#4a5d75', dot: '#eef6ff', dotFill: '#0c1828' }
        : { text: '#606266', split: '#f0f2f5', band: 'rgba(144, 147, 153, 0.12)', zero: '#c0c4cc', dot: '#303133', dotFill: '#fff' }
      const lim = Math.max(PRINT_NORMAL * 2, ...rows.map(r => Math.abs(r.measured)), ...rows.map(r => Math.abs(r.fitted))) * 1.1
      this.printChart.setOption({
        animation: false,
        grid: { left: 72, right: 24, top: 8, bottom: 28 },
        tooltip: {
          trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: items => `${items[0].name}<br/>` + items.map(i => `${i.seriesName} ${i.value.toFixed(1)} 倍正常波动`).join('<br/>')
        },
        xAxis: {
          type: 'value', min: -lim, max: lim, splitLine: { lineStyle: { color: c.split } },
          axisLabel: { formatter: v => v.toFixed(0), color: c.text }
        },
        yAxis: { type: 'category', inverse: true, data: rows.map(r => r.label), axisTick: { show: false },
          axisLabel: { color: c.text }, axisLine: { lineStyle: { color: c.zero } } },
        series: [
          {
            name: '实测偏差', type: 'bar', barWidth: 10,
            data: rows.map(r => ({ value: r.measured, itemStyle: { color: r.state === 'normal' ? '#a0cfff' : STATE_COLOR[r.state] } })),
            markArea: { silent: true, itemStyle: { color: c.band }, data: [[{ xAxis: -PRINT_NORMAL }, { xAxis: PRINT_NORMAL }]] },
            markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: c.zero, type: 'solid' }, data: [{ xAxis: 0 }] }
          },
          {
            name: '解释应有的偏差', type: 'scatter', symbol: 'circle', symbolSize: 11,
            itemStyle: { color: c.dotFill, borderColor: c.dot, borderWidth: 1.5 },
            data: rows.map(r => r.fitted)
          }
        ]
      }, true)
      this.printChart.resize()
    }
  }
}
</script>

<style lang="scss" scoped>
/* 颜色都走变量：浅色用于自动诊断、任务记录，暗色（dark）用于工作台大屏；子组件继承这些变量 */
.diagnosis-view {
  --dv-card: #fff;
  --dv-card-solid: #fff;
  --dv-border: #ebeef5;
  --dv-text: #303133;
  --dv-text2: #606266;
  --dv-muted: #909399;
  --dv-faint: #c0c4cc;
  --dv-hover: #c6e2ff;
  --dv-band: rgba(144, 147, 153, 0.18);
  --dv-seg: rgba(64, 158, 255, 0.06);
  --dv-device: #f4f4f5;
  --dv-device-border: #909399;
  --dv-pipe: #c0c4cc;
  --dv-loop: #dcdfe6;
  --dv-abnormal-bg: #fffafa;
  --dv-warning-bg: #fdf6ec;
  --dv-danger-bg: #fef0f0;
  color: var(--dv-text);
}
.diagnosis-view.dark {
  --dv-card: rgba(255, 255, 255, 0.03);
  --dv-card-solid: #0c1828;
  --dv-border: rgba(56, 189, 248, 0.16);
  --dv-text: #eef6ff;
  --dv-text2: #c7d2e0;
  --dv-muted: #7891ad;
  --dv-faint: #4a5d75;
  --dv-hover: rgba(56, 189, 248, 0.45);
  --dv-band: rgba(148, 163, 184, 0.2);
  --dv-seg: rgba(56, 189, 248, 0.08);
  --dv-device: #13243a;
  --dv-device-border: #4a6584;
  --dv-pipe: #3b5372;
  --dv-loop: #2a3f58;
  --dv-abnormal-bg: rgba(239, 68, 68, 0.08);
  --dv-warning-bg: rgba(245, 158, 11, 0.12);
  --dv-danger-bg: rgba(239, 68, 68, 0.14);
}
.conclusion {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding: 12px 16px;
  border: 1px solid var(--dv-border);
  border-left: 4px solid #67c23a;
  background: var(--dv-card);
  margin-bottom: 12px;
}
.conclusion.warning { border-left-color: #e6a23c; }
.conclusion.abnormal { border-left-color: #f56c6c; }
.conclusion.inconclusive { border-left-color: #909399; }
.conclusion-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--dv-text);
}
.conclusion-sub {
  font-size: 13px;
  color: var(--dv-text2);
}
.conclusion-meta {
  margin-left: auto;
  font-size: 13px;
  color: var(--dv-muted);
}
.block {
  background: var(--dv-card);
  border: 1px solid var(--dv-border);
  border-radius: 4px;
  padding: 0 16px 14px;
  margin-bottom: 12px;
}
.block-head {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-weight: 600;
  padding: 12px 0 10px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--dv-border);
}
.block-sub {
  font-size: 12px;
  font-weight: 400;
  color: var(--dv-muted);
}
.key {
  display: inline-block;
  width: 16px;
  height: 8px;
  margin: 0 4px 0 10px;
  vertical-align: 0;
}
.key.measured { height: 2px; background: #409eff; vertical-align: 3px; }
.key.expected { height: 0; border-top: 1.5px dashed var(--dv-muted); vertical-align: 3px; }
.key.band { background: var(--dv-band); }
.key.seg { background: var(--dv-seg); border: 1px solid rgba(64, 158, 255, 0.3); }
.spark-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
@media (max-width: 900px) {
  .spark-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.detail-wrap {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--dv-border);
}
.print-chart {
  width: 100%;
}
.print-note {
  font-size: 12px;
  color: var(--dv-muted);
  line-height: 1.6;
}
.turbine + .turbine {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--dv-border);
}
.turbine-name {
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--dv-text);
}
.turbine-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  line-height: 1.9;
  color: var(--dv-text2);
}
.turbine-row b {
  font-weight: 500;
  color: var(--dv-text);
}
.more {
  border-top: none;
  border-bottom: none;
}
.finding {
  padding: 6px 0;
  border-bottom: 1px dashed var(--dv-border);
  font-size: 13px;
}
.finding-title {
  margin-left: 6px;
  font-weight: 600;
}
.finding-detail {
  color: var(--dv-text2);
  margin-top: 4px;
  line-height: 1.6;
}
.advice {
  white-space: pre-line;
  line-height: 1.7;
  color: var(--dv-text2);
}
.more ::v-deep .el-collapse-item__header,
.more ::v-deep .el-collapse-item__wrap {
  background: var(--dv-card);
  color: var(--dv-text);
  border-color: var(--dv-border);
}
.more ::v-deep .el-collapse-item__header {
  padding: 0 16px;
  border: 1px solid var(--dv-border);
}
.more ::v-deep .el-collapse-item__content {
  padding: 10px 16px;
  color: var(--dv-text2);
}
.more ::v-deep .el-collapse-item + .el-collapse-item .el-collapse-item__header {
  border-top: none;
}
</style>
