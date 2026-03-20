<template>
  <div class="auto-diagnosis-container">
    <el-row :gutter="20">
      <el-col :span="24">
        <div class="page-title">自动诊断流程控制</div>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="6">
        <el-card class="config-card">
          <div slot="header" class="card-header">
            <span>配置参数</span>
          </div>
          <el-form label-width="100px">
            <el-form-item label="试验数据路径">
              <el-input v-model="config.dataPath" placeholder="如: C:/test_data" />
            </el-form-item>
            <el-form-item label="AMESim模型">
              <el-input v-model="config.ameModel" placeholder="如: pump_model.ame" />
            </el-form-item>
            <el-form-item label="诊断模式">
              <el-select v-model="config.diagnosisMode" placeholder="请选择">
                <el-option label="实时监控" value="realtime" />
                <el-option label="文件处理" value="file" />
                <el-option label="混合模式" value="hybrid" />
              </el-select>
            </el-form-item>
            <el-form-item label="自动诊断">
              <el-switch v-model="config.autoDiagnosis" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="startDiagnosis" :loading="isRunning">
                启动诊断
              </el-button>
              <el-button @click="stopDiagnosis" :disabled="!isRunning">
                停止
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="status-card">
          <div slot="header" class="card-header">
            <span>流程状态</span>
          </div>
          <div class="process-steps">
            <el-steps direction="vertical" :active="currentStep" finish-status="success">
              <el-step title="数据监控" description="监控试验数据文件" />
              <el-step title="数据预处理" description="读取并解析数据" />
              <el-step title="系统仿真" description="运行AMESim仿真" />
              <el-step title="故障诊断" description="分析数据并进行诊断" />
              <el-step title="报告生成" description="生成诊断报告" />
              <el-step title="结果展示" description="前端可视化展示" />
            </el-steps>
          </div>
          <div class="current-status">
            <el-alert :title="statusMessage" :type="statusType" :closable="false" show-icon />
          </div>
          <div class="log-area">
            <div class="log-title">执行日志</div>
            <div class="log-content" ref="logContent">
              <div v-for="(log, index) in logs" :key="index" :class="['log-item', log.level]">
                <span class="log-time">{{ log.time }}</span>
                <span class="log-msg">{{ log.message }}</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="result-card">
          <div slot="header" class="card-header">
            <span>诊断结果</span>
          </div>
          <div v-if="diagnosisResult" class="diagnosis-result">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="状态">
                <el-tag :type="getResultTagType(diagnosisResult.status)">
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
            <div v-if="diagnosisResult.diagnosis" class="diagnosis-details">
              <h4>诊断详情</h4>
              <div v-for="(item, key) in diagnosisResult.diagnosis" :key="key" class="diagnosis-item">
                <div class="diagnosis-label">{{ key }}</div>
                <div class="diagnosis-value">{{ formatDiagnosisValue(item) }}</div>
              </div>
            </div>
            <div v-if="diagnosisResult.repairAdvice" class="repair-advice">
              <h4>维修建议</h4>
              <p>{{ diagnosisResult.repairAdvice }}</p>
            </div>
          </div>
          <div v-else class="no-result">
            <p>暂无诊断结果</p>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="data-display-row">
      <el-col :span="24">
        <el-card class="data-display-card">
          <div slot="header" class="card-header">
            <span>实时数据监控</span>
            <div class="header-actions">
              <el-button-group>
                <el-button size="small" :type="dataMode === 'temperature' ? 'primary' : ''" @click="dataMode = 'temperature'">
                  温度
                </el-button>
                <el-button size="small" :type="dataMode === 'pressure' ? 'primary' : ''" @click="dataMode = 'pressure'">
                  压力
                </el-button>
              </el-button-group>
            </div>
          </div>
          <div class="data-display-content">
            <div class="data-charts">
              <div v-for="(chart, index) in chartData" :key="index" class="chart-item">
                <div class="chart-title">{{ chart.title }}</div>
                <div :ref="'chart' + index" class="chart-container"></div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="tasks-card">
          <div slot="header" class="card-header">
            <span>历史任务</span>
          </div>
          <el-table :data="tasks" border style="width: 100%">
            <el-table-column prop="task_id" label="任务ID" width="180" />
            <el-table-column prop="type" label="类型" width="80" />
            <el-table-column prop="status" label="状态" width="100">
              <template slot-scope="scope">
                <el-tag :type="getStatusTagType(scope.row.status)">
                  {{ scope.row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="files" label="文件" min-width="200" />
            <el-table-column prop="path" label="路径" min-width="150" />
            <el-table-column label="操作" width="200">
              <template slot-scope="scope">
                <el-button size="mini" @click="viewReport(scope.row)">查看报告</el-button>
                <el-button size="mini" type="danger" @click="deleteTask(scope.row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            :current-page="taskPage"
            :page-size="taskPageSize"
            :total="taskTotal"
            layout="total, prev, pager, next"
            @current-change="handleTaskPageChange"
          />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import {
  startAutoDiagnosis,
  stopAutoDiagnosis,
  getDiagnosisStatus,
  getDiagnosisReport,
  getTasks
} from '@/api/autoDiagnosis'
import { Message } from 'element-ui'

export default {
  name: 'AutoDiagnosis',
  data() {
    return {
      config: {
        dataPath: 'C:/test_data',
        ameModel: 'pump_model.ame',
        diagnosisMode: 'realtime',
        autoDiagnosis: true
      },
      isRunning: false,
      currentStep: 0,
      statusMessage: '等待启动',
      statusType: 'info',
      logs: [],
      diagnosisResult: null,
      tasks: [],
      taskPage: 1,
      taskPageSize: 10,
      taskTotal: 0,
      dataMode: 'temperature',
      chartData: [
        { title: '转速', key: '燃油泵实际转速', data: [] },
        { title: '供油压力', key: '供油压力1-1', data: [] },
        { title: '回油压力', key: '回油压力1-1', data: [] },
        { title: '供油温度', key: '供油温度1-1', data: [] }
      ],
      charts: [],
      featureMap: {},
      timer: null,
      pollTimer: null
    }
  },
  created() {
    this.loadTasks()
  },
  beforeDestroy() {
    this.stopPolling()
    this.disposeCharts()
  },
  methods: {
    addLog(message, level = 'info') {
      const now = new Date()
      const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`
      this.logs.push({ time, message, level })
      this.$nextTick(() => {
        if (this.$refs.logContent) {
          this.$refs.logContent.scrollTop = this.$refs.logContent.scrollHeight
        }
      })
    },
    async startDiagnosis() {
      if (!this.config.dataPath) {
        Message.warning('请输入试验数据路径')
        return
      }
      this.isRunning = true
      this.currentStep = 0
      this.statusMessage = '正在启动诊断流程...'
      this.statusType = 'info'
      this.addLog('开始自动诊断流程', 'info')

      try {
        const response = await startAutoDiagnosis({
          dataPath: this.config.dataPath,
          ameModel: this.config.ameModel,
          mode: this.config.diagnosisMode,
          autoDiagnosis: this.config.autoDiagnosis
        })
        this.addLog('诊断任务已启动: ' + (response.taskId || ''), 'success')
        this.currentStep = 1
        this.statusMessage = '数据监控中...'
        this.startPolling()
      } catch (error) {
        this.addLog('启动失败: ' + (error.message || error), 'error')
        this.isRunning = false
        this.statusMessage = '启动失败'
        this.statusType = 'error'
        Message.error('启动诊断失败')
      }
    },
    async stopDiagnosis() {
      try {
        await stopAutoDiagnosis()
        this.isRunning = false
        this.stopPolling()
        this.addLog('诊断流程已停止', 'warn')
        this.statusMessage = '已停止'
        this.statusType = 'warning'
        this.currentStep = 0
        Message.info('诊断已停止')
      } catch (error) {
        Message.error('停止失败: ' + (error.message || error))
      }
    },
    startPolling() {
      this.pollTimer = setInterval(async () => {
        if (!this.isRunning) return
        try {
          const status = await getDiagnosisStatus()
          this.updateStatus(status)
        } catch (error) {
          console.error('获取状态失败', error)
        }
      }, 2000)
    },
    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer)
        this.pollTimer = null
      }
    },
    updateStatus(status) {
      if (status.step) {
        this.currentStep = status.step
      }
      if (status.message) {
        this.statusMessage = status.message
        this.addLog(status.message, status.level || 'info')
      }
      if (status.type) {
        this.statusType = status.type
      }
      if (status.featureMap) {
        this.featureMap = status.featureMap
        this.updateCharts()
      }
      if (status.result) {
        this.diagnosisResult = status.result
        this.addLog('诊断完成', 'success')
      }
      if (status.completed) {
        this.isRunning = false
        this.stopPolling()
      }
    },
    async loadTasks() {
      try {
        const response = await getTasks(this.taskPage, this.taskPageSize)
        this.tasks = response.tasks || []
        this.taskTotal = response.total_count || 0
      } catch (error) {
        console.error('加载任务失败', error)
      }
    },
    handleTaskPageChange(page) {
      this.taskPage = page
      this.loadTasks()
    },
    async viewReport(task) {
      try {
        const report = await getDiagnosisReport(task.task_id)
        this.diagnosisResult = report
        Message.success('报告已加载')
      } catch (error) {
        Message.error('加载报告失败')
      }
    },
    async deleteTask(task) {
      this.$confirm('确认删除此任务?', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        this.loadTasks()
        Message.success('删除成功')
      })
    },
    getStatusTagType(status) {
      const map = {
        'Completed': 'success',
        'Pending': 'primary',
        'Stop': 'warning',
        'Failed': 'danger'
      }
      return map[status] || 'info'
    },
    getResultTagType(status) {
      const map = {
        '正常': 'success',
        '异常': 'danger',
        '警告': 'warning'
      }
      return map[status] || 'info'
    },
    formatDiagnosisValue(value) {
      if (typeof value === 'object') {
        return JSON.stringify(value)
      }
      return value
    },
    initCharts() {
      this.$nextTick(() => {
        this.chartData.forEach((chart, index) => {
          const ref = this.$refs['chart' + index]
          if (ref && ref[0]) {
            const chartInstance = echarts.init(ref[0])
            chartInstance.setOption({
              title: { text: chart.title, left: 'center', textStyle: { fontSize: 12 } },
              tooltip: { trigger: 'axis' },
              xAxis: { type: 'category', data: [] },
              yAxis: { type: 'value' },
              series: [{ data: [], type: 'line', smooth: true }]
            })
            this.charts.push(chartInstance)
          }
        })
      })
    },
    updateCharts() {
      this.chartData.forEach((chart, index) => {
        const chartInstance = this.charts[index]
        if (chartInstance && this.featureMap[chart.key]) {
          const value = this.featureMap[chart.key].avg
          if (typeof value === 'number') {
            const data = chart.data
            data.push(value)
            if (data.length > 20) data.shift()
            chartInstance.setOption({
              xAxis: { data: data.map((_, i) => i) },
              series: [{ data: data }]
            })
          }
        }
      })
    },
    disposeCharts() {
      this.charts.forEach(chart => {
        if (chart && chart.dispose) {
          chart.dispose()
        }
      })
      this.charts = []
    }
  }
}
</script>

<style scoped>
.auto-diagnosis-container {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.page-title {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 20px;
  text-align: center;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.config-card, .status-card, .result-card, .data-display-card, .tasks-card {
  margin-bottom: 20px;
}

.process-steps {
  padding: 20px;
  background-color: #fff;
  border-radius: 4px;
  margin-bottom: 15px;
}

.current-status {
  margin-bottom: 15px;
}

.log-area {
  background-color: #1d2530;
  border-radius: 4px;
  padding: 10px;
}

.log-title {
  color: #fff;
  font-size: 14px;
  margin-bottom: 10px;
}

.log-content {
  max-height: 200px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 12px;
}

.log-item {
  display: flex;
  gap: 10px;
  padding: 2px 0;
}

.log-time {
  color: #909399;
  flex-shrink: 0;
}

.log-msg {
  color: #fff;
}

.log-item.info .log-msg { color: #909399; }
.log-item.success .log-msg { color: #67c23a; }
.log-item.warn .log-msg { color: #e6a23c; }
.log-item.error .log-msg { color: #f56c6c; }

.diagnosis-result {
  padding: 10px;
}

.diagnosis-details, .repair-advice {
  margin-top: 15px;
  padding: 10px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.diagnosis-item {
  display: flex;
  justify-content: space-between;
  padding: 5px 0;
  border-bottom: 1px solid #ebeef5;
}

.diagnosis-label {
  font-weight: bold;
  color: #606266;
}

.diagnosis-value {
  color: #303133;
}

.no-result {
  text-align: center;
  color: #909399;
  padding: 40px;
}

.data-display-content {
  min-height: 300px;
}

.data-charts {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.chart-item {
  background: #fff;
  padding: 10px;
  border-radius: 4px;
}

.chart-title {
  text-align: center;
  font-weight: bold;
  margin-bottom: 10px;
}

.chart-container {
  height: 200px;
}

.header-actions {
  float: right;
}
</style>
