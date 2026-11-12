<template>
  <el-card class="result-display-card" shadow="hover">
    <div slot="header" class="card-header">
      <span>诊断结果</span>
      <div class="header-actions">
        <el-button 
          type="primary" 
          size="small" 
          icon="el-icon-download"
          @click="$emit('download-report', diagnosisResult && diagnosisResult.taskId)"
          :disabled="!diagnosisResult"
        >
          下载报告
        </el-button>
        <el-button 
          type="success" 
          size="small" 
          icon="el-icon-refresh"
          @click="$emit('restart')"
        >
          重新诊断
        </el-button>
      </div>
    </div>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card shadow="never" class="result-info-card">
          <div slot="header">诊断信息</div>
          
          <div v-if="diagnosisResult" class="result-content">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="诊断状态">
                <el-tag :type="statusTagType" size="small">
                  {{ diagnosisResult.statusText }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="诊断时间">
                {{ diagnosisResult.timestamp }}
              </el-descriptions-item>
              <el-descriptions-item label="任务ID">
                {{ diagnosisResult.taskId }}
              </el-descriptions-item>
              <el-descriptions-item v-if="diagnosisResult.condition && diagnosisResult.condition.label" label="试验工况">
                {{ diagnosisResult.condition.label }}
              </el-descriptions-item>
              <el-descriptions-item v-if="diagnosisResult.summary" label="结论">
                {{ diagnosisResult.summary }}
              </el-descriptions-item>
            </el-descriptions>

            <div class="diagnosis-section">
              <h4>原因分析</h4>
              <cause-list :causes="diagnosisResult.causes || []" :history="diagnosisResult.history" />
            </div>

            <div v-if="shownFindings.length" class="diagnosis-section">
              <el-collapse>
                <el-collapse-item :title="`检查项明细（${shownFindings.length}）`">
                  <div v-for="(f, i) in shownFindings" :key="i" :class="['finding', f.severity]">
                    <el-tag :type="SEVERITY_TAG[f.severity]" size="mini">{{ SEVERITY_LABELS[f.severity] }}</el-tag>
                    <span class="finding-title">{{ f.title }}</span>
                    <div class="finding-detail">{{ f.detail }}</div>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>

            <div v-if="diagnosisResult.repairAdvice" class="repair-section">
              <h4>处理建议</h4>
              <el-card shadow="never" class="advice-card">
                {{ diagnosisResult.repairAdvice }}
              </el-card>
            </div>
          </div>

          <el-empty v-else description="暂无诊断结果" :image-size="100" />
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="never" class="chart-card">
          <div slot="header">
            <span>实测曲线与模型预期</span>
            <div class="chart-controls">
              <el-select 
                v-model="selectedField" 
                size="small" 
                placeholder="选择数据字段"
                @change="updateChart"
              >
                <el-option
                  v-for="field in fields"
                  :key="field"
                  :label="field"
                  :value="field"
                />
              </el-select>
            </div>
          </div>
          <div ref="chartContainer" class="chart-container"></div>
        </el-card>

        <el-card shadow="never" class="indicators-card" v-if="diagnosisResult && diagnosisResult.model">
          <div slot="header">仿真模型对比</div>
          <model-compare :model="diagnosisResult.model" />
        </el-card>

        <el-card shadow="never" class="indicators-card" v-if="diagnosisResult && diagnosisResult.indicators.length">
          <div slot="header">检测明细</div>
          <el-table :data="diagnosisResult.indicators" border size="small" max-height="200">
            <el-table-column prop="name" label="项目" min-width="150" />
            <el-table-column prop="reference" label="判定标准 / 来源" width="150" />
            <el-table-column prop="value" label="结果" min-width="140">
              <template slot-scope="scope">
                <span :class="{'abnormal-value': scope.row.abnormal}">
                  {{ scope.row.value }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <div class="action-bar">
      <el-button size="medium" @click="$emit('prev')">
        <i class="el-icon-arrow-left"></i>
        上一步
      </el-button>
    </div>
  </el-card>
</template>

<script>
import * as echarts from 'echarts'
import { RESULT_TAG, SEVERITY_LABELS } from '@/utils/report'
import CauseList from '@/components/CauseList'
import ModelCompare from '@/components/ModelCompare'

const SEVERITY_TAG = { info: 'info', notice: 'info', warning: 'warning', abnormal: 'danger' }

export default {
  name: 'ResultDisplayStep',
  components: { CauseList, ModelCompare },
  props: {
    // utils/report.js summarizeReport() 的结果
    diagnosisResult: { type: Object, default: null },
    // { 变量: [每组均值] }
    experimentSeries: { type: Object, default: () => ({}) }
  },
  data() {
    return {
      selectedField: '',
      SEVERITY_TAG,
      SEVERITY_LABELS
    }
  },
  computed: {
    fields() {
      return Object.keys(this.experimentSeries)
    },
    /** 当前字段的模型预期（报告 model.rows 中同名测点） */
    modelRow() {
      const model = this.diagnosisResult && this.diagnosisResult.model
      return (model && model.rows || []).find(r => r.column === this.selectedField) || null
    },
    /** 需要展示的发现（不含“提示”级别） */
    shownFindings() {
      return ((this.diagnosisResult && this.diagnosisResult.findings) || []).filter(f => f.severity !== 'info')
    },
    statusTagType() {
      return (this.diagnosisResult && RESULT_TAG[this.diagnosisResult.result]) || 'info'
    }
  },
  watch: {
    diagnosisResult() {
      this.$nextTick(this.updateChart)
    },
    fields: {
      handler(fields) {
        if (!fields.includes(this.selectedField)) {
          this.selectedField = fields[0] || ''
          this.$nextTick(this.updateChart)
        }
      },
      immediate: true
    }
  },
  mounted() {
    this.chart = echarts.init(this.$refs.chartContainer)
    this.updateChart()
    window.addEventListener('resize', this.handleResize)
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.handleResize)
    if (this.chart) {
      this.chart.dispose()
      this.chart = null
    }
  },
  methods: {
    handleResize() {
      if (this.chart) this.chart.resize()
    },
    updateChart() {
      if (!this.chart || !this.selectedField) return
      const values = this.experimentSeries[this.selectedField] || []
      const row = this.modelRow
      const line = {
        name: '实测',
        type: 'line',
        data: values,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: '#409eff' }
      }
      if (row) {
        const lo = row.expected * (1 - row.warn)
        const hi = row.expected * (1 + row.warn)
        line.markLine = {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#909399', type: 'dashed' },
          label: { formatter: `模型预期 ${row.expected.toFixed(row.unit === 'MPa' ? 3 : 1)} ${row.unit}`, color: '#606266' },
          data: [{ yAxis: row.expected }]
        }
        line.markArea = {
          silent: true,
          itemStyle: { color: 'rgba(144, 147, 153, 0.12)' },
          label: { show: true, position: 'insideTopLeft', color: '#909399', formatter: `预警范围 ±${(row.warn * 100).toFixed(1)}%` },
          data: [[{ yAxis: lo }, { yAxis: hi }]]
        }
      }
      const all = values.concat(row ? [row.expected * (1 - row.alarm), row.expected * (1 + row.alarm)] : [])
      const finite = all.filter(v => Number.isFinite(v))
      this.chart.setOption({
        title: {
          text: row ? `${this.selectedField} · 实测与模型预期` : `${this.selectedField}（该测点不在仿真模型输出中）`,
          left: 'center',
          textStyle: { fontSize: 14 }
        },
        tooltip: { trigger: 'axis' },
        grid: { left: '3%', right: '4%', bottom: '3%', top: 50, containLabel: true },
        xAxis: { type: 'category', data: values.map((_, i) => i), name: '特征组' },
        yAxis: {
          type: 'value',
          name: row ? `${this.selectedField}（${row.unit}）` : this.selectedField,
          min: finite.length ? Math.min(...finite) : null,
          max: finite.length ? Math.max(...finite) : null,
          axisLabel: { formatter: v => Number(v.toPrecision(4)) }
        },
        series: [line]
      }, true)
    }
  }
}
</script>

<style scoped>
.result-display-card {
  max-height: calc(100vh - 280px);
  overflow-y: auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 16px;
  font-weight: bold;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.finding {
  padding: 6px 0;
  border-bottom: 1px dashed #ebeef5;
  font-size: 13px;
}
.finding-title {
  margin-left: 6px;
  font-weight: 600;
}
.finding-detail {
  margin-top: 2px;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}
.indicators-card {
  margin-bottom: 15px;
}

.result-info-card >>> .el-card__header,
.chart-card >>> .el-card__header,
.indicators-card >>> .el-card__header {
  padding: 10px 15px;
  background-color: #f5f7fa;
}

.result-content {
  padding: 10px 0;
}

.diagnosis-section,
.repair-section {
  margin-top: 15px;
}

.diagnosis-section h4,
.repair-section h4 {
  font-size: 14px;
  color: #303133;
  margin-bottom: 10px;
  padding-left: 8px;
  border-left: 3px solid #409eff;
}

.advice-card {
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.8;
  background: #f5f7fa;
}

.chart-controls {
  float: right;
  display: flex;
  align-items: center;
}

.chart-container {
  height: 300px;
  width: 100%;
  min-height: 300px;
}

.abnormal-value {
  color: #f56c6c;
  font-weight: bold;
}

.action-bar {
  margin-top: 20px;
  text-align: right;
  padding: 10px 0;
  border-top: 1px solid #ebeef5;
}
</style>
