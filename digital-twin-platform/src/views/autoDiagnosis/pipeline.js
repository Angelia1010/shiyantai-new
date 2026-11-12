/**
 * “文件处理”模式下单个数据文件的诊断流程（实时模式由后端在文件写完后自动诊断，不经过这里）：
 *
 *   1. 创建任务（开启“自动诊断”时）
 *   2. 分页读取文件，计算特征帧（用于结果页图表）
 *   3. 诊断：后端做流量计互校、质量-体积校核、传感器自检，以及与仿真模型预期值的比较
 *      （仿真在后端进行：按实测工况查仿真基准表，见“仿真模型”页）
 *
 * 页面组件只负责状态展示，流程逻辑都在这里。
 */
import { createTask, diagnoseTask } from '@/api/tasks'
import { readFilePage } from '@/api/files'
import { buildFeatureFrames, framesToSeries, pickFields } from '@/utils/features'

const PAGE_SIZE = 500

export class Cancelled extends Error {
  constructor() {
    super('诊断已停止')
  }
}

export class DiagnosisPipeline {
  /**
   * @param {object} options
   * @param {object} options.config           自动诊断配置
   * @param {Function} options.log            (message, level) => void
   * @param {Function} options.onStep         (step: 1-5, message) => void
   * @param {Function} options.isCancelled    () => boolean
   */
  constructor({ config, log, onStep, isCancelled }) {
    this.config = config
    this.log = log
    this.onStep = onStep
    this.isCancelled = isCancelled
  }

  checkCancelled() {
    if (this.isCancelled()) throw new Cancelled()
  }

  async prepare() {}

  async close() {}

  /** 处理一个文件，返回 { taskId, report, experimentSeries } */
  async processFile(fileName) {
    const { config } = this
    let taskId = null
    if (config.autoDiagnosis) {
      const mode = config.diagnosisMode === 'realtime' ? 'realtime' : 'file'
      taskId = (await createTask(config.dataPath, fileName, mode)).task_id
      this.log(`已创建任务 ${taskId}`, 'info')
    }

    this.onStep(2, `正在读取: ${fileName}`)
    const frames = await this.loadFrames(fileName)
    const experimentSeries = framesToSeries(frames)
    this.log(`数据读取完成，共 ${frames.length} 组特征、${Object.keys(experimentSeries).length} 个变量`, 'success')

    let report = null
    if (taskId) {
      this.checkCancelled()
      this.onStep(3, '正在诊断分析（含仿真模型对比）...')
      const density = this.config.mediumDensity || null // 当前燃油 20 ℃ 密度，留空时后端用诊断设置
      report = await diagnoseTask(taskId, density)
      const model = report.model
      if (model && model.available) {
        this.log(`仿真模型对比：${model.model}，工况 ${Object.entries(model.condition)
          .map(([k, v]) => `${k} ${Number(v).toFixed(v >= 100 ? 0 : 2)}`).join('、')}`, 'info')
      } else if (model) {
        this.log(`仿真模型对比未进行：${(model.notes || []).join('；') || '工况不完整'}`, 'warn')
      }
    }
    this.onStep(5, `处理完成: ${fileName}`)
    return { taskId, report, experimentSeries }
  }

  async loadFrames(fileName) {
    const frames = []
    let fields = null
    for (let page = 0; ; page++) {
      this.checkCancelled()
      const data = await readFilePage(this.config.dataPath, fileName, page, PAGE_SIZE)
      fields = fields || pickFields(data.columns)
      const pageFrames = buildFeatureFrames(data.columns, fields, this.config.groupSize)
      frames.push(...pageFrames)
      if (!data.has_more) break
    }
    return frames
  }
}
