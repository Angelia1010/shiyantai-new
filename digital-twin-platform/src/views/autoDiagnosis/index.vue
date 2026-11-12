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
        @next="handleConfigNext"
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
import { addDataDir, setAutoDiagnose, setWatchPath } from '@/api/files'
import { downloadReport, getDiagnosisSettings, getReport, listTasks, saveDiagnosisSettings } from '@/api/tasks'
import { errorMessage } from '@/utils/request'
import { createTicker } from '@/utils/backgroundTicker'
import { MessageType, openChannel } from '@/utils/broadcastChannel'
import { createRemoteLogger } from '@/utils/remoteLogger'
import { summarizeReport } from '@/utils/report'

const POLL_INTERVAL_MS = 3000
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
        diagnosisMode: 'realtime',
        autoDiagnosis: true,
        mediumDensity: null, // 当前燃油 20 ℃ 密度；与工作台、自动诊断共用（诊断设置），留空按健康基准的油品
        groupSize: 5
      },
      selectedFiles: [],
      logs: [],
      diagnosisResult: null,
      experimentSeries: {}
    }
  },
  created() {
    // 以下对象不需要响应式
    this.remoteLogger = createRemoteLogger('autoDiagnosis')
    this.pipeline = null
    this.channel = null
    this.ticker = null
    this.polling = false
    this.realtimeSince = 0
    this.handledTasks = new Set()
    this.announcedTasks = new Set()
    this.savedDensity = null
    getDiagnosisSettings().then(st => {
      this.savedDensity = st.fuel_density_20
      if (this.config.mediumDensity == null || this.config.mediumDensity === '') {
        this.config.mediumDensity = st.fuel_density_20
      }
    }).catch(() => {})
  },
  beforeDestroy() {
    // 实时模式的诊断在后端进行，离开页面不关闭它，只停止本页的结果轮询
    if (this.isRunning) this.stopDiagnosis({ keepBackend: true })
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
    async handleConfigNext() {
      if (!this.config.dataPath.trim()) {
        this.$message.warning('请输入试验数据路径')
        return
      }
      // 前端填写的目录先登记到后端（已登记的直接通过），之后读文件、监控都用它
      try {
        const { path } = await addDataDir(this.config.dataPath.trim(), true)
        this.config.dataPath = path
      } catch (error) {
        this.$message.error(errorMessage(error))
        return
      }
      // 燃油密度保存为诊断设置，后端自动诊断也用它
      const density = this.config.mediumDensity === '' ? null : this.config.mediumDensity
      if (density !== this.savedDensity) {
        try {
          const st = await saveDiagnosisSettings({ fuel_density_20: density })
          this.savedDensity = st.fuel_density_20
        } catch (error) {
          this.$message.error(errorMessage(error))
          return
        }
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
        experimentSeries: {}
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
        log: this.addLog,
        onStep: (step, message) => {
          this.currentProcessStep = step
          this.setStatus(message)
        },
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

    stopDiagnosis({ keepBackend = false } = {}) {
      const wasRealtime = this.isRunning && this.config.diagnosisMode === 'realtime'
      this.isRunning = false
      if (this.ticker) {
        this.ticker.stop()
        this.ticker = null
      }
      if (this.pipeline) {
        this.pipeline.close()
      }
      if (wasRealtime && !keepBackend) {
        setAutoDiagnose(false)
          .then(() => this.addLog('已关闭后端自动诊断（工作台的实时数据显示不受影响）', 'warn'))
          .catch(() => {})
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

    /** 实时模式：由后端在每个文件写完后自动诊断，本页只负责开启并展示结果。 */
    async startRealtimeMode() {
      this.channel = this.channel || openChannel()
      if (!this.dashboardWindow || this.dashboardWindow.closed) {
        this.dashboardWindow = window.open(`${window.location.pathname}#/`, 'shiyantai_dashboard')
      }
      const { path } = await setWatchPath(this.config.dataPath, false, true)
      this.addLog(`开始监控目录（含子目录）：${path}`, 'success')
      this.addLog('后端将在每个数据文件写完后自动诊断，离开本页也会继续；点“停止”可关闭自动诊断', 'info')
      this.realtimeSince = Date.now() - 1000
      this.handledTasks = new Set()
      this.announcedTasks = new Set()
      this.currentProcessStep = 2
      this.setStatus('监控中，等待文件写完...')
      this.ticker = createTicker(POLL_INTERVAL_MS, this.pollAutoTasks)
    },

    /** 查询本次开启以来后端自动诊断产生的任务，展示新完成的结果。 */
    async pollAutoTasks() {
      if (!this.isRunning || this.polling) return
      this.polling = true
      try {
        const { items } = await listTasks({ mode: 'auto', start_time: this.realtimeSince, page_size: 50 })
        for (const task of items.slice().reverse()) {
          if (this.handledTasks.has(task.task_id)) continue
          if (task.status === 'Created') {
            if (!this.announcedTasks.has(task.task_id)) {
              this.announcedTasks.add(task.task_id)
              this.addLog(`文件已写完，正在诊断：${task.file_name}`, 'info')
              this.setStatus(`正在诊断: ${task.file_name}`)
            }
            continue
          }
          this.handledTasks.add(task.task_id)
          if (task.status === 'Failed') {
            this.addLog(`诊断 ${task.file_name} 失败：${task.error || '未知原因'}`, 'error')
            continue
          }
          const report = await getReport(task.task_id)
          this.showResult(summarizeReport(task.task_id, task.file_name, report))
          this.setStatus('监控中，等待文件写完...')
        }
      } catch (error) {
        this.addLog(`查询诊断结果失败：${errorMessage(error)}`, 'error')
      } finally {
        this.polling = false
      }
    },

    showResult(summary) {
      this.diagnosisResult = summary
      this.broadcast(MessageType.DIAGNOSIS_RESULT, summary)
      const level = { abnormal: 'warn', warning: 'warn', inconclusive: 'info' }[summary.result] || 'success'
      this.addLog(`诊断完成：${summary.fileName} → ${summary.statusText}${summary.summary ? '（' + summary.summary + '）' : ''}`, level)
      if (summary.result === 'abnormal') {
        this.$notify({ title: '异常警告', message: `${summary.fileName}：${summary.summary}`, type: 'warning', duration: 0 })
      }
    },

    async processFile(fileName) {
      this.addLog(`开始处理：${fileName}`, 'info')
      try {
        const { taskId, report, experimentSeries } = await this.pipeline.processFile(fileName)
        this.experimentSeries = experimentSeries
        if (!report) {
          this.addLog(`${fileName} 已展示（未开启自动诊断）`, 'success')
          return
        }
        this.showResult(summarizeReport(taskId, fileName, report))
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
