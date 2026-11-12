<template>
  <div class="app-container simulation-page">
    <div class="page-header">
      <h2 class="page-title">仿真模型</h2>
      <span class="page-sub">健康参考模型：给定工况，给出健康系统各测点的预期值。诊断时与实测比较，发现各表一致但整体偏离、以及没有冗余表的测点问题。</span>
    </div>

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card shadow="never" class="box-card">
          <div slot="header" class="card-head">
            <span>当前模型与仿真基准表</span>
            <div>
              <el-button v-if="table && !table.is_default" size="mini" @click="reset">恢复默认表</el-button>
              <el-button size="mini" type="primary" :disabled="running" @click="openBuild">重建基准表</el-button>
            </div>
          </div>
          <div v-if="loading" class="muted">加载中...</div>
          <template v-else-if="table">
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="模型">
                <el-tag size="mini" :type="table.model.type === 'amesim' ? 'success' : ''">{{ table.model.label }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="建立时间">{{ table.created }}</el-descriptions-item>
              <el-descriptions-item label="工况网格" :span="2">
                <span v-for="i in table.inputs" :key="i.name" class="grid-item">
                  {{ i.name }}（{{ i.column }}）：{{ i.grid.join(' / ') }} {{ i.unit }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="标定" :span="2">
                {{ table.calibration.files }} 个正常数据文件，{{ table.calibration.method }}
              </el-descriptions-item>
              <el-descriptions-item label="来源" :span="2">
                {{ table.is_default ? '随代码提供的默认表（2026-11 正常数据）' : table.source }}
              </el-descriptions-item>
            </el-descriptions>
            <el-alert
              v-if="table.model.type === 'surrogate'"
              class="note"
              type="info"
              :closable="false"
              show-icon
              title="当前是由正常数据拟合的数据代理模型，用于在 AMESim 模型接入前跑通整套流程。它只学到了健康数据的规律，能发现偏离健康规律的情况，但不能模拟没见过的部件故障。接入 AMESim 后在此重建基准表即可切换。"
            />
          </template>
          <el-empty v-else description="还没有仿真基准表" :image-size="80" />

          <div v-if="job.state === 'running'" class="job">
            <div class="muted">正在建立基准表：{{ job.stage }} {{ job.total ? `${job.done}/${job.total}` : '' }}</div>
            <el-progress :percentage="jobPercent" :stroke-width="10" />
          </div>
          <el-alert v-else-if="job.state === 'failed'" class="note" type="error" :closable="false" :title="`上次建立失败：${job.error}`" />
        </el-card>

        <el-card v-if="table" shadow="never" class="box-card">
          <div slot="header">标定结果（模型 vs 正常数据）</div>
          <div class="muted small">
            固有偏差：正常时该测点比模型预期高/低多少，诊断时先扣除；离散σ：扣除后的波动，决定阈值（预警 = max(下限, 3σ)）。
            σ 越小，模型能发现的偏离越小。
          </div>
          <el-table :data="table.calibration.columns" size="small" border max-height="360">
            <el-table-column prop="column" label="测点" min-width="120" />
            <el-table-column prop="output" label="模型输出" min-width="100" />
            <el-table-column label="固有偏差" width="90" align="right">
              <template slot-scope="{ row }">{{ pct(row.bias) }}</template>
            </el-table-column>
            <el-table-column label="离散σ" width="80" align="right">
              <template slot-scope="{ row }">{{ (row.std * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="预警 / 异常" width="120" align="right">
              <template slot-scope="{ row }">±{{ (row.warn * 100).toFixed(1) }}% / ±{{ (row.alarm * 100).toFixed(1) }}%</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card shadow="never" class="box-card">
          <div slot="header">工况试算</div>
          <el-form v-if="table" size="small" label-width="80px" @submit.native.prevent>
            <el-form-item v-for="i in table.inputs" :key="i.name" :label="i.name">
              <el-input-number v-model="condition[i.name]" :step="stepOf(i)" :precision="precisionOf(i)" controls-position="right" />
              <span class="unit">{{ i.unit }}</span>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="runPredict">计算预期值</el-button>
            </el-form-item>
          </el-form>
          <el-alert v-if="prediction && prediction.outside.length" type="warning" :closable="false"
                    :title="`超出基准表范围：${prediction.outside.join('、')}`" />
          <el-table v-if="prediction" :data="prediction.expected" size="small" border>
            <el-table-column prop="name" label="模型输出" />
            <el-table-column label="预期值" align="right">
              <template slot-scope="{ row }">{{ fmt(row.value, row.unit) }}</template>
            </el-table-column>
          </el-table>
          <div v-show="curve.length" ref="curve" class="curve" />
        </el-card>

        <el-card shadow="never" class="box-card">
          <div slot="header">仿真动画</div>
          <video class="video" controls preload="metadata" :src="videoSrc">您的浏览器不支持视频播放。</video>
          <div class="muted small">涡轮流量计 AMESim 仿真录屏（示意），不随本次计算变化。</div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog title="重建仿真基准表" :visible.sync="build.visible" width="520px">
      <el-form label-width="110px" size="small">
        <el-form-item label="模型">
          <el-radio-group v-model="build.model">
            <el-radio label="surrogate">数据代理模型</el-radio>
            <el-radio label="amesim" :disabled="!amesimReady">AMESim 模型</el-radio>
          </el-radio-group>
          <div v-if="!amesimReady" class="muted small">AMESim：simulation.json 的 amesim 段还有“待填写”项，补全并启动 AMESim 服务后可用</div>
        </el-form-item>
        <el-form-item label="正常数据目录">
          <el-autocomplete v-model="build.path" :fetch-suggestions="suggestDirs" placeholder="设备正常时采集的数据目录" style="width: 100%" />
          <div class="muted small">用于{{ build.model === 'surrogate' ? '拟合代理模型并' : '' }}标定；目录需已在“数据目录”中登记，子目录会一起读取</div>
        </el-form-item>
      </el-form>
      <span slot="footer">
        <el-button @click="build.visible = false">取消</el-button>
        <el-button type="primary" :disabled="!build.path" @click="startBuild">开始建立</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import { getDataDirs } from '@/api/files'
import { buildSimulationTable, getSimulationStatus, predictSimulation, resetSimulationTable } from '@/api/simulation'
import { errorMessage } from '@/utils/request'

const DEFAULT_CONDITION = { 电传转速: 2000, 进口压力: 0.15, 油温: 36 }

export default {
  name: 'Simulation',
  data() {
    return {
      loading: true,
      status: null,
      job: { state: 'idle' },
      condition: {},
      prediction: null,
      curve: [],
      build: { visible: false, model: 'surrogate', path: '' },
      videoSrc: `${process.env.BASE_URL}videos/涡轮流量计仿真2.mp4`
    }
  },
  computed: {
    table() {
      return this.status && this.status.table
    },
    amesimReady() {
      return !!(this.status && this.status.config.amesim_ready)
    },
    running() {
      return this.job.state === 'running'
    },
    jobPercent() {
      return this.job.total ? Math.round((this.job.done / this.job.total) * 100) : 0
    }
  },
  created() {
    this.load()
  },
  beforeDestroy() {
    clearTimeout(this.timer)
    window.removeEventListener('resize', this.resize)
    if (this.chart) this.chart.dispose()
  },
  methods: {
    pct(v) {
      return `${v > 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
    },
    fmt(v, unit) {
      return `${unit === 'MPa' ? v.toFixed(3) : v.toFixed(1)} ${unit}`
    },
    stepOf(i) {
      return i.unit === 'MPa' ? 0.01 : i.unit === 'rpm' ? 100 : 1
    },
    precisionOf(i) {
      return i.unit === 'MPa' ? 3 : 0
    },
    async load() {
      try {
        this.status = await getSimulationStatus()
        this.job = this.status.job || { state: 'idle' }
        if (this.table && !Object.keys(this.condition).length) {
          const c = {}
          for (const i of this.table.inputs) {
            c[i.name] = i.name in DEFAULT_CONDITION ? DEFAULT_CONDITION[i.name] : i.grid[Math.floor(i.grid.length / 2)]
          }
          this.condition = c
          this.runPredict()
        }
      } finally {
        this.loading = false
      }
      if (this.running) this.timer = setTimeout(this.load, 1000)
    },
    openBuild() {
      this.build = { visible: true, model: this.table ? this.table.model.type : 'surrogate', path: '' }
    },
    async suggestDirs(query, callback) {
      try {
        const { preset, registered } = await getDataDirs()
        const keyword = (query || '').toLowerCase()
        callback([...registered, ...preset].filter(d => !keyword || d.toLowerCase().includes(keyword)).map(value => ({ value })))
      } catch (e) {
        callback([])
      }
    },
    async startBuild() {
      try {
        this.job = await buildSimulationTable(this.build.path, this.build.model)
        this.build.visible = false
        this.$message.info('已开始建立仿真基准表')
        this.prediction = null
        this.condition = {}
        this.timer = setTimeout(this.load, 800)
      } catch (e) {
        this.$message.error(errorMessage(e))
      }
    },
    async reset() {
      try {
        await this.$confirm('删除重建的基准表，恢复使用随代码提供的默认表？', '恢复默认', { type: 'warning' })
      } catch (e) {
        return
      }
      this.status = await resetSimulationTable()
      this.condition = {}
      this.load()
    },
    async runPredict() {
      try {
        this.prediction = await predictSimulation(this.condition)
        await this.loadCurve()
      } catch (e) {
        this.$message.error(errorMessage(e))
      }
    },
    /** 系统流量随电传转速的模型曲线（其余输入取当前值） */
    async loadCurve() {
      const speed = this.table.inputs[0]
      const lo = Math.min(...speed.grid)
      const hi = Math.max(...speed.grid)
      const xs = Array.from({ length: 11 }, (_, k) => lo + ((hi - lo) * k) / 10)
      const results = await Promise.all(xs.map(x => predictSimulation({ ...this.condition, [speed.name]: x })))
      const flowName = this.table.outputs[0].name
      this.curve = xs.map((x, k) => [x, (results[k].expected.find(e => e.name === flowName) || {}).value])
      this.$nextTick(() => this.drawCurve(speed, flowName))
    },
    drawCurve(speed, flowName) {
      if (!this.chart) {
        this.chart = echarts.init(this.$refs.curve)
        window.addEventListener('resize', this.resize)
      }
      const unit = this.table.outputs[0].unit
      const current = this.condition[speed.name]
      const now = this.prediction.expected.find(e => e.name === flowName)
      this.chart.setOption({
        title: { text: `${flowName}随${speed.name}的模型曲线`, left: 0, textStyle: { fontSize: 13, fontWeight: 'normal' } },
        grid: { left: 50, right: 20, top: 36, bottom: 36 },
        tooltip: { trigger: 'axis', formatter: p => `${speed.name} ${p[0].value[0].toFixed(0)} ${speed.unit}<br/>${flowName} ${p[0].value[1].toFixed(1)} ${unit}` },
        xAxis: { type: 'value', name: speed.unit, min: Math.min(...speed.grid), max: Math.max(...speed.grid), splitLine: { show: false } },
        yAxis: { type: 'value', name: unit, splitLine: { lineStyle: { color: '#f0f0f0' } } },
        series: [{
          type: 'line',
          data: this.curve,
          showSymbol: false,
          lineStyle: { color: '#9ca3af', width: 2 },
          markPoint: now ? {
            symbol: 'circle',
            symbolSize: 9,
            itemStyle: { color: '#2563eb' },
            label: { show: true, position: 'top', formatter: `${now.value.toFixed(1)} ${unit}`, color: '#2563eb' },
            data: [{ coord: [current, now.value] }]
          } : undefined
        }]
      }, true)
    },
    resize() {
      if (this.chart) this.chart.resize()
    }
  }
}
</script>

<style scoped>
.page-header {
  margin-bottom: 12px;
}
.page-sub {
  display: block;
  margin-top: 4px;
  font-size: 13px;
  color: #909399;
}
.box-card {
  margin-bottom: 16px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.grid-item {
  display: block;
  line-height: 1.8;
}
.note {
  margin-top: 12px;
}
.job {
  margin-top: 12px;
}
.muted {
  color: #909399;
}
.small {
  font-size: 12px;
  line-height: 1.7;
  margin-bottom: 8px;
}
.unit {
  margin-left: 8px;
  color: #909399;
}
.curve {
  width: 100%;
  height: 240px;
  margin-top: 12px;
}
.video {
  width: 100%;
  border-radius: 4px;
  background: #000;
}
</style>
