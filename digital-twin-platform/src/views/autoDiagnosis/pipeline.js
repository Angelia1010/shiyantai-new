/**
 * “文件处理”模式下单个数据文件的诊断流程（实时模式由后端在文件写完后自动诊断，不经过这里）：
 *
 *   1. 创建任务（开启“自动诊断”时）
 *   2. 分页读取文件，计算特征帧（用于结果页图表和仿真输入）
 *   3. 运行 AMESim 仿真（开启“系统仿真”时）：用试验数据设置模型参数，读回仿真结果
 *   4. 诊断：后端做流量计互校、质量-体积校核、传感器自检；有仿真数据时附上仿真对比
 *
 * 页面组件只负责状态展示，流程逻辑都在这里。
 */
import { createTask, diagnoseTask, preliminaryDiagnose } from '@/api/tasks'
import { readFilePage } from '@/api/files'
import * as amesim from '@/api/amesim'
import { buildFeatureFrames, framesToSeries, mean, pickFields } from '@/utils/features'

const PAGE_SIZE = 500
const SIMULATION_SAMPLE_POINTS = 300
const INPUT_DATA_POINTS = 150

// AMESim 模型参数
const PUMP_SPEED_PARAM = 'speed@pmover01'
const ORDIAM_PARAMS = ['ordiam@flowcontrol01', 'ordiam@flowcontrol01_1', 'ordiam@flowcontrol01_2']
// 电传转速档位（rpm）→ 三个流量控制阀的 ordiam 参数。
// 原来按工况编号（1295/2999/4975/7958/9990）配置，实测这些工况的电传转速约为 1000/1500/2000/2500/3000 rpm
export const ORDIAM_BY_SPEED_LEVEL = {
  1000: [2, 2, 2],
  1500: [3, 5, 5],
  2000: [7, 10, 10],
  2500: [7, 7, 10],
  3000: [6.5, 7, 7]
}

/** 实测电传转速 → 最接近的档位 */
export function nearestSpeedLevel(speed) {
  if (speed === null || speed === undefined) return null
  return Number(Object.keys(ORDIAM_BY_SPEED_LEVEL).reduce((best, level) =>
    Math.abs(level - speed) < Math.abs(best - speed) ? level : best))
}

export class Cancelled extends Error {
  constructor() {
    super('诊断已停止')
  }
}

/** 解析 AMESim 的 .data 文本（“# 注释”行 + 两列数值），返回均匀抽样后的 Y 值。 */
export function parseSimulationData(text, maxPoints = SIMULATION_SAMPLE_POINTS) {
  const ys = []
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const [x, y] = trimmed.split(/\s+/).map(Number)
    if (!Number.isNaN(x) && !Number.isNaN(y)) ys.push(y)
  }
  if (ys.length <= maxPoints) return ys
  const step = ys.length / maxPoints
  return Array.from({ length: maxPoints }, (_, i) => ys[Math.floor(i * step)])
}

export class DiagnosisPipeline {
  /**
   * @param {object} options
   * @param {object} options.config           自动诊断配置
   * @param {Array}  options.variableConfigs  [{ name: 试验变量名, fileName: 仿真结果 .data 文件 }]
   * @param {Function} options.log            (message, level) => void
   * @param {Function} options.onStep         (step: 1-5, message) => void
   * @param {Function} options.isCancelled    () => boolean
   */
  constructor({ config, variableConfigs, log, onStep, isCancelled }) {
    this.config = config
    this.variableConfigs = variableConfigs
    this.log = log
    this.onStep = onStep
    this.isCancelled = isCancelled
    this.modelOpened = false
  }

  checkCancelled() {
    if (this.isCancelled()) throw new Cancelled()
  }

  /** 开启仿真时初始化 AMESim 并打开模型；失败则本次运行不做仿真。 */
  async prepare() {
    if (!this.config.enableSimulation || !this.config.ameModel) return
    this.log('正在初始化 AMESim 仿真环境...', 'info')
    try {
      await amesim.initAmesim()
      await amesim.openModel(this.config.ameModel)
      this.modelOpened = true
      this.log(`AMESim 模型 ${this.config.ameModel} 加载成功`, 'success')
    } catch (e) {
      this.log('AMESim 初始化失败，本次将跳过仿真步骤', 'warn')
    }
  }

  async close() {
    if (this.modelOpened) {
      this.modelOpened = false
      await amesim.closeModel().catch(() => {})
    }
  }

  /** 处理一个文件，返回 { taskId, report, experimentSeries, simulationData } */
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

    let simulationData = {}
    if (this.modelOpened) {
      this.checkCancelled()
      this.onStep(3, '正在运行仿真...')
      simulationData = await this.simulate(experimentSeries)
    }

    let report = null
    if (taskId) {
      this.checkCancelled()
      this.onStep(4, '正在诊断分析...')
      report = await this.diagnose(taskId, experimentSeries, simulationData)
    }
    this.onStep(5, `处理完成: ${fileName}`)
    return { taskId, report, experimentSeries, simulationData }
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

  async simulate(experimentSeries) {
    const pumpSpeed = mean(experimentSeries['燃油泵实际转速'])
    if (pumpSpeed !== null) {
      await amesim.setComponentParameter(PUMP_SPEED_PARAM, pumpSpeed)
      this.log(`已按燃油泵实际转速均值 ${pumpSpeed.toFixed(2)} 设置 ${PUMP_SPEED_PARAM}`, 'info')
    }

    // 阀开度：配置页手动选了档位就用它，否则按实测电传转速自动选最接近的档位
    const electricalSpeed = mean(experimentSeries['电传实际转速'])
    const level = this.config.electricalSpeed || nearestSpeedLevel(electricalSpeed)
    const ordiam = ORDIAM_BY_SPEED_LEVEL[level]
    if (ordiam) {
      for (let i = 0; i < ORDIAM_PARAMS.length; i++) {
        await amesim.setComponentParameter(ORDIAM_PARAMS[i], ordiam[i])
      }
      this.log(`电传转速档位 ${level} rpm${this.config.electricalSpeed ? '（手动）' : '（按实测自动）'}，` +
        `ordiam 参数设为 ${ordiam.join('/')}`, 'info')
    }

    if (electricalSpeed !== null) {
      await amesim.writeInputData(Array(INPUT_DATA_POINTS).fill(electricalSpeed))
      this.log(`已按电传实际转速均值 ${electricalSpeed.toFixed(2)} 更新 input.data`, 'info')
    }

    await amesim.runSimulation()
    this.log('仿真运行完成', 'success')

    const simulationData = {}
    for (const { name, fileName } of this.variableConfigs) {
      if (!name.trim() || !fileName.trim()) continue
      try {
        const { data } = await amesim.readDataFile(fileName.trim())
        simulationData[name.trim()] = parseSimulationData(data)
      } catch (e) {
        this.log(`读取仿真结果 ${fileName} 失败`, 'warn')
      }
    }
    this.log(`仿真结果读取完成，共 ${Object.keys(simulationData).length} 个变量`, 'success')
    return simulationData
  }

  async diagnose(taskId, experimentSeries, simulationData) {
    const density = this.config.mediumDensity || null // 留空时后端按油温计算
    const comparable = Object.keys(simulationData).filter(name => name in experimentSeries)
    if (comparable.length) {
      this.log('执行诊断，并附上与仿真数据的对比...', 'info')
      const { preliminary, report } = await preliminaryDiagnose(taskId, {
        experiment_data: experimentSeries,
        simulation_data: simulationData,
        density
      })
      this.log(`仿真对比：${preliminary.conclusion}`, preliminary.is_abnormal ? 'warn' : 'success')
      return report
    }
    this.log('执行诊断（流量计互校、质量-体积校核、传感器自检）...', 'info')
    return diagnoseTask(taskId, density)
  }
}
