<template>
  <div class="app-container simulation-page">
    <div class="page-header">
      <h2 class="page-title">仿真模型</h2>
      <span class="page-sub">
        每个模型是试验台一部分的健康参考：给定工况，给出健康时各测点的预期值。每个模型各有一张仿真基准表并用正常数据标定，
        诊断时按“诊断方案”决定哪些模型参与结论。
      </span>
    </div>

    <el-card shadow="never" class="box-card">
      <div slot="header" class="card-head">
        <span>诊断方案 <span class="muted small-inline">自动诊断与手动诊断共用；手动诊断时可在“自动诊断”页临时调整</span></span>
        <el-button size="mini" type="primary" :disabled="!profileDirty" @click="saveProfile">保存方案</el-button>
      </div>
      <el-table v-loading="loading" :data="models" size="small" border>
        <el-table-column label="模型" min-width="200">
          <template slot-scope="{ row }">
            <b>{{ row.name }}</b>
            <div class="muted small">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="基准表" min-width="170">
          <template slot-scope="{ row }">
            <template v-if="row.table">
              {{ row.table.model.label }}
              <div class="muted small">{{ row.table.is_default ? '默认表' : '重建于' }} {{ row.table.created }}</div>
            </template>
            <span v-else class="warn">还没有基准表</span>
          </template>
        </el-table-column>
        <el-table-column label="参与方式" width="130">
          <template slot-scope="{ row }">
            <el-select v-model="profile[row.id].mode" size="mini" @change="profileDirty = true">
              <el-option v-for="(label, value) in MODE_LABELS" :key="value" :label="label" :value="value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="预警 / 异常倍数（σ）" width="220">
          <template slot-scope="{ row }">
            <el-input-number v-model="profile[row.id].sigma_warn" size="mini" :min="1" :max="20" :step="0.5"
                             controls-position="right" style="width: 90px" @change="profileDirty = true" />
            /
            <el-input-number v-model="profile[row.id].sigma_alarm" size="mini" :min="1" :max="20" :step="0.5"
                             controls-position="right" style="width: 90px" @change="profileDirty = true" />
          </template>
        </el-table-column>
      </el-table>
      <div class="muted small note">
        参与结论：偏离超过阈值时判预警/异常；仅作参考：只写进报告，不影响结论；关闭：不做该模型的对比。
        阈值 = max(下限, 倍数 × 标定离散 σ)，倍数越大越不容易报。
      </div>
    </el-card>

    <el-tabs v-model="activeId" type="border-card" class="model-tabs">
      <el-tab-pane v-for="m in models" :key="m.id" :name="m.id" :label="m.name">
        <el-row :gutter="16">
          <el-col :span="14">
            <div class="section">
              <div class="section-head">
                <span>基准表</span>
                <div>
                  <el-button v-if="m.table && !m.table.is_default" size="mini" :disabled="running" @click="reset(m)">恢复默认表</el-button>
                  <el-button size="mini" type="primary" :disabled="running" @click="openBuild(m)">重建基准表</el-button>
                </div>
              </div>
              <template v-if="m.table">
                <el-descriptions :column="2" size="small" border>
                  <el-descriptions-item label="模型">
                    <el-tag size="mini">{{ m.table.model.label }}</el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="建立时间">{{ m.table.created }}</el-descriptions-item>
                  <el-descriptions-item label="工况网格" :span="2">
                    <span v-for="i in m.table.inputs" :key="i.name" class="grid-item">
                      {{ i.name }}（{{ i.source }}）：{{ i.grid.join(' / ') }} {{ i.unit }}
                    </span>
                  </el-descriptions-item>
                  <el-descriptions-item label="三维部件" :span="2">{{ m.components.join('、') }}</el-descriptions-item>
                  <el-descriptions-item label="标定" :span="2">
                    {{ m.table.calibration.files }} 个正常数据文件，{{ m.table.calibration.method }}
                  </el-descriptions-item>
                  <el-descriptions-item label="来源" :span="2">
                    {{ m.table.is_default ? '随代码提供的默认表（2026-11 正常数据）' : m.table.source }}
                  </el-descriptions-item>
                </el-descriptions>
                <el-alert v-if="m.table.model.type === 'surrogate'" class="note" type="info" :closable="false" show-icon
                          title="数据代理模型由正常数据拟合，用于在 AMESim 模型接入前跑通流程。它只学到了健康数据的规律，能发现偏离，但不能模拟没见过的部件故障。" />
              </template>
              <el-empty v-else description="还没有基准表" :image-size="70" />

              <div v-if="job.state === 'running' && job.model_id === m.id" class="job">
                <div class="muted">正在建立：{{ job.stage }} {{ job.total ? `${job.done}/${job.total}` : '' }}</div>
                <el-progress :percentage="jobPercent" :stroke-width="10" />
              </div>
              <div v-else-if="job.state === 'done' && job.model_id === m.id && job.result" class="muted small job">
                上次重建：{{ job.result.created }}，{{ job.operator }} 用 {{ job.source }}（{{ job.result.files }} 个文件）
              </div>
              <el-alert v-else-if="job.state === 'failed' && job.model_id === m.id" class="note" type="error"
                        :closable="false" :title="`上次建立失败：${job.error}`" />
            </div>

            <div v-if="m.table" class="section">
              <div class="section-head"><span>标定结果（模型 vs 正常数据）</span></div>
              <div class="muted small">
                固有偏差：正常时该测点比模型预期高/低多少（随工况变化，此处为平均值），诊断时先扣除；
                离散 σ：扣除后的波动，决定阈值。σ 越小，模型能发现的偏离越小。
              </div>
              <el-table :data="m.table.calibration.columns" size="small" border max-height="320">
                <el-table-column prop="column" label="测点" min-width="120" />
                <el-table-column prop="output" label="模型输出" min-width="100" />
                <el-table-column label="固有偏差" width="90" align="right">
                  <template slot-scope="{ row }">{{ val(row.bias, row, true) }}</template>
                </el-table-column>
                <el-table-column label="离散σ" width="80" align="right">
                  <template slot-scope="{ row }">{{ val(row.std, row) }}</template>
                </el-table-column>
                <el-table-column label="预警 / 异常" width="140" align="right">
                  <template slot-scope="{ row }">±{{ val(row.warn, row) }} / ±{{ val(row.alarm, row) }}</template>
                </el-table-column>
              </el-table>
            </div>
          </el-col>

          <el-col :span="10">
            <div class="section">
              <div class="section-head"><span>工况试算</span></div>
              <el-form v-if="m.table && conditions[m.id]" size="small" label-width="80px" @submit.native.prevent>
                <el-form-item v-for="i in m.table.inputs" :key="i.name" :label="i.name">
                  <el-input-number v-model="conditions[m.id][i.name]" :step="stepOf(i)" :precision="precisionOf(i)" controls-position="right" />
                  <span class="unit">{{ i.unit }}</span>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="runPredict(m)">计算预期值</el-button>
                </el-form-item>
              </el-form>
              <template v-if="predictions[m.id]">
                <el-alert v-if="predictions[m.id].outside.length" type="warning" :closable="false"
                          :title="`超出基准表范围：${predictions[m.id].outside.join('、')}`" />
                <el-table :data="predictions[m.id].expected" size="small" border>
                  <el-table-column prop="name" label="模型输出" />
                  <el-table-column label="预期值" align="right">
                    <template slot-scope="{ row }">{{ fmt(row.value, row.unit) }}</template>
                  </el-table-column>
                </el-table>
              </template>
              <div :ref="`curve-${m.id}`" class="curve" />
            </div>

            <div v-if="m.media && m.media.video" class="section">
              <div class="section-head"><span>仿真动画</span></div>
              <video class="video" controls preload="metadata" :src="publicPath + m.media.video">您的浏览器不支持视频播放。</video>
              <div class="muted small">{{ m.media.caption }}</div>
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>

    <el-dialog :title="`重建基准表：${build.model ? build.model.name : ''}`" :visible.sync="build.visible" width="560px">
      <el-form v-if="build.model" label-width="110px" size="small">
        <el-form-item label="模型引擎">
          <el-radio-group v-model="build.engine">
            <el-radio v-for="e in build.model.engines" :key="e.type" :label="e.type" :disabled="!e.ready">{{ e.label }}</el-radio>
          </el-radio-group>
          <div v-for="e in notReady" :key="e.type" class="muted small">{{ e.label }}：{{ e.note }}</div>
        </el-form-item>
        <el-form-item label="正常数据目录">
          <el-autocomplete v-model="build.path" :fetch-suggestions="suggestDirs" placeholder="设备正常时采集的数据目录" style="width: 100%" />
          <div class="muted small">用于{{ build.engine === 'surrogate' ? '拟合代理模型并' : '' }}标定；填写完整路径，会自动登记为数据目录，子目录会一起读取</div>
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
import { addDataDir, getDataDirs } from '@/api/files'
import {
  MODE_LABELS, buildModelTable, getSimulationStatus, predictModel, resetModelTable, saveDiagnosisProfile
} from '@/api/simulation'
import { errorMessage } from '@/utils/request'

// 工况试算的初始值（没有的输入取网格中点）
const DEFAULT_CONDITION = { 电传转速: 2000, 进口压力: 0.15, 油温: 36, 质量流量: 290, 燃油密度: 782, 汇流温度: 36, 流量: 370 }

export default {
  name: 'Simulation',
  data() {
    return {
      loading: true,
      models: [],
      job: { state: 'idle' },
      profile: {},
      profileDirty: false,
      activeId: '',
      conditions: {},
      predictions: {},
      build: { visible: false, model: null, engine: '', path: '' },
      publicPath: process.env.BASE_URL,
      MODE_LABELS
    }
  },
  computed: {
    running() {
      return this.job.state === 'running'
    },
    jobPercent() {
      return this.job.total ? Math.round((this.job.done / this.job.total) * 100) : 0
    },
    notReady() {
      return this.build.model ? this.build.model.engines.filter(e => !e.ready) : []
    }
  },
  watch: {
    activeId(id) {
      const m = this.models.find(x => x.id === id)
      if (m && m.table && !this.predictions[id]) this.runPredict(m)
      this.$nextTick(this.resize)
    }
  },
  created() {
    this.charts = {}
    this.load()
  },
  beforeDestroy() {
    clearTimeout(this.timer)
    window.removeEventListener('resize', this.resize)
    Object.values(this.charts).forEach(c => c.dispose())
  },
  methods: {
    val(v, row, signed = false) {
      const sign = signed && v > 0 ? '+' : ''
      if (row.mode === 'absolute') return `${sign}${v.toFixed(2)} ${row.unit}`
      return `${sign}${(v * 100).toFixed(2)}%`
    },
    fmt(v, unit) {
      return `${unit === 'MPa' ? v.toFixed(3) : v.toFixed(1)} ${unit}`
    },
    stepOf(i) {
      return i.unit === 'MPa' ? 0.01 : i.unit === 'rpm' ? 100 : i.unit === '℃' ? 1 : 10
    },
    precisionOf(i) {
      return i.unit === 'MPa' ? 3 : 0
    },
    applyStatus(st, keepProfile = false) {
      this.models = st.models
      this.job = st.job || { state: 'idle' }
      if (!keepProfile || !this.profileDirty) {
        const p = {}
        for (const m of st.models) p[m.id] = { mode: 'decisive', sigma_warn: 3, sigma_alarm: 5, ...m.setting }
        this.profile = p
        this.profileDirty = false
      }
      for (const m of st.models) {
        if (!m.table || this.conditions[m.id]) continue
        const c = {}
        for (const i of m.table.inputs) {
          c[i.name] = i.name in DEFAULT_CONDITION ? DEFAULT_CONDITION[i.name] : i.grid[Math.floor(i.grid.length / 2)]
        }
        this.$set(this.conditions, m.id, c)
      }
      if (!this.activeId && st.models.length) this.activeId = st.models[0].id
    },
    async load() {
      const wasRunning = this.running
      try {
        this.applyStatus(await getSimulationStatus(), true)
        if (wasRunning && this.job.state === 'done' && this.job.result) {
          const r = this.job.result
          this.$message.success(`${this.job.model_name}基准表已更新：${r.model}，${r.files} 个正常数据文件，${r.created}`)
          this.$delete(this.predictions, this.job.model_id)
          const m = this.models.find(x => x.id === this.job.model_id)
          if (m && m.id === this.activeId) this.runPredict(m)
        } else if (wasRunning && this.job.state === 'failed') {
          this.$message.error(`建立基准表失败：${this.job.error}`)
        }
      } finally {
        this.loading = false
      }
      if (this.running) this.timer = setTimeout(this.load, 1000)
    },
    async saveProfile() {
      try {
        const st = await saveDiagnosisProfile(this.profile)
        this.applyStatus(st)
        this.$message.success('诊断方案已保存，之后的诊断（含后台自动诊断）按此方案进行')
      } catch (e) {
        this.$message.error(errorMessage(e))
      }
    },
    openBuild(m) {
      this.build = { visible: true, model: m, engine: (m.table && m.table.model.type) || m.engine, path: '' }
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
        // 填写的目录先登记为数据目录（已登记的直接通过），与“自动诊断”页一致
        const { path } = await addDataDir(this.build.path.trim(), true)
        this.job = await buildModelTable(this.build.model.id, path, this.build.engine)
        this.build.visible = false
        this.$message.info(`已开始建立“${this.build.model.name}”的基准表`)
        this.timer = setTimeout(this.load, 800)
      } catch (e) {
        this.$message.error(errorMessage(e))
      }
    },
    async reset(m) {
      try {
        await this.$confirm(`删除“${m.name}”重建的基准表，恢复使用随代码提供的默认表？`, '恢复默认', { type: 'warning' })
      } catch (e) {
        return
      }
      this.applyStatus(await resetModelTable(m.id), true)
      this.$delete(this.predictions, m.id)
      this.runPredict(this.models.find(x => x.id === m.id))
    },
    async runPredict(m) {
      if (!m || !m.table) return
      try {
        this.$set(this.predictions, m.id, await predictModel(m.id, this.conditions[m.id]))
        await this.drawCurve(m)
      } catch (e) {
        this.$message.error(errorMessage(e))
      }
    },
    /** 第一个输出随第一个输入变化的模型曲线（其余输入取当前值） */
    async drawCurve(m) {
      const x = m.table.inputs[0]
      const out = m.table.outputs[0]
      const lo = Math.min(...x.grid)
      const hi = Math.max(...x.grid)
      const xs = Array.from({ length: 11 }, (_, k) => lo + ((hi - lo) * k) / 10)
      const results = await Promise.all(xs.map(v => predictModel(m.id, { ...this.conditions[m.id], [x.name]: v })))
      const curve = xs.map((v, k) => [v, (results[k].expected.find(e => e.name === out.name) || {}).value])
        .filter(p => p[1] !== undefined)
      await this.$nextTick()
      const el = this.$refs[`curve-${m.id}`]
      const dom = Array.isArray(el) ? el[0] : el
      if (!dom) return
      if (!this.charts[m.id]) {
        this.charts[m.id] = echarts.init(dom)
        window.addEventListener('resize', this.resize)
      }
      const now = this.predictions[m.id].expected.find(e => e.name === out.name)
      this.charts[m.id].setOption({
        title: { text: `${out.name}随${x.name}的模型曲线`, left: 0, textStyle: { fontSize: 13, fontWeight: 'normal' } },
        grid: { left: 50, right: 20, top: 36, bottom: 36 },
        tooltip: {
          trigger: 'axis',
          formatter: p => `${x.name} ${p[0].value[0].toFixed(1)} ${x.unit}<br/>${out.name} ${p[0].value[1].toFixed(1)} ${out.unit}`
        },
        xAxis: { type: 'value', name: x.unit, min: lo, max: hi, splitLine: { show: false } },
        yAxis: { type: 'value', name: out.unit, scale: true, splitLine: { lineStyle: { color: '#f0f0f0' } } },
        series: [{
          type: 'line',
          data: curve,
          showSymbol: false,
          lineStyle: { color: '#9ca3af', width: 2 },
          markPoint: now ? {
            symbol: 'circle',
            symbolSize: 9,
            itemStyle: { color: '#2563eb' },
            label: { show: true, position: 'top', formatter: `${now.value.toFixed(1)} ${out.unit}`, color: '#2563eb' },
            data: [{ coord: [this.conditions[m.id][x.name], now.value] }]
          } : undefined
        }]
      }, true)
    },
    resize() {
      Object.values(this.charts).forEach(c => c.resize())
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
  line-height: 1.7;
}
.box-card {
  margin-bottom: 16px;
}
.card-head,
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section {
  margin-bottom: 18px;
}
.section-head {
  font-weight: 500;
  margin-bottom: 8px;
}
.grid-item {
  display: block;
  line-height: 1.8;
}
.note,
.job {
  margin-top: 10px;
}
.muted {
  color: #909399;
}
.small {
  font-size: 12px;
  line-height: 1.7;
}
.small-inline {
  font-size: 12px;
  margin-left: 8px;
}
.warn {
  color: #e6a23c;
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
