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
                <el-tag :type="getStatusType(diagnosisResult.status)" size="small">
                  {{ diagnosisResult.status }}
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
                  v-for="col in dataFeatures.columns" 
                  :key="col.name" 
                  :label="col.name" 
                  :value="col.name"
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
                  :disabled="!config.enableSimulation || Object.keys(simulationData).length === 0"
                >
                  仿真数据
                </el-button>
                <el-button 
                  size="small" 
                  :type="chartMode === 'compare' ? 'primary' : ''"
                  @click="chartMode = 'compare'; updateChart()"
                  :disabled="!config.enableSimulation || Object.keys(simulationData).length === 0"
                >
                  对比
                </el-button>
              </el-button-group>
            </div>
          </div>
          <div ref="chartContainer" class="chart-container"></div>
        </el-card>

        <el-card shadow="never" class="indicators-card" v-if="diagnosisResult && diagnosisResult.indicators">
          <div slot="header">诊断指标</div>
          <el-table :data="diagnosisResult.indicators" border size="small" max-height="200">
            <el-table-column prop="name" label="指标名称" min-width="150" />
            <el-table-column prop="reference" label="参考值" width="120" />
            <el-table-column prop="value" label="实测值" width="120">
              <template slot-scope="scope">
                <span :class="{'abnormal-value': isAbnormal(scope.row)}">
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

export default {
  name: 'ResultDisplayStep',
  props: {
    diagnosisResult: {
      type: Object,
      default: null
    },
    experimentData: {
      type: Array,
      default: () => []
    },
    simulationData: {
      type: Object,
      default: () => ({})
    },
    simulationVariables: {
      type: Array,
      default: () => []
    },
    dataFeatures: {
      type: Object,
      default: () => ({ rowCount: 0, columnCount: 0, columns: [] })
    },
    config: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      chart: null,
      selectedField: '',
      chartMode: 'experiment'
    }
  },
  mounted() {
    this.$nextTick(() => {
      this.initChart()
      if (this.dataFeatures.columns.length > 0) {
        this.selectedField = this.dataFeatures.columns[0].name
        this.updateChart()
      }
    })
    window.addEventListener('resize', this.handleResize)
  },
  beforeDestroy() {
    if (this.chart) {
      this.chart.dispose()
      this.chart = null
    }
    window.removeEventListener('resize', this.handleResize)
  },
  watch: {
    dataFeatures: {
      handler(val) {
        if (val.columns.length > 0 && !this.selectedField) {
          this.selectedField = val.columns[0].name
          this.updateChart()
        }
      },
      deep: true
    }
  },
  methods: {
    initChart() {
      if (!this.$refs.chartContainer) return
      if (this.chart) {
        this.chart.dispose()
      }
      this.chart = echarts.init(this.$refs.chartContainer)
    },
    handleResize() {
      if (this.chart) {
        this.chart.resize()
      }
    },
    updateChart() {
      console.log('updateChart called - selectedField:', this.selectedField)
      console.log('updateChart - experimentData length:', this.experimentData.length)
      console.log('updateChart - simulationData length:', this.simulationData.length)
      console.log('updateChart - chartMode:', this.chartMode)
      
      if (!this.selectedField) return
      
      // 如果图表未初始化，先初始化
      if (!this.chart) {
        this.initChart()
      }
      
      if (!this.chart) {
        console.error('Chart initialization failed')
        return
      }

      const option = {
        title: {
          text: `${this.selectedField} 数据曲线`,
          left: 'center',
          textStyle: { fontSize: 14 }
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'cross' }
        },
        legend: {
          data: [],
          top: 30
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '3%',
          top: 80,
          containLabel: true
        },
        xAxis: {
          type: 'category',
          data: []
        },
        yAxis: {
          type: 'value',
          name: this.selectedField
        },
        series: []
      }

      if (this.chartMode === 'experiment' || this.chartMode === 'compare') {
        const expData = this.extractFieldData(this.experimentData, this.selectedField)
        console.log('updateChart - expData length:', expData.length)
        if (expData.length > 0) {
          option.xAxis.data = expData.map((_, i) => i)
          option.series.push({
            name: '试验数据',
            type: 'line',
            data: expData,
            smooth: true,
            lineStyle: { width: 2 },
            itemStyle: { color: '#409eff' },
            symbol: 'circle',
            symbolSize: 6
          })
          option.legend.data.push('试验数据')
        }
      }

      if ((this.chartMode === 'simulation' || this.chartMode === 'compare') && Object.keys(this.simulationData).length > 0) {
        const simData = this.extractSimulationData(this.simulationData, this.selectedField)
        console.log('updateChart - simData length:', simData.length)
        if (simData.length > 0) {
          if (option.xAxis.data.length === 0) {
            option.xAxis.data = simData.map((_, i) => i)
          }
          option.series.push({
            name: '仿真数据',
            type: 'line',
            data: simData,
            smooth: true,
            lineStyle: { width: 2, type: 'dashed' },
            itemStyle: { color: '#67c23a' },
            symbol: 'circle',
            symbolSize: 6
          })
          option.legend.data.push('仿真数据')
        }
      }

      console.log('updateChart - final option:', JSON.stringify({
        xAxisDataLength: option.xAxis.data.length,
        seriesLength: option.series.length,
        legendData: option.legend.data
      }))

      this.chart.setOption(option, true)
    },
    extractFieldData(data, field) {
      console.log('extractFieldData - field:', field)
      console.log('extractFieldData - data sample:', data.slice(0, 2))
      
      const result = data.map((item, index) => {
        if (item[field]) {
          const avg = item[field].avg
          // 处理可能是字符串的数字
          const numValue = typeof avg === 'number' ? avg : parseFloat(avg)
          if (!isNaN(numValue)) {
            return numValue
          }
        }
        return null
      }).filter(v => v !== null)
      
      console.log('extractFieldData - result length:', result.length)
      console.log('extractFieldData - result sample:', result.slice(0, 5))
      return result
    },
    extractSimulationData(simulationDataObj, field) {
      console.log('extractSimulationData - field:', field)
      console.log('extractSimulationData - available variables:', Object.keys(simulationDataObj))
      
      if (!simulationDataObj[field]) {
        console.log('extractSimulationData - field not found in simulation data')
        return []
      }
      
      const data = simulationDataObj[field]
      console.log('extractSimulationData - data length:', data.length)
      console.log('extractSimulationData - data sample:', data.slice(0, 5))
      
      return data.map(value => {
        if (typeof value === 'number') return value
        const numValue = parseFloat(value)
        return isNaN(numValue) ? null : numValue
      }).filter(v => v !== null)
    },
    getStatusType(status) {
      const map = {
        '正常': 'success',
        '异常': 'danger',
        '警告': 'warning'
      }
      return map[status] || 'info'
    },
    isAbnormal(row) {
      if (!row.reference || !row.value) return false
      const ref = parseFloat(row.reference)
      const val = parseFloat(row.value)
      if (isNaN(ref) || isNaN(val)) return false
      const tolerance = ref * 0.1
      return Math.abs(val - ref) > tolerance
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
