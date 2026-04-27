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
        @skip="handleSkipFileSelect"
      />
    </div>

    <div class="step-content" v-if="currentStep === 2">
      <diagnosis-exec-step
        :config="config"
        :selected-files="selectedFiles"
        :is-running="isRunning"
        :logs="logs"
        :current-process-step="currentProcessStep"
        :status-message="statusMessage"
        :feature-map="featureMap"
        @start="startDiagnosis"
        @stop="stopDiagnosis"
        @prev="handleDiagnosisPrev"
        @next="handleDiagnosisComplete"
      />
    </div>

    <div class="step-content" v-if="currentStep === 3">
      <result-display-step
        :diagnosis-result="diagnosisResult"
        :experiment-data="experimentData"
        :simulation-data="simulationData"
        :simulation-variables="simulationVariables"
        :data-features="dataFeatures"
        :config="config"
        @prev="currentStep = 2"
        @restart="handleRestart"
        @view-report="viewReport"
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

import {
  fileListAPI,
  newFileListAPI,
  readExcelApi,
  createTask,
  storeReport,
  diagnose,
  preliminaryDiagnose,
  getJobStatus,
  setWatchPath,
  saveFrontendLog
} from '@/api/home'
import {
  openModel,
  runSimulation,
  closeModel,
  setComponentParameter,
  readSimulationDataFile,
  writeInputData,
  initAmesimApi
} from '@/api/amesimAPI'
import { fetchReportPreview, downloadFile } from '@/api/article'
import { Message } from 'element-ui'
import {
  initBroadcastChannel,
  sendFeatureMapToDashboard,
  sendStatusToDashboard,
  sendDiagnosisResultToDashboard,
  closeBroadcastChannel
} from '@/utils/broadcastChannel'

export default {
  name: 'AutoDiagnosis',
  components: {
    ConfigStep,
    FileSelectStep,
    DiagnosisExecStep,
    ResultDisplayStep
  },
  data() {
    return {
      currentStep: 0,
      currentProcessStep: 0,
      isRunning: false,
      config: {
        dataPath: '',
        ameModel: '',
        diagnosisMode: 'realtime',
        autoDiagnosis: true,
        enableSimulation: false,
        electricalSpeed: null,
        mediumDensity: 850
      },
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
      featureMap: {},
      diagnosisResult: null,
      experimentData: [],
      simulationData: {},
      simulationVariables: [],
      dataFeatures: {
        rowCount: 0,
        columnCount: 0,
        columns: []
      },
      statusMessage: '等待启动',
      monitorTimer: null,
      dataTimer: null,
      heartbeatTimer: null,
      lastHeartbeat: 0,
      fileMonitorWorker: null,
      workerHeartbeatTimer: null,
      page: 0,
      pageSize: 500,
      featuresQueue: [],
      queueThreshold: 60,
      groupSize: 50,
      processedFiles: [],
      currentTaskId: null,
      modelOpened: false,
      dashboardWindow: null,
      dashboardOpened: false
    }
  },
  mounted() {
    document.addEventListener('visibilitychange', this.handleVisibilityChange)
  },
  beforeDestroy() {
    document.removeEventListener('visibilitychange', this.handleVisibilityChange)
    this.stopAllTimers()
    if (this.fileMonitorWorker) {
      this.fileMonitorWorker.postMessage({ type: 'STOP' })
      this.fileMonitorWorker.terminate()
      this.fileMonitorWorker = null
    }
    if (this.modelOpened) {
      closeModel().catch(() => {})
    }
    closeBroadcastChannel()
  },
  methods: {
    initFileMonitorWorker() {
      if (this.fileMonitorWorker) {
        return
      }
      
      try {
        const workerCode = `
let monitorTimer = null
let isRunning = false
let dataPath = ''
let checkInterval = 5000
let lastCheckTime = 0

self.onmessage = function(e) {
  const { type, payload } = e.data

  switch (type) {
    case 'START':
      startMonitor(payload)
      break
    case 'STOP':
      stopMonitor()
      break
    case 'UPDATE_CONFIG':
      updateConfig(payload)
      break
    case 'HEARTBEAT_CHECK':
      sendHeartbeat()
      break
    default:
      console.log('Unknown message type:', type)
  }
}

function startMonitor(config) {
  if (isRunning) {
    return
  }
  
  isRunning = true
  dataPath = config.dataPath || dataPath
  checkInterval = config.checkInterval || 5000
  
  self.postMessage({
    type: 'STATUS',
    payload: {
      status: 'started',
      message: '监控已启动',
      dataPath: dataPath,
      checkInterval: checkInterval
    }
  })

  checkNewFiles()
  
  monitorTimer = setInterval(() => {
    if (isRunning) {
      checkNewFiles()
    }
  }, checkInterval)
}

function stopMonitor() {
  isRunning = false
  
  if (monitorTimer) {
    clearInterval(monitorTimer)
    monitorTimer = null
  }
  
  self.postMessage({
    type: 'STATUS',
    payload: {
      status: 'stopped',
      message: '监控已停止'
    }
  })
}

function updateConfig(config) {
  if (config.dataPath) {
    dataPath = config.dataPath
  }
  if (config.checkInterval) {
    checkInterval = config.checkInterval
    if (isRunning && monitorTimer) {
      clearInterval(monitorTimer)
      monitorTimer = setInterval(() => {
        if (isRunning) {
          checkNewFiles()
        }
      }, checkInterval)
    }
  }
  
  self.postMessage({
    type: 'STATUS',
    payload: {
      status: 'config_updated',
      message: '配置已更新',
      dataPath: dataPath,
      checkInterval: checkInterval
    }
  })
}

function checkNewFiles() {
  lastCheckTime = Date.now()
  
  self.postMessage({
    type: 'CHECK_FILES',
    payload: {
      dataPath: dataPath,
      timestamp: lastCheckTime
    }
  })
}

function sendHeartbeat() {
  self.postMessage({
    type: 'HEARTBEAT',
    payload: {
      isRunning: isRunning,
      lastCheckTime: lastCheckTime,
      timestamp: Date.now()
    }
  })
}
`
        
        const blob = new Blob([workerCode], { type: 'application/javascript' })
        const workerUrl = URL.createObjectURL(blob)
        this.fileMonitorWorker = new Worker(workerUrl)
        
        this.fileMonitorWorker.onmessage = async (e) => {
          const { type, payload } = e.data
          
          switch (type) {
            case 'STATUS':
              this.addLog(`[Worker] ${payload.message}`, 'info')
              break
            case 'CHECK_FILES':
              await this.handleWorkerCheckFiles(payload)
              break
            case 'HEARTBEAT':
              this.lastHeartbeat = payload.timestamp
              break
            default:
              console.log('Unknown worker message:', type, payload)
          }
        }
        
        this.fileMonitorWorker.onerror = (error) => {
          this.addLog(`[Worker] 错误: ${error.message}`, 'error')
        }
        
        this.addLog('Web Worker 文件监控器已初始化', 'success')
      } catch (error) {
        this.addLog(`Web Worker 初始化失败: ${error.message}，将使用备用监控方式`, 'warn')
        this.fileMonitorWorker = null
      }
    },

    async handleWorkerCheckFiles(payload) {
      if (!this.isRunning) return
      
      try {
        const response = await newFileListAPI(payload.dataPath)
        const newFiles = response.new_files || []
        
        for (const filename of newFiles) {
          if (!this.processedFiles.includes(filename)) {
            this.processedFiles.push(filename)
            this.addLog(`检测到新文件: ${filename}`, 'info')
            await this.processFile(filename)
          }
        }
      } catch (error) {
        this.addLog('监控出错: ' + error.message, 'error')
      }
    },

    startWorkerHeartbeat() {
      this.lastHeartbeat = Date.now()
      this.workerHeartbeatTimer = setInterval(() => {
        if (this.fileMonitorWorker && this.isRunning) {
          this.fileMonitorWorker.postMessage({ type: 'HEARTBEAT_CHECK' })
        }
      }, 3000)
    },

    stopWorkerHeartbeat() {
      if (this.workerHeartbeatTimer) {
        clearInterval(this.workerHeartbeatTimer)
        this.workerHeartbeatTimer = null
      }
    },

    handleVisibilityChange() {
      if (document.visibilityState === 'visible') {
        this.addLog('页面重新可见，检查监控状态...', 'info')
        if (this.isRunning && this.config.diagnosisMode === 'realtime') {
          if (!this.fileMonitorWorker && !this.monitorTimer) {
            this.addLog('检测到监控已停止，重新启动监控', 'warn')
            this.restartRealtimeMonitor()
          }
        }
      } else {
        this.addLog('页面进入后台状态，Web Worker 将继续监控', 'info')
      }
    },

    restartRealtimeMonitor() {
      this.stopAllTimers()
      this.addLog('重新启动实时监控', 'info')
      
      if (this.fileMonitorWorker) {
        this.fileMonitorWorker.postMessage({
          type: 'START',
          payload: {
            dataPath: this.config.dataPath,
            checkInterval: 5000
          }
        })
        this.startWorkerHeartbeat()
      } else {
        this.startMonitorTimer()
        this.startHeartbeat()
      }
    },

    startMonitorTimer() {
      this.monitorTimer = setInterval(async () => {
        if (!this.isRunning) return
        this.lastHeartbeat = Date.now()
        try {
          const response = await newFileListAPI(this.config.dataPath)
          const newFiles = response.new_files || []
          
          for (const filename of newFiles) {
            if (!this.processedFiles.includes(filename)) {
              this.processedFiles.push(filename)
              this.addLog(`检测到新文件: ${filename}`, 'info')
              await this.processFile(filename)
            }
          }
        } catch (error) {
          this.addLog('监控出错: ' + error.message, 'error')
        }
      }, 5000)
    },

    startHeartbeat() {
      this.lastHeartbeat = Date.now()
      this.heartbeatTimer = setInterval(() => {
        if (this.isRunning) {
          this.lastHeartbeat = Date.now()
        }
      }, 3000)
    },

    addLog(message, level = 'info') {
      const now = new Date()
      const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`
      this.logs.push({ time, message, level })
      if (this.logs.length > 200) {
        this.logs.shift()
      }
      saveFrontendLog(message, level, 'autoDiagnosis').catch(() => {})
    },

    addVariable() {
      this.variableConfigs.push({ name: '', fileName: '' })
    },

    removeVariable(index) {
      if (this.variableConfigs.length > 1) {
        this.variableConfigs.splice(index, 1)
      }
    },

    async handleConfigNext() {
      if (!this.config.dataPath) {
        Message.warning('请输入试验数据路径')
        return
      }
      
      // 设置后端文件监控路径
      try {
        this.addLog(`正在设置监控路径: ${this.config.dataPath}`, 'info')
        await setWatchPath(this.config.dataPath)
        this.addLog('监控路径设置成功', 'success')
      } catch (error) {
        this.addLog('设置监控路径失败: ' + error.message, 'warn')
        // 继续流程，不阻断用户操作
      }
      
      if (this.config.diagnosisMode === 'file') {
        this.currentStep = 1
      } else {
        this.selectedFiles = []
        this.currentStep = 2
      }
    },

    async handleFileSelectNext() {
      if (this.selectedFiles.length === 0) {
        Message.warning('请选择至少一个文件')
        return
      }
      this.currentStep = 2
    },

    handleSkipFileSelect() {
      this.currentStep = 2
    },

    handleDiagnosisPrev() {
      if (this.config.diagnosisMode === 'realtime') {
        this.currentStep = 0
      } else {
        this.currentStep = 1
      }
    },

    async startDiagnosis() {
      this.isRunning = true
      this.currentProcessStep = 1
      this.statusMessage = '正在初始化...'
      this.addLog('开始自动诊断流程', 'info')

      try {
        if (this.config.enableSimulation && this.config.ameModel) {
          await this.initSimulation()
        }

        if (this.config.diagnosisMode === 'realtime') {
          await this.startRealtimeMode()
        } else {
          await this.startFileMode()
        }
      } catch (error) {
        this.addLog('诊断启动失败: ' + error.message, 'error')
        this.statusMessage = '启动失败'
        this.isRunning = false
        Message.error('诊断启动失败')
      }
    },

    async initSimulation() {
      this.addLog('正在初始化AMESim仿真环境...', 'info')
      try {
        await initAmesimApi()
        await openModel(this.config.ameModel)
        this.modelOpened = true
        this.addLog('AMESim模型加载成功', 'success')
      } catch (error) {
        this.addLog('AMESim初始化失败: ' + error.message, 'warn')
        this.config.enableSimulation = false
      }
    },

    async startRealtimeMode() {
      this.addLog('启动实时监控模式', 'info')
      this.statusMessage = '监控中 - 等待新文件...'
      this.currentProcessStep = 1

      initBroadcastChannel()
      this.addLog('BroadcastChannel 已初始化', 'info')

      if (!this.dashboardOpened) {
        const dashboardUrl = `${window.location.origin}/#/?mode=realtime&source=autoDiagnosis`
        this.dashboardWindow = window.open(dashboardUrl, '_blank')
        this.dashboardOpened = true
        this.addLog('已打开 Dashboard 展示页面', 'info')
      }

      sendStatusToDashboard({
        status: 'monitoring',
        message: '监控中 - 等待新文件...'
      })

      this.initFileMonitorWorker()
      
      if (this.fileMonitorWorker) {
        this.fileMonitorWorker.postMessage({
          type: 'START',
          payload: {
            dataPath: this.config.dataPath,
            checkInterval: 5000
          }
        })
        this.startWorkerHeartbeat()
        this.addLog('Web Worker 监控已启动（后台标签页不受影响）', 'success')
      } else {
        this.startMonitorTimer()
        this.startHeartbeat()
        this.addLog('备用监控定时器已启动', 'info')
      }
    },

    async startFileMode() {
      this.addLog(`启动文件处理模式，共 ${this.selectedFiles.length} 个文件`, 'info')
      
      for (const filename of this.selectedFiles) {
        if (!this.isRunning) break
        await this.processFile(filename)
      }

      if (this.isRunning) {
        this.currentProcessStep = 5
        this.statusMessage = '诊断完成'
        this.addLog('所有文件处理完成', 'success')
      }
    },

    async processFile(filename) {
      if (!this.isRunning) return
      
      this.currentProcessStep = 2
      this.statusMessage = `正在处理: ${filename}`
      this.addLog(`开始处理文件: ${filename}`, 'info')

      if (this.config.diagnosisMode === 'realtime') {
        sendStatusToDashboard({
          status: 'processing',
          message: `正在处理: ${filename}`,
          filename: filename
        })
      }

      try {
        this.currentTaskId = `${Date.now()}${Math.floor(Math.random() * 100000).toString().padStart(5, '0')}`
        
        if (this.config.autoDiagnosis && this.isRunning) {
          await createTask({
            task_id: this.currentTaskId,
            file_name: filename,
            path: this.config.dataPath,
            type: '1',
            fault: '1'
          })
        }

        if (!this.isRunning) return

        this.page = 0
        this.featuresQueue = []
        this.experimentData = []

        this.addLog(`开始加载文件数据: ${filename}`, 'info')
        await this.loadFileData(filename)
        this.addLog(`文件数据加载完成`, 'success')

        if (!this.isRunning) return

        if (this.config.enableSimulation && this.modelOpened) {
          this.currentProcessStep = 3
          this.statusMessage = '正在运行仿真...'
          await this.runSimulationAndGetData()
        } else {
          this.addLog('跳过仿真步骤（未启用仿真）', 'info')
        }

        if (!this.isRunning) return

        this.currentProcessStep = 4
        this.statusMessage = '正在诊断分析...'
        this.addLog('开始诊断分析...', 'info')
        
        if (this.config.autoDiagnosis) {
          await this.runDiagnosis(filename)
        }

        if (!this.isRunning) return

        this.currentProcessStep = 5
        this.addLog(`文件处理完成: ${filename}`, 'success')

        if (this.config.diagnosisMode === 'file' && this.isRunning) {
          this.currentStep = 3
          this.isRunning = false
        }
      } catch (error) {
        this.addLog(`处理文件失败 ${filename}: ${error.message}`, 'error')
      }
    },

    async loadFileData(filename) {
      let hasMoreData = true
      
      this.addLog(`loadFileData started for: ${filename}`, 'info')
      
      while (hasMoreData && this.isRunning) {
        if (this.featuresQueue.length >= this.queueThreshold) {
          await this.sleep(1000)
          continue
        }

        this.addLog(`Reading page ${this.page}...`, 'info')
        
        const response = await readExcelApi({
          page: this.page,
          page_size: this.pageSize,
          file_names: [filename],
          path: this.config.dataPath
        })

        this.addLog(`API response received`, 'info')
        console.log('loadFileData - API response:', response)

        const firstKey = Object.keys(response)[0]
        const res = response[firstKey]
        
        if (!res || !res.data) {
          this.addLog('No data in response, stopping', 'warn')
          hasMoreData = false
          break
        }
        
        const sheetName = Object.keys(res.data)[0]
        const dataRoot = res.data[sheetName]
        
        console.log('loadFileData - dataRoot:', dataRoot)
        console.log('loadFileData - available columns:', dataRoot ? Object.keys(dataRoot) : 'null')

        if (!dataRoot) {
          this.addLog('No sheet data found, stopping', 'warn')
          hasMoreData = false
          break
        }

        const fields = this.getDataFields()
        const allFieldData = {}
        const availableColumns = Object.keys(dataRoot)
        
        this.addLog(`Looking for ${fields.length} fields...`, 'info')
        this.addLog(`Available columns: ${availableColumns.join(', ')}`, 'info')
        
        for (const field of fields) {
          const arr = dataRoot[field]
          if (arr && Array.isArray(arr)) {
            allFieldData[field] = arr
          }
        }
        
        // 如果没有匹配到任何字段，尝试使用所有可用的数值列
        if (Object.keys(allFieldData).length === 0 && availableColumns.length > 0) {
          this.addLog('No predefined fields matched, using all available columns', 'warn')
          for (const col of availableColumns) {
            const arr = dataRoot[col]
            if (arr && Array.isArray(arr) && arr.length > 0) {
              allFieldData[col] = arr
            }
          }
        }

        console.log('loadFileData - matched fields:', Object.keys(allFieldData))
        this.addLog(`Matched ${Object.keys(allFieldData).length} fields`, 'info')

        const maxLen = Math.max(...Object.values(allFieldData).map(arr => arr.length || 0), 0)
        
        this.addLog(`maxLen: ${maxLen}`, 'info')
        
        if (maxLen === 0) {
          this.addLog('No data found in matched fields, stopping', 'warn')
          hasMoreData = false
          break
        }
        
        for (let i = 0; i < maxLen; i += this.groupSize) {
          const featureMap = {}
          for (const field of fields) {
            const arr = allFieldData[field] || []
            const group = arr.slice(i, i + this.groupSize)
              .map(v => v === 'nan' || v === null || v === undefined ? NaN : Number(v))
              .filter(v => typeof v === 'number' && !isNaN(v))
            
            if (group.length > 0) {
              featureMap[field] = {
                max: Math.max(...group),
                min: Math.min(...group),
                avg: group.reduce((a, b) => a + b, 0) / group.length
              }
            }
          }
          if (Object.keys(featureMap).length > 0) {
            this.featuresQueue.push(featureMap)
            this.experimentData.push(featureMap)
            if (this.config.diagnosisMode === 'realtime') {
              sendFeatureMapToDashboard(featureMap)
            }
          }
        }

        this.page++
        // 当返回的数据量小于pageSize时，说明已经读取完所有数据
        hasMoreData = maxLen >= this.pageSize
        
        this.addLog(`已读取第 ${this.page} 页数据，共 ${this.experimentData.length} 条记录，本页${maxLen}条`, 'info')
      }

      // 从experimentData中提取实际的字段名
      const actualColumns = this.experimentData.length > 0 
        ? Object.keys(this.experimentData[0]).map(name => ({ name, type: 'number' }))
        : []
      
      this.dataFeatures = {
        rowCount: this.experimentData.length,
        columnCount: actualColumns.length,
        columns: actualColumns
      }
      
      this.addLog(`文件数据加载完成，共 ${this.experimentData.length} 条特征数据，${actualColumns.length} 个字段`, 'success')
      console.log('loadFileData - dataFeatures:', this.dataFeatures)
    },

    async runSimulationAndGetData() {
      try {
        this.addLog('开始设置仿真参数...', 'info')
        await this.setSimulationParameters()
        this.addLog('仿真参数设置完成', 'success')

        await runSimulation()
        this.addLog('仿真运行完成', 'success')

        this.simulationData = {}
        this.simulationVariables = []
        
        for (const config of this.variableConfigs) {
          if (config.name.trim() && config.fileName.trim()) {
            try {
              const result = await readSimulationDataFile(config.fileName.trim())
              if (result && result.data) {
                const parsedData = this.parseSimulationDataFile(result.data, config.name.trim())
                this.simulationData[config.name.trim()] = parsedData
                this.simulationVariables.push(config.name.trim())
                this.addLog(`读取仿真文件 ${config.fileName}: ${parsedData.length} 条数据`, 'success')
              }
            } catch (err) {
              this.addLog(`读取仿真文件 ${config.fileName} 失败: ${err.message}`, 'warn')
            }
          }
        }
        
        const totalPoints = Object.values(this.simulationData).reduce((sum, arr) => sum + arr.length, 0)
        this.addLog(`仿真数据获取完成，共 ${this.simulationVariables.length} 个变量，${totalPoints} 条记录`, 'success')
      } catch (error) {
        this.addLog('仿真运行失败: ' + error.message, 'warn')
      }
    },

    async setSimulationParameters() {
      const fuelPumpSpeedData = this.getExperimentColumnData('燃油泵实际转速')
      const electricalSpeedData = this.getExperimentColumnData('电传实际转速')
      //this.addLog(fuelPumpSpeedData)
      //this.addLog(electricalSpeedData)
      if (fuelPumpSpeedData && fuelPumpSpeedData.length > 0) {
        const first10 = fuelPumpSpeedData.filter(v => !isNaN(v))
        if (first10.length > 0) {
          const avgSpeed = first10.reduce((a, b) => a + b, 0) / first10.length
          this.addLog(`计算燃油泵实际转速平均值: ${avgSpeed.toFixed(2)}`, 'info')
          await setComponentParameter('speed@pmover01', avgSpeed)
          this.addLog('已设置 speed@pmover01 参数', 'success')
        }
      }

      if (this.config.electricalSpeed) {
        const ordiamValues = this.getOrdiamValues(this.config.electricalSpeed)
        if (ordiamValues) {
          this.addLog(`电传转速 ${this.config.electricalSpeed} rpm，配置 ordiam 参数: ${ordiamValues.join('/')}`, 'info')
          await setComponentParameter('ordiam@flowcontrol01', ordiamValues[0])
          await setComponentParameter('ordiam@flowcontrol01_1', ordiamValues[1])
          await setComponentParameter('ordiam@flowcontrol01_2', ordiamValues[2])
          this.addLog('已设置三个流量控制阀 ordiam 参数', 'success')
        }
      }

      if (electricalSpeedData && electricalSpeedData.length > 0) {
        const filteredElectricalData = electricalSpeedData.filter(v => !isNaN(v))
        const avgElectricalSpeed = filteredElectricalData.reduce((a, b) => a + b, 0) / filteredElectricalData.length
        if (avgElectricalSpeed) {
          this.addLog(`使用电传实际转速平均值${avgElectricalSpeed.toFixed(2)}更新 input.data`, 'info')
          await writeInputData(Array(150).fill(avgElectricalSpeed))
          this.addLog('已更新 input.data 文件', 'success')
        }
      }
    },

    getOrdiamValues(speed) {
      const speedMap = {
        1295: [2, 2, 2],
        2999: [3, 5, 5],
        4975: [7, 10, 10],
        7958: [7, 7, 10],
        9990: [6.5, 7, 7]
      }
      return speedMap[speed] || null
    },

    getExperimentColumnData(columnName) {
      if (!this.experimentData || this.experimentData.length === 0) return null
      const allValues = []
      for (const record of this.experimentData) {
        if (record[columnName] !== undefined) {
          if (typeof record[columnName] === 'object' && record[columnName].avg !== undefined) {
            allValues.push(record[columnName].avg)
          } else if (typeof record[columnName] === 'number') {
            allValues.push(record[columnName])
          }
        }
      }
      return allValues
    },

    parseSimulationDataFile(rawData, variableName) {
      const lines = rawData.split('\n').filter(line => line.trim())
      const dataLines = lines.filter(line => !line.startsWith('#'))
      const allPoints = []

      for (const line of dataLines) {
        const parts = line.trim().split(/\s+/)
        if (parts.length >= 2) {
          const x = parseFloat(parts[0])
          const y = parseFloat(parts[1])
          if (!isNaN(x) && !isNaN(y)) {
            allPoints.push({ x, y })
          }
        }
      }

      const maxDataPoints = 300
      const sampledPoints = this.sampleDataPoints(allPoints, maxDataPoints)

      return sampledPoints.map(point => point.y)
    },

    sampleDataPoints(points, maxPoints) {
      if (points.length <= maxPoints) {
        return points
      }

      const result = []
      const step = points.length / maxPoints
      
      for (let i = 0; i < maxPoints; i++) {
        const index = Math.floor(i * step)
        result.push(points[index])
      }

      return result
    },

    async runDiagnosis(filename) {
      if (!this.isRunning) {
        this.addLog('诊断已停止，跳过诊断', 'warn')
        return
      }
      
      this.addLog(`开始诊断: ${filename}`, 'info')
      this.addLog(`任务ID: ${this.currentTaskId}`, 'info')
      
      try {
        const hasSimulationData = this.config.enableSimulation && 
          this.modelOpened && 
          Object.keys(this.simulationData).length > 0

        if (hasSimulationData && this.experimentData.length > 0) {
          this.addLog('检测到仿真数据，启动初步诊断（仿真 vs 试验对比）...', 'info')
          await this.runPreliminaryDiagnosis(filename)
        } else {
          this.addLog('无仿真数据或试验数据不足，跳过初步诊断，直接执行精确诊断', 'info')
          await this.runPreciseDiagnosis(filename)
        }
      } catch (error) {
        this.addLog('诊断失败: ' + error.message, 'error')
      }
    },

    async runPreliminaryDiagnosis(filename) {
      this.addLog('正在调用初步诊断API...', 'info')

      const payload = {
        task_id: this.currentTaskId,
        experiment_data: this.experimentData,
        simulation_data: this.simulationData,
        file_name: filename,
        path: this.config.dataPath,
        density: this.config.mediumDensity
      }

      const prelimResult = await preliminaryDiagnose(payload)
      this.addLog(`初步诊断完成: ${prelimResult.preliminary_conclusion}`, 'info')
      this.addLog(
        `对比变量: ${prelimResult.total_compared}个, ` +
        `超限: ${prelimResult.exceeded_count}个, ` +
        `阈值: ${prelimResult.exceeded_limit}个`,
        prelimResult.is_abnormal ? 'warn' : 'success'
      )

      if (prelimResult.is_abnormal) {
        if (prelimResult.precise_diagnosis_triggered) {
          this.addLog(`初步判定异常，后端已完成精确诊断，获取报告...`, 'warn')
          const report = await fetchReportPreview(this.currentTaskId)
          this.diagnosisResult = {
            taskId: this.currentTaskId,
            status: report.diagnosis && report.diagnosis.fault_name && report.diagnosis.fault_name.includes('异常') ? '异常' : '正常',
            timestamp: new Date().toLocaleString(),
            diagnosis: report.diagnosis,
            repairAdvice: report.repair_advice,
            indicators: report.indicators,
            productInfo: report.product_info
          }

          if (this.config.diagnosisMode === 'realtime') {
            sendDiagnosisResultToDashboard({
              taskId: this.currentTaskId,
              filename: filename,
              status: this.diagnosisResult.status,
              timestamp: this.diagnosisResult.timestamp,
              diagnosis: this.diagnosisResult.diagnosis,
              repairAdvice: this.diagnosisResult.repairAdvice,
              indicators: this.diagnosisResult.indicators
            })
          }

          if (this.diagnosisResult.status === '异常') {
            this.showAbnormalAlert(filename)
          }

          this.addLog(`诊断完成(初步异常→精确): ${filename}`, 'success')
        } else {
          this.addLog(`初步判定异常，但后端精确诊断失败: ${prelimResult.precise_error || '未知错误'}，尝试前端调用精确诊断...`, 'warn')
          await this.runPreciseDiagnosis(filename)
        }
      } else {
        this.addLog('初步判定正常，获取正常结果报告...', 'success')
        const report = await fetchReportPreview(this.currentTaskId)
        this.diagnosisResult = {
          taskId: this.currentTaskId,
          status: report.diagnosis && report.diagnosis.fault_name && report.diagnosis.fault_name.includes('异常') ? '异常' : '正常',
          timestamp: new Date().toLocaleString(),
          diagnosis: report.diagnosis,
          repairAdvice: report.repair_advice,
          indicators: report.indicators,
          productInfo: report.product_info
        }

        if (this.config.diagnosisMode === 'realtime') {
          sendDiagnosisResultToDashboard({
            taskId: this.currentTaskId,
            filename: filename,
            status: this.diagnosisResult.status,
            timestamp: this.diagnosisResult.timestamp,
            diagnosis: this.diagnosisResult.diagnosis,
            repairAdvice: this.diagnosisResult.repairAdvice,
            indicators: this.diagnosisResult.indicators
          })
        }

        this.addLog(`诊断完成(初步-正常): ${filename}`, 'success')
      }
    },

    async runPreciseDiagnosis(filename) {
      this.addLog('正在调用精确诊断API...', 'info')
      await diagnose(this.currentTaskId, this.config.dataPath, filename, this.config.mediumDensity)
      this.addLog('精确诊断API调用成功，等待结果...', 'info')
      
      let attempts = 0
      const maxAttempts = 60
      
      while (attempts < maxAttempts && this.isRunning) {
        this.addLog(`检查诊断状态 (尝试 ${attempts + 1}/${maxAttempts})`, 'info')
        const status = await getJobStatus(this.currentTaskId)
        this.addLog(`当前状态: ${status.status}`, 'info')
        
        if (status.status === 'Completed') {
          this.addLog('精确诊断完成，获取报告...', 'info')
          const report = await fetchReportPreview(this.currentTaskId)
          this.diagnosisResult = {
            taskId: this.currentTaskId,
            status: report.diagnosis && report.diagnosis.fault_name && report.diagnosis.fault_name.includes('异常') ? '异常' : '正常',
            timestamp: new Date().toLocaleString(),
            diagnosis: report.diagnosis,
            repairAdvice: report.repair_advice,
            indicators: report.indicators,
            productInfo: report.product_info
          }
          
          if (this.config.diagnosisMode === 'realtime') {
            sendDiagnosisResultToDashboard({
              taskId: this.currentTaskId,
              filename: filename,
              status: this.diagnosisResult.status,
              timestamp: this.diagnosisResult.timestamp,
              diagnosis: this.diagnosisResult.diagnosis,
              repairAdvice: this.diagnosisResult.repairAdvice,
              indicators: this.diagnosisResult.indicators
            })
          }
          
          if (this.diagnosisResult.status === '异常') {
            this.showAbnormalAlert(filename)
          }
          
          this.addLog(`诊断完成(精确): ${filename}`, 'success')
          break
        }
        attempts++
        await this.sleep(2000)
      }
      
      if (attempts >= maxAttempts) {
        this.addLog('诊断超时，请检查后端服务', 'warn')
      }
    },

    showAbnormalAlert(filename) {
      this.$notify({
        title: '异常警告',
        message: `文件 ${filename} 检测到异常，请查看诊断结果`,
        type: 'warning',
        duration: 0
      })
    },

    stopDiagnosis() {
      this.isRunning = false
      this.stopAllTimers()
      if (this.fileMonitorWorker) {
        this.fileMonitorWorker.postMessage({ type: 'STOP' })
      }
      this.currentProcessStep = 0
      this.statusMessage = '已停止'
      this.addLog('诊断流程已停止', 'warn')
      Message.info('诊断已停止')
      
      sendStatusToDashboard({
        status: 'stopped',
        message: '诊断已停止'
      })
      
      if (this.diagnosisResult) {
        this.currentStep = 3
      }
    },

    stopAllTimers() {
      if (this.monitorTimer) {
        clearInterval(this.monitorTimer)
        this.monitorTimer = null
      }
      if (this.dataTimer) {
        clearInterval(this.dataTimer)
        this.dataTimer = null
      }
      if (this.heartbeatTimer) {
        clearInterval(this.heartbeatTimer)
        this.heartbeatTimer = null
      }
      this.stopWorkerHeartbeat()
    },

    handleDiagnosisComplete() {
      this.currentStep = 3
    },

    handleRestart() {
      this.currentStep = 0
      this.currentProcessStep = 0
      this.isRunning = false
      this.logs = []
      this.featureMap = {}
      this.diagnosisResult = null
      this.experimentData = []
      this.simulationData = {}
      this.simulationVariables = []
      this.processedFiles = []
      this.statusMessage = '等待启动'
    },

    async viewReport(taskId) {
      try {
        const report = await fetchReportPreview(taskId)
        this.diagnosisResult = {
          taskId: taskId,
          status: report.diagnosis && report.diagnosis.fault_name && report.diagnosis.fault_name.includes('异常') ? '异常' : '正常',
          timestamp: new Date().toLocaleString(),
          diagnosis: report.diagnosis,
          repairAdvice: report.repair_advice,
          indicators: report.indicators,
          productInfo: report.product_info
        }
        Message.success('报告已加载')
      } catch (error) {
        Message.error('加载报告失败')
      }
    },

    downloadReport(taskId) {
      if (taskId) {
        downloadFile(taskId)
      }
    },

    getDataFields() {
      return [
        '燃油泵实际转速', '电传实际转速', '电传扭矩',
        'P1进口压力', 'P17滑油压力', 'P18回油工况模拟供油压力',
        'P2低压出口压力', 'P3高压出口压力',
        '供油压力1-1', '供油压力1-2',
        '回油压力1-2', '回油压力1-1', '回油压力2-2', '回油压力2-1',
        '回油流量1-2', '回油流量2-2', '回油流量2-1', '回油流量1-1',
        '供油流量1-1', '供油流量1-2',
        'T20加热出口温度', 'T3进口温度', 'T4高压出口温度', 'T5出口温度',
        '供油温度1-1', '供油温度1-2',
        '回油温度2-2', '回油温度2-1', '回油温度1-2', '回油温度1-1',
        '振动传感器1-1', '振动传感器2-1', '振动传感器3-1'
      ]
    },

    sleep(ms) {
      return new Promise(resolve => setTimeout(resolve, ms))
    }
  }
}
</script>

<style scoped>
.auto-diagnosis-container {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
  overflow-y: auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
  margin: 0;
}

.steps-card {
  margin-bottom: 20px;
}

.step-content {
  min-height: calc(100vh - 250px);
  overflow-y: auto;
  padding-bottom: 20px;
}
</style>
