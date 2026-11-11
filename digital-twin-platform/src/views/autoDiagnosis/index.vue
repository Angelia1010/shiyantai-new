<template>
  <div class="auto-diagnosis-container">
    <div class="page-header">
      <h2 class="page-title">自动诊断流程</h2>
      <el-tag :type="isRunning ? 'success' : 'info'" size="medium">
        {{ isRunning ? '运行中' : '待机' }}
      </el-tag>
    </div>

    <el-card class="steps-card" shadow="hover">
      <el-steps :active="currentStep" align-center finish-status="success">
        <el-step title="配置参数" description="设置数据路径和诊断模式" />
        <el-step title="文件选择" description="选择待诊断文件" />
        <el-step title="诊断执行" description="运行诊断流程" />
        <el-step title="结果展示" description="查看诊断结果" />
      </el-steps>
    </el-card>

    <div class="step-content" v-if="currentStep === 0">
      <config-step
        :config="config"
        :variable-configs="variableConfigs"
        @next="handleConfigNext"
        @add-variable="addVariable"
        @remove-variable="removeVariable"
      />
    </div>

    <div class="step-content" v-if="currentStep === 1">
      <file-select-step
        :config="config"
        :selected-files="selectedFiles"
        @update:selected-files="selectedFiles = $event"
        @prev="currentStep = 0"
        @next="handleFileSelectNext"
      />
    </div>

    <div class="step-content" v-if="currentStep === 2">
      <diagnosis-exec-step
        :is-running="isRunning"
        :logs="logs"
        :current-process-step="currentProcessStep"
        :status-message="statusMessage"
        @start="startDiagnosis"
        @stop="stopDiagnosis"
        @prev="handleDiagnosisPrev"
        @next="currentStep = 3"
        @clear-logs="logs = []"
      />
    </div>

    <div class="step-content" v-if="currentStep === 3">
      <result-display-step
        :diagnosis-result="diagnosisResult"
        :experiment-series="experimentSeries"
        :simulation-data="simulationData"
        @prev="currentStep = 2"
        @restart="handleRestart"
        @download-report="downloadReport"
      />
    </div>
  </div>
</template>

<script>
import ConfigStep from './components/ConfigStep.vue'
import FileSelectStep from './components/FileSelectStep.vue'
import DiagnosisExecStep from './components/DiagnosisExecStep.vue'
import ResultDisplayStep from './components/ResultDisplayStep.vue'
import { Cancelled, DiagnosisPipeline } from './pipeline'
import { getWatchEvents, setWatchPath } from '@/api/files'
import { downloadReport } from '@/api/tasks'
import { errorMessage } from '@/utils/request'
import { createTicker } from '@/utils/backgroundTicker'
import { MessageType, openChannel } from '@/utils/broadcastChannel'
import { createRemoteLogger } from '@/utils/remoteLogger'
import { summarizeReport } from '@/utils/report'

const POLL_INTERVAL_MS = 5000
const MAX_LOGS = 300

export default {
  name: 'AutoDiagnosis',
  components: { ConfigStep, FileSelectStep, DiagnosisExecStep, ResultDisplayStep },
  data() {
    return {
      currentStep: 0,
      currentProcessStep: 0,
      isRunning: false,
      statusMessage: '等待启动',
      config: {
        dataPath: '',
        ameModel: '',
        diagnosisMode: 'realtime',
        autoDiagnosis: true,
        enableSimulation: false,
        electricalSpeed: null,
        mediumDensity: 850,
        groupSize: 5
      },
      // 试验变量 ↔ AMESim 仿真结果文件
      variableConfigs: [
        { name: '供油压力1-1', fileName: 'pressureGY11.data' },
        { name: '供油压力1-2', fileName: 'pressureGY12.data' },
        { name: '供油流量1-1', fileName: 'flowRateGY11.data' },
        { name: '供油流量1-2', fileName: 'flowRateGY12.data' },
        { name: '回油压力1-1', fileName: 'pressureHY11.data' },
        { name: '回油压力1-2', fileName: 'pressureHY12.data' },
        { name: '回油压力2-1', fileName: 'pressureHY21.data' },
        { name: '回油压力2-2', fileName: 'pressureHY22.data' },
        { name: '回油流量1-1', fileName: 'flowRateHY11.data' },
        { name: '回油流量1-2', fileName: 'flowRateHY12.data' }
      ],
      selectedFiles: [],
      logs: [],
      diagnosisResult: null,
      experimentSeries: {},
      simulationData: {}
    }
  },
  created() {
    // 以下对象不需要响应式
    this.remoteLogger = createRemoteLogger('autoDiagnosis')
    this.pipeline = null
    this.channel = null
    this.ticker = null
    this.fileQueue = []
    this.processing = false
    this.polling = false
    this.lastEventSeq = 0
  },
  beforeDestroy() {
    if (this.isRunning) this.stopDiagnosis()
    if (this.channel) this.channel.close()
    this.remoteLogger.close()
  },
  methods: {
    addLog(message, level = 'info') {
      const now = new Date()
      const time = [now.getHours(), now.getMinutes(), now.getSeconds()].map(n => String(n).padStart(2, '0')).join(':')
      this.logs.push({ time, message, level })
      if (this.logs.length > MAX_LOGS) this.logs.splice(0, this.logs.length - MAX_LOGS)
      this.remoteLogger.log(level, message)
    },

    broadcast(type, payload) {
      if (this.channel) this.channel.send(type, payload)
    },

    setStatus(message) {
      this.statusMessage = message
      this.broadcast(MessageType.DIAGNOSIS_STATUS, { message })
    },

    // ------------------------------------------------------------ 步骤导航
    addVariable() {
      this.variableConfigs.push({ name: '', fileName: '' })
    },
    removeVariable(index) {
      if (this.variableConfigs.length > 1) this.variableConfigs.splice(index, 1)
    },
    handleConfigNext() {
      if (!this.config.dataPath.trim()) {
        this.$message.warning('请输入试验数据路径')
        return
      }
      if (this.config.diagnosisMode === 'file') {
        this.currentStep = 1
      } else {
        this.selectedFiles = []
        this.currentStep = 2
      }
    },
    handleFileSelectNext() {
      if (!this.selectedFiles.length) {
        this.$message.warning('请选择至少一个文件')
        return
      }
      this.currentStep = 2
    },
    handleDiagnosisPrev() {
      this.currentStep = this.config.diagnosisMode === 'realtime' ? 0 : 1
    },
    handleRestart() {
      Object.assign(this, {
        currentStep: 0,
        currentProcessStep: 0,
        statusMessage: '等待启动',
        logs: [],
        diagnosisResult: null,
        experimentSeries: {},
        simulationData: {}
      })
    },
    downloadReport(taskId) {
      if (taskId) downloadReport(taskId).catch(() => {})
    },

    // ------------------------------------------------------------ 运行控制
    async startDiagnosis() {
      this.isRunning = true
      this.currentProcessStep = 1
      this.addLog('开始自动诊断流程', 'info')
      this.pipeline = new DiagnosisPipeline({
        config: this.config,
        variableConfigs: this.variableConfigs,
        log: this.addLog,
        onStep: (step, message) => {
          this.currentProcessStep = step
          this.setStatus(message)
        },
        onFrames: frames => this.broadcast(MessageType.FEATURE_FRAMES, frames),
        isCancelled: () => !this.isRunning
      })
      try {
        await this.pipeline.prepare()
        if (this.config.diagnosisMode === 'realtime') {
          await this.startRealtimeMode()
        } else {
          await this.runFileMode()
        }
      } catch (error) {
        this.addLog(`启动失败：${errorMessage(error)}`, 'error')
        this.stopDiagnosis()
      }
    },

    stopDiagnosis() {
      this.isRunning = false
      this.fileQueue = []
      if (this.ticker) {
        this.ticker.stop()
        this.ticker = null
      }
      if (this.pipeline) {
        this.pipeline.close()
      }
      this.currentProcessStep = 0
      this.setStatus('已停止')
      this.addLog('诊断流程已停止', 'warn')
      if (this.diagnosisResult) this.currentStep = 3
    },

    async runFileMode() {
      this.addLog(`文件模式，共 ${this.selectedFiles.length} 个文件`, 'info')
      for (const fileName of this.selectedFiles) {
        if (!this.isRunning) return
        await this.processFile(fileName)
      }
      if (!this.isRunning) return
      this.isRunning = false
      await this.pipeline.close()
      this.setStatus('诊断完成')
      this.addLog('所有文件处理完成', 'success')
      this.currentStep = 3
    },

    async startRealtimeMode() {
      this.channel = this.channel || openChannel()
      // 打开工作台展示实时数据（只打开一次，可被浏览器拦截弹窗）
      if (!this.dashboardWindow || this.dashboardWindow.closed) {
        this.dashboardWindow = window.open(`${window.location.pathname}#/?mode=realtime`, 'shiyantai_dashboard')
      }
      const { latest_seq: latestSeq, path } = await setWatchPath(this.config.dataPath)
      this.lastEventSeq = latestSeq
      this.addLog(`开始监控目录：${path}`, 'success')
      this.setStatus('监控中，等待新文件...')
      this.ticker = createTicker(POLL_INTERVAL_MS, this.pollWatchEvents)
    },

    async pollWatchEvents() {
      if (!this.isRunning || this.polling) return
      this.polling = true
      try {
        const { latest_seq: latestSeq, events } = await getWatchEvents(this.lastEventSeq)
        this.lastEventSeq = latestSeq
        for (const event of events) {
          if (!this.fileQueue.includes(event.file_name)) {
            this.fileQueue.push(event.file_name)
            this.addLog(`检测到${event.type === 'created' ? '新文件' : '文件更新'}：${event.file_name}`, 'info')
          }
        }
      } catch (error) {
        this.addLog(`查询文件变化失败：${errorMessage(error)}`, 'error')
      } finally {
        this.polling = false
      }
      this.drainQueue()
    },

    // 文件逐个处理，前一个处理完之前不会开始下一个
    async drainQueue() {
      if (this.processing) return
      this.processing = true
      try {
        while (this.isRunning && this.fileQueue.length) {
          await this.processFile(this.fileQueue.shift())
        }
      } finally {
        this.processing = false
      }
      if (this.isRunning) this.setStatus('监控中，等待新文件...')
    },

    async processFile(fileName) {
      this.addLog(`开始处理：${fileName}`, 'info')
      try {
        const { taskId, report, experimentSeries, simulationData } = await this.pipeline.processFile(fileName)
        this.experimentSeries = experimentSeries
        this.simulationData = simulationData
        if (!report) {
          this.addLog(`${fileName} 已展示（未开启自动诊断）`, 'success')
          return
        }
        const summary = summarizeReport(taskId, fileName, report)
        this.diagnosisResult = summary
        this.broadcast(MessageType.DIAGNOSIS_RESULT, summary)
        this.addLog(`诊断完成：${fileName} → ${summary.statusText}`, summary.result === 'abnormal' ? 'warn' : 'success')
        if (summary.result === 'abnormal') {
          this.$notify({ title: '异常警告', message: `文件 ${fileName} 检测到异常，请查看诊断结果`, type: 'warning', duration: 0 })
        }
      } catch (error) {
        if (error instanceof Cancelled) {
          this.addLog(`已停止处理 ${fileName}`, 'warn')
        } else {
          this.addLog(`处理 ${fileName} 失败：${errorMessage(error)}`, 'error')
        }
      }
    }
  }
}
</script>

<style scoped>
.auto-diagnosis-container {
  padding: 20px;
}

.steps-card {
  margin-bottom: 20px;
}

.step-content {
  padding-bottom: 20px;
}
</style>
