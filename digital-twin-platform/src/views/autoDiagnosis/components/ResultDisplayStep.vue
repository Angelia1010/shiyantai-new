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
            </el-descriptions>

            <div v-if="diagnosisResult.diagnosis" class="diagnosis-section">
              <h4>诊断结论</h4>
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="故障类型">
                  {{ diagnosisResult.diagnosis.fault_name || '无' }}
                </el-descriptions-item>
                <el-descriptions-item label="故障位置">
                  {{ diagnosisResult.diagnosis.location || '无' }}
                </el-descriptions-item>
                <el-descriptions-item label="分析说明">
                  {{ diagnosisResult.diagnosis.analysis || '无' }}
                </el-descriptions-item>
              </el-descriptions>
            </div>

            <div v-if="diagnosisResult.repairAdvice" class="repair-section">
              <h4>维修建议</h4>
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
            <span>数据对比图表</span>
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
              <el-button-group style="margin-left: 10px;">
                <el-button 
                  size="small" 
                  :type="chartMode === 'experiment' ? 'primary' : ''"
                  @click="chartMode = 'experiment'; updateChart()"
                >
                  试验数据
                </el-button>
                <el-button 
                  size="small" 
                  :type="chartMode === 'simulation' ? 'primary' : ''"
                  @click="chartMode = 'simulation'; updateChart()"
                  :disabled="!hasSimulation"
                >
                  仿真数据
                </el-button>
                <el-button 
                  size="small" 
                  :type="chartMode === 'compare' ? 'primary' : ''"
                  @click="chartMode = 'compare'; updateChart()"
                  :disabled="!hasSimulation"
                >
                  对比
                </el-button>
              </el-button-group>
            </div>
          </div>
          <div ref="chartContainer" class="chart-container"></div>
        </el-card>

        <el-card shadow="never" class="indicators-card" v-if="diagnosisResult && diagnosisResult.indicators.length">
          <div slot="header">诊断指标</div>
          <el-table :data="diagnosisResult.indicators" border size="small" max-height="200">
            <el-table-column prop="name" label="指标名称" min-width="150" />
            <el-table-column prop="reference" label="类型" width="120" />
            <el-table-column prop="value" label="指标值" width="120">
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

const STATUS_TAG = { normal: 'success', abnormal: 'danger', inconclusive: 'warning' }

export default {
  name: 'ResultDisplayStep',
  props: {
    // utils/report.js summarizeReport() 的结果
    diagnosisResult: { type: Object, default: null },
    // { 变量: [每组均值] }
    experimentSeries: { type: Object, default: () => ({}) },
    // { 变量: [仿真值] }
    simulationData: { type: Object, default: () => ({}) }
  },
  data() {
    return {
      selectedField: '',
      chartMode: 'experiment'
    }
  },
  computed: {
    fields() {
      return Object.keys(this.experimentSeries)
    },
    hasSimulation() {
      return Object.keys(this.simulationData).length > 0
    },
    statusTagType() {
      return (this.diagnosisResult && STATUS_TAG[this.diagnosisResult.result]) || 'info'
    }
  },
  watch: {
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
      const series = []
      if (this.chartMode !== 'simulation') {
        series.push({ name: '试验数据', values: this.experimentSeries[this.selectedField] || [], color: '#409eff' })
      }
      if (this.chartMode !== 'experiment') {
        series.push({ name: '仿真数据', values: this.simulationData[this.selectedField] || [], color: '#67c23a', dashed: true })
      }
      const length = Math.max(0, ...series.map(s => s.values.length))
      this.chart.setOption({
        title: { text: `${this.selectedField} 数据曲线`, left: 'center', textStyle: { fontSize: 14 } },
        tooltip: { trigger: 'axis' },
        legend: { data: series.map(s => s.name), top: 30 },
        grid: { left: '3%', right: '4%', bottom: '3%', top: 80, containLabel: true },
        xAxis: { type: 'category', data: Array.from({ length }, (_, i) => i) },
        yAxis: { type: 'value', name: this.selectedField },
        series: series.map(s => ({
          name: s.name,
          type: 'line',
          data: s.values,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, type: s.dashed ? 'dashed' : 'solid' },
          itemStyle: { color: s.color }
        }))
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

.result-info-card,
.chart-card,
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
