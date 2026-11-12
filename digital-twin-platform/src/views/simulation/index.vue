<template>
  <div class="sim-page">
    <header class="sim-head">
      <h2>仿真模型</h2>
      <div class="head-actions">
        <el-button size="small" type="primary" icon="el-icon-plus" @click="openEditor(null)">新建模型</el-button>
      </div>
    </header>

    <div v-loading="loading" class="sim-body">
      <!-- 模型列表 -->
      <nav class="rail" aria-label="仿真模型列表">
        <button v-for="m in models" :key="m.id" type="button" :class="['rail-item', statusOf(m).tone, { active: m.id === selectedId }]"
                @click="select(m)">
          <span class="rail-name">{{ m.name }}</span>
          <span class="rail-method">{{ methodText(m) }}</span>
          <span class="rail-meta">
            <i class="dot" />{{ statusOf(m).text }}
            <template v-if="accuracyOf(m)"><span class="sep" />换油温误差 {{ accuracyOf(m) }}</template>
          </span>
          <span v-if="job.state === 'running' && job.model_id === m.id" class="rail-progress"><span :style="{ width: jobPercent + '%' }" /></span>
        </button>
        <div v-if="!loading && !models.length" class="rail-empty">
          还没有仿真模型。
          <el-button type="text" @click="openEditor(null)">新建一个</el-button>
        </div>
        <div v-if="profileDirty" class="profile-bar">
          <span>诊断方案有未保存的修改</span>
          <el-button size="mini" type="primary" @click="saveProfile">保存方案</el-button>
        </div>
      </nav>

      <!-- 模型详情 -->
      <section v-if="current" class="sheet">
        <div class="sheet-head">
          <div class="title-block">
            <h3>{{ current.name }}</h3>
            <p class="desc">{{ current.description }}</p>
            <div class="badges">
              <span class="badge">{{ methodText(current) }}</span>
              <span :class="['badge', current.source]">{{ SOURCE_LABELS[current.source] }}</span>
              <span class="badge mono">{{ current.id }}</span>
            </div>
          </div>
          <div class="sheet-actions">
            <el-button size="small" icon="el-icon-edit" @click="openEditor(current)">编辑</el-button>
            <el-button size="small" type="primary" icon="el-icon-cpu" :disabled="running" @click="openBuild(current)">
              {{ current.table ? '重建模型' : '建立模型' }}
            </el-button>
            <el-dropdown trigger="click" @command="onMore">
              <el-button size="small" icon="el-icon-more" aria-label="更多操作" />
              <el-dropdown-menu slot="dropdown">
                <el-dropdown-item command="reset" :disabled="!current.table || current.table.is_default || running">恢复默认结果</el-dropdown-item>
                <el-dropdown-item command="restore" :disabled="current.source !== 'override'">恢复内置配置</el-dropdown-item>
                <el-dropdown-item command="delete" divided class="danger-item">删除模型</el-dropdown-item>
              </el-dropdown-menu>
            </el-dropdown>
          </div>
        </div>

        <dl class="facts">
          <div class="fact">
            <dt>诊断中</dt>
            <dd>
              <el-select v-model="profile[current.id].mode" size="mini" class="mode-select" @change="profileDirty = true">
                <el-option v-for="(label, value) in MODE_LABELS" :key="value" :label="label" :value="value" />
              </el-select>
            </dd>
          </div>
          <div class="fact">
            <dt>
              预警 / 异常倍数
              <el-tooltip content="阈值 = max(下限, 倍数 × 标定离散 σ)，倍数越大越不容易报" placement="top"><i class="el-icon-question" /></el-tooltip>
            </dt>
            <dd class="sigma">
              <el-input-number v-model="profile[current.id].sigma_warn" size="mini" :min="1" :max="20" :step="0.5" controls-position="right"
                               @change="profileDirty = true" />
              <span>/</span>
              <el-input-number v-model="profile[current.id].sigma_alarm" size="mini" :min="1" :max="20" :step="0.5" controls-position="right"
                               @change="profileDirty = true" />
              <span class="unit">σ</span>
            </dd>
          </div>
        </dl>

        <div v-if="job.state === 'running' && job.model_id === current.id" class="job">
          <span>正在建立：{{ job.stage }} {{ job.total ? `${job.done}/${job.total}` : '' }}</span>
          <el-progress :percentage="jobPercent" :stroke-width="6" :show-text="false" />
        </div>
        <el-alert v-else-if="job.state === 'failed' && job.model_id === current.id" class="job" type="error" :closable="false"
                  :title="`上次建立失败：${job.error}`" />
        <el-alert v-if="current.table && current.table.stale" class="job" type="warning" :closable="false" show-icon
                  title="模型配置已修改，原结果已作废，重建前该模型不参与诊断" />

        <el-tabs v-model="tab" class="sheet-tabs">
          <!-- 拟合精度 -->
          <el-tab-pane v-if="current.table && current.table.kind === 'formula'" label="精度" name="formulas">
            <div v-if="excludedFiles.length" class="excluded-line">
              已排除 {{ excludedFiles.length }} 个文件：
              <el-tag v-for="f in excludedFiles" :key="f" size="mini" closable class="excluded" @close="includeFile(f)">{{ f }}</el-tag>
            </div>
            <div class="spec-table" role="table">
              <div class="spec-row spec-header" role="row">
                <span role="columnheader">输出</span>
                <span role="columnheader">建模方式</span>
                <span role="columnheader" class="num">
                  换油温误差
                  <el-tooltip content="留一温度组交叉验证：用其余油温段的数据建模，预测这一段；阈值按它定" placement="top"><i class="el-icon-question" /></el-tooltip>
                </span>
                <span role="columnheader" class="num">用平均值的误差</span>
                <span role="columnheader" />
              </div>
              <template v-for="o in current.config.outputs">
                <div :key="o.name" :class="['spec-row', { open: openOutputs[o.name] }]" role="row">
                  <span class="spec-out">
                    <b>{{ o.name }}</b>
                    <small>{{ [o.system, o.unit].filter(Boolean).join('，') }}</small>
                  </span>
                  <template v-if="formulaOf(o.name)">
                    <span><span :class="['method-tag', formulaOf(o.name).method]">{{ METHOD_LABELS[formulaOf(o.name).method] || formulaOf(o.name).method }}</span></span>
                    <span :class="['num', 'metric-value', cvTone(formulaOf(o.name).assessment)]">{{ cvText(formulaOf(o.name).assessment) }}</span>
                    <span class="num muted">{{ constText(formulaOf(o.name).assessment) }}</span>
                    <span class="spec-tools">
                      <span v-if="!formulaOf(o.name).assessment.constant && (formulaOf(o.name).assessment.suggestions || []).length" class="flag"
                            title="有改进建议，见详情">
                        <i class="el-icon-warning-outline" />{{ formulaOf(o.name).assessment.suggestions.length }}
                      </span>
                      <el-button type="text" size="mini" :icon="openOutputs[o.name] ? 'el-icon-arrow-up' : 'el-icon-arrow-down'"
                                 @click="toggleOutput(o.name)">{{ openOutputs[o.name] ? '收起' : '详情' }}</el-button>
                    </span>
                  </template>
                  <span v-else class="spec-missing">
                    {{ current.table.calibration.failed_outputs[o.name] ? `未建立：${current.table.calibration.failed_outputs[o.name]}` : '没有结果，重建模型后显示' }}
                  </span>
                </div>
                <div v-if="openOutputs[o.name] && formulaOf(o.name)" :key="`${o.name}-detail`" class="spec-detail">
                  <fit-result :result="formulaOf(o.name)" selectable @pick="onPick(o.name, $event)" />
                </div>
              </template>
            </div>
            <div v-if="pickedCount" class="exclude-bar">
              已选 {{ pickedCount }} 个可疑样本
              <el-button size="mini" type="warning" @click="excludePicked">排除这些样本并重建</el-button>
            </div>
          </el-tab-pane>

          <!-- 变量与输出 -->
          <el-tab-pane label="变量与输出" name="io">
            <h4 class="block-title">变量</h4>
            <el-table :data="current.config.inputs" size="small" class="plain-table">
              <el-table-column prop="name" label="名称" width="110" />
              <el-table-column label="来源" min-width="200">
                <template slot-scope="{ row }">{{ inputSource(row) }}</template>
              </el-table-column>
              <el-table-column label="单位换算" width="130">
                <template slot-scope="{ row }">{{ convText(row) }}</template>
              </el-table-column>
              <el-table-column prop="unit" label="单位" width="70" />
              <el-table-column v-if="current.engine === 'surrogate'" label="角色" width="130">
                <template slot-scope="{ row }">
                  {{ ROLE_LABELS[row.role || 'auto'] }}
                  <span v-if="(row.role || 'auto') === 'auto' && current.table && current.table.roles && current.table.roles[row.name]" class="muted">
                    （{{ ROLE_LABELS[current.table.roles[row.name]] }}）
                  </span>
                </template>
              </el-table-column>
              <el-table-column v-else label="网格" min-width="150">
                <template slot-scope="{ row }">{{ (row.grid || []).join(' / ') }}</template>
              </el-table-column>
              <el-table-column label="备用测点" width="120">
                <template slot-scope="{ row }">{{ (row.fallback_columns || []).join('、') || '—' }}</template>
              </el-table-column>
            </el-table>

            <h4 class="block-title">输出</h4>
            <el-table :data="current.config.outputs" size="small" class="plain-table">
              <el-table-column label="所属系统" width="160">
                <template slot-scope="{ row }">{{ row.system || '—' }}</template>
              </el-table-column>
              <el-table-column prop="name" label="名称" min-width="130" />
              <el-table-column v-if="current.engine === 'surrogate'" label="建模方式" width="96">
                <template slot-scope="{ row }">{{ METHOD_LABELS[row.method || 'autofit'] || row.method }}</template>
              </el-table-column>
              <el-table-column label="对应测点" min-width="180">
                <template slot-scope="{ row }">{{ (row.columns || []).join('、') }}</template>
              </el-table-column>
              <el-table-column label="比较" width="70">
                <template slot-scope="{ row }">{{ row.residual === 'absolute' ? '绝对' : '相对' }}</template>
              </el-table-column>
              <el-table-column label="单测点偏离" width="96">
                <template slot-scope="{ row }">{{ row.single === 'notice' ? '补充依据' : '参与结论' }}</template>
              </el-table-column>
              <el-table-column label="三维部件" width="150">
                <template slot-scope="{ row }">{{ componentNames([row.component]).join('') || '—' }}</template>
              </el-table-column>
            </el-table>

            <h4 class="block-title">适用与判定</h4>
            <dl class="rules">
              <dt>适用条件</dt>
              <dd>
                <template v-if="(current.config.active_if || []).length">
                  <div v-for="(c, k) in current.config.active_if" :key="k">{{ conditionText(c) }}</div>
                </template>
                <span v-else>始终适用</span>
              </dd>
              <dt>单测点偏离</dt>
              <dd>扣除标定的固有偏差后，偏离超过阈值判预警 / 异常</dd>
              <template v-if="groupRule(current.config)">
                <dt>整体偏移</dt>
                <dd>
                  {{ groupOutputs(current.config).join('、') }} 中至少 {{ groupRule(current.config).min_columns || 3 }} 个测点彼此一致、整体偏离时，
                  判为“{{ MEANING_LABELS[groupRule(current.config).meaning] }}”<template v-if="groupRule(current.config).driver">，沿 {{ groupRule(current.config).driver }} 判断</template>
                </dd>
              </template>
              <dt>三维部件</dt>
              <dd>{{ componentNames(current.config.components).join('、') || '—' }}</dd>
            </dl>

            <template v-if="current.engine === 'amesim'">
              <h4 class="block-title">AMESim</h4>
              <dl class="rules">
                <dt>模型文件</dt>
                <dd>{{ current.config.amesim.model_file }}（{{ current.config.amesim.url || '—' }}）</dd>
                <dt>参数映射</dt>
                <dd>
                  <div v-for="(p, k) in current.config.amesim.parameters" :key="k">
                    {{ p.input }}{{ p.derive ? `（${DERIVE_LABELS[p.derive]}）` : '' }} → {{ Array.isArray(p.params) ? p.params.join('、') : (p.params || 'input.data') }}
                  </div>
                </dd>
                <dt>输出变量</dt>
                <dd><div v-for="(v, k) in current.config.amesim.variables" :key="k">{{ k }} ← {{ v }}</div></dd>
              </dl>
            </template>
          </el-tab-pane>

          <!-- 标定 -->
          <el-tab-pane label="标定" name="calib">
            <template v-if="current.table">
              <el-table :data="current.table.calibration.columns" size="small" class="plain-table">
                <el-table-column prop="column" label="测点" min-width="140" />
                <el-table-column prop="output" label="模型输出" min-width="130" />
                <el-table-column width="110" align="right">
                  <template slot="header">
                    固有偏差
                    <el-tooltip content="正常时该测点比模型预期高/低多少（随工况变化，此处为平均值），诊断时先扣除" placement="top"><i class="el-icon-question" /></el-tooltip>
                  </template>
                  <template slot-scope="{ row }"><span :class="{ warn: row.warning }">{{ val(row.bias, row, true) }}</span></template>
                </el-table-column>
                <el-table-column width="100" align="right">
                  <template slot="header">
                    离散 σ
                    <el-tooltip content="扣除固有偏差后的波动；σ 越小，能发现的偏离越小" placement="top"><i class="el-icon-question" /></el-tooltip>
                  </template>
                  <template slot-scope="{ row }">{{ val(row.std, row) }}</template>
                </el-table-column>
                <el-table-column label="预警 / 异常" width="170" align="right">
                  <template slot-scope="{ row }">±{{ val(row.warn, row) }} / ±{{ val(row.alarm, row) }}</template>
                </el-table-column>
                <el-table-column label="提示" min-width="200">
                  <template slot-scope="{ row }"><span v-if="row.warning" class="warn small">{{ row.warning }}</span></template>
                </el-table-column>
              </el-table>
            </template>
            <el-empty v-else description="还没有模型结果，点右上角“建立模型”" :image-size="64" />
          </el-tab-pane>

          <!-- 工况试算 -->
          <el-tab-pane label="工况试算" name="predict" :disabled="!current.table">
            <div v-if="current.table && conditions[current.id]" class="predict">
              <el-form size="small" label-position="top" class="predict-form" @submit.native.prevent>
                <el-form-item v-for="i in current.table.inputs" :key="i.name" :label="`${i.name}${i.unit ? '（' + i.unit + '）' : ''}`">
                  <el-input-number v-model="conditions[current.id][i.name]" :step="stepOf(i)" :precision="precisionOf(i)" controls-position="right" />
                </el-form-item>
                <el-button type="primary" size="small" @click="runPredict(current)">计算预期值</el-button>
              </el-form>
              <div class="predict-out">
                <template v-if="predictions[current.id]">
                  <el-alert v-if="predictions[current.id].outside.length" type="warning" :closable="false"
                            :title="`超出建模数据范围（外推）：${predictions[current.id].outside.join('、')}`" />
                  <table class="expect">
                    <tr v-for="row in predictions[current.id].expected" :key="row.name">
                      <th>{{ row.name }}</th>
                      <td>{{ fmt(row.value, row.unit) }}</td>
                    </tr>
                  </table>
                </template>
                <div v-if="current.table.inputs.length > 1" class="curve-head">
                  曲线横轴
                  <el-select v-model="curveVar" size="mini" style="width: 130px" @change="drawCurve(current)">
                    <el-option v-for="i in current.table.inputs" :key="i.name" :label="i.name" :value="i.name" />
                  </el-select>
                </div>
                <div ref="curve" class="curve" />
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane v-if="current.media && current.media.video" label="仿真动画" name="media">
            <video class="video" controls preload="metadata" :src="publicPath + current.media.video">您的浏览器不支持视频播放。</video>
            <p class="source-line">{{ current.media.caption }}</p>
          </el-tab-pane>
        </el-tabs>
      </section>
      <section v-else-if="!loading" class="sheet sheet-empty">
        <el-empty description="选择左侧的模型，或新建一个" :image-size="80" />
      </section>
    </div>

    <el-dialog :title="`${build.model && build.model.table ? '重建' : '建立'}模型：${build.model ? build.model.name : ''}`" :visible.sync="build.visible"
               width="560px" append-to-body>
      <el-form v-if="build.model" label-width="110px" size="small">
        <el-form-item label="模型方式">
          <el-radio-group v-model="build.engine">
            <el-radio v-for="e in build.model.engines" :key="e.type" :label="e.type" :disabled="!e.ready">{{ e.label }}</el-radio>
          </el-radio-group>
          <div v-for="e in notReady" :key="e.type" class="warn small">{{ e.note }}</div>
        </el-form-item>
        <el-form-item label="正常数据目录">
          <el-autocomplete v-model="build.path" :fetch-suggestions="suggestDirs" placeholder="设备正常时采集的数据目录（完整路径，含子目录）" style="width: 100%" />
        </el-form-item>
      </el-form>
      <span slot="footer">
        <el-button @click="build.visible = false">取消</el-button>
        <el-button type="primary" :disabled="!build.path" @click="startBuild">开始建立</el-button>
      </span>
    </el-dialog>

    <model-editor :visible="editor.visible" :model="editor.model" :builders="builders" @close="editor.visible = false" @saved="onSaved" />

  </div>
</template>

<script>
import * as echarts from 'echarts'
import { addDataDir, getDataDirs } from '@/api/files'
import {
  ENGINE_LABELS, KIND_LABELS, MEANING_LABELS, METHOD_LABELS, MODE_LABELS, ROLE_LABELS, buildModelTable, deleteModel,
  getSimulationStatus, predictModel, resetModelTable, saveDiagnosisProfile,
  updateModel
} from '@/api/simulation'
import { errorMessage } from '@/utils/request'
import { COMPONENTS } from '@/views/dashboard/scene/components'
import FitResult from './FitResult'
import ModelEditor from './ModelEditor'

const SOURCE_LABELS = { builtin: '内置', custom: '自定义', override: '内置·已修改' }
const DERIVE_LABELS = { temperature: '油温', density: '由油温算密度', viscosity: '由油温算黏度' }


export default {
  name: 'Simulation',
  components: { FitResult, ModelEditor },
  data() {
    return {
      loading: true,
      models: [],
      builders: [],
      curveVar: '',
      picks: {},
      job: { state: 'idle' },
      profile: {},
      profileDirty: false,
      selectedId: '',
      tab: 'formulas',
      openOutputs: {},
      conditions: {},
      predictions: {},
      build: { visible: false, model: null, engine: '', path: '' },
      publicPath: process.env.BASE_URL,
      editor: { visible: false, model: null },
      MODE_LABELS,
      SOURCE_LABELS,
      ENGINE_LABELS,
      METHOD_LABELS,
      ROLE_LABELS,
      KIND_LABELS,
      MEANING_LABELS,
      DERIVE_LABELS
    }
  },
  computed: {
    running() {
      return this.job.state === 'running'
    },
    jobPercent() {
      return this.job.total ? Math.round((this.job.done / this.job.total) * 100) : 0
    },
    current() {
      return this.models.find(m => m.id === this.selectedId) || null
    },
    excludedFiles() {
      return (this.current && this.current.config.exclude_files) || []
    },
    pickedCount() {
      return new Set(Object.values(this.picks).flat()).size
    },
    notReady() {
      return this.build.model ? this.build.model.engines.filter(e => !e.ready) : []
    }
  },
  watch: {
    tab(tab) {
      if (tab === 'predict' && this.current) this.runPredict(this.current)
    }
  },
  created() {
    this.chart = null
    window.addEventListener('resize', this.resize)
    this.load()
  },
  beforeDestroy() {
    clearTimeout(this.timer)
    window.removeEventListener('resize', this.resize)
    if (this.chart) this.chart.dispose()
  },
  methods: {
    outputColumns(cfg) {
      return [].concat(...(cfg.outputs || []).map(o => o.columns || []))
    },
    systemsOf(cfg) {
      return [...new Set((cfg.outputs || []).map(o => o.system).filter(Boolean))]
    },
    componentNames(keys) {
      return (keys || []).filter(Boolean).map(k => (COMPONENTS[k] ? COMPONENTS[k].label : k))
    },
    conditionText(c) {
      const parts = []
      if (c.min !== undefined && c.min !== null) parts.push(`≥ ${c.min}`)
      if (c.max !== undefined && c.max !== null) parts.push(`≤ ${c.max}`)
      return `${c.column} ${parts.join(' 且 ')}${c.note ? `（${c.note}）` : ''}`
    },
    thresholdText(cfg) {
      const th = cfg.thresholds || {}
      return `预警 ${th.sigma_warn || 3}σ / 异常 ${th.sigma_alarm || 5}σ（诊断方案可单独调整），并不低于各类型的阈值下限`
    },
    inputSource(i) {
      if (i.derived === 'density') return `由油温算燃油密度（${i.temperature_column}）`
      if (i.derived === 'viscosity') return `由油温算运动黏度（${i.temperature_column}）`
      if (i.constant !== undefined && i.constant !== null && !i.column && !(i.columns && i.columns.length)) return `常数 ${i.constant}`
      if (i.columns && i.columns.length) return `取中位数：${i.columns.join('、')}`
      return i.column || '—'
    },
    groupRule(cfg) {
      return (cfg.rules || {}).group_shift || null
    },
    groupOutputs(cfg) {
      const r = this.groupRule(cfg)
      return r ? (r.outputs || [r.output]) : []
    },
    select(row) {
      if (!row) return
      this.disposeChart()
      this.selectedId = row.id
      this.tab = row.table && row.table.kind === 'formula' ? 'formulas' : 'io'
      this.picks = {}
      this.openOutputs = {}
      this.curveVar = ''
    },
    disposeChart() {
      if (this.chart) {
        this.chart.dispose()
        this.chart = null
      }
    },
    /** 列表上的状态：颜色（ok / reference / off / pending）与一句话 */
    statusOf(m) {
      const mode = (this.profile[m.id] || {}).mode || 'decisive'
      if (!m.table) return { tone: 'pending', text: '还没有模型结果' }
      if (m.table.stale) return { tone: 'pending', text: '配置已修改，需要重建' }
      if (mode === 'off') return { tone: 'off', text: '诊断中关闭' }
      return { tone: mode === 'reference' ? 'reference' : 'ok', text: MODE_LABELS[mode] }
    },
    /** 模型的方式：内置模型（后端配置的计算） / 数据拟合 / 仿真 */
    methodText(m) {
      if (m.engine !== 'surrogate') return ENGINE_LABELS[m.engine] || m.engine
      const methods = m.methods || []
      if (methods.includes('formula')) return methods.length > 1 ? '内置模型 + 数据拟合' : '内置模型'
      return '数据拟合'
    },
    constText(a) {
      if (!a || a.const_error === null || a.const_error === undefined || a.constant) return '—'
      return a.mode === 'absolute' ? `${Number(a.const_error).toPrecision(2)} ${a.unit || ''}` : `${(a.const_error * 100).toFixed(1)}%`
    },
    /** 各输出换油温段误差（相对误差的输出）的范围 */
    accuracyOf(m) {
      const f = (m.table && m.table.formulas) || {}
      const errs = Object.values(f).map(x => x.assessment).filter(a => a && a.mode === 'relative' && a.cv_error !== null && !a.constant)
        .map(a => a.cv_error * 100)
      if (!errs.length) return ''
      const lo = Math.min(...errs)
      const hi = Math.max(...errs)
      return lo === hi || errs.length === 1 ? `${lo.toFixed(2)}%` : `${lo.toFixed(2)}–${hi.toFixed(2)}%`
    },
    warningsOf(m) {
      const f = (m.table && m.table.formulas) || {}
      return Object.values(f).reduce((n, x) => n + ((x.assessment && x.assessment.suggestions) || []).length, 0)
    },
    cvText(a) {
      if (!a || a.cv_error === null || a.cv_error === undefined) return '—'
      if (a.constant) return '恒定值'
      return a.mode === 'absolute' ? `${Number(a.cv_error).toPrecision(2)} ${a.unit || ''}` : `${(a.cv_error * 100).toFixed(2)}%`
    },
    cvTone(a) {
      if (!a || a.cv_error === null || a.constant || a.mode === 'absolute') return ''
      return a.cv_error < 0.01 ? 'good' : a.cv_error < 0.03 ? '' : 'poor'
    },
    toggleOutput(name) {
      this.$set(this.openOutputs, name, !this.openOutputs[name])
    },
    onMore(cmd) {
      const m = this.current
      if (cmd === 'reset') this.reset(m)
      else if (cmd === 'restore') this.restoreConfig(m)
      else if (cmd === 'delete') this.removeModel(m)
    },
    convText(i) {
      const parts = []
      if (i.scale !== undefined && i.scale !== 1) parts.push(`× ${Number(i.scale).toPrecision(6).replace(/\.?0+$/, '')}`)
      if (i.offset) parts.push(`${i.offset > 0 ? '+' : '−'} ${Math.abs(i.offset)}`)
      return parts.join(' ') || '—'
    },
    formulaOf(name) {
      const t = this.current && this.current.table
      return t && t.formulas ? t.formulas[name] : null
    },
    onPick(output, keys) {
      this.$set(this.picks, output, keys)
    },
    async saveConfig(m, cfg, message) {
      try {
        await updateModel(m.id, cfg)
        this.applyStatus(await getSimulationStatus(), true)
        this.$message.success(message)
        return true
      } catch (e) {
        this.$message.error(errorMessage(e))
        return false
      }
    },
    async excludePicked() {
      const m = this.current
      const keys = [...new Set(Object.values(this.picks).flat())]
      const cfg = JSON.parse(JSON.stringify(m.config))
      cfg.exclude_files = [...new Set([...(cfg.exclude_files || []), ...keys])]
      if (await this.saveConfig(m, cfg, `已排除 ${keys.length} 个文件，请重建模型`)) {
        this.picks = {}
        this.openBuild(this.current)
      }
    },
    async includeFile(file) {
      const m = this.current
      const cfg = JSON.parse(JSON.stringify(m.config))
      cfg.exclude_files = (cfg.exclude_files || []).filter(f => f !== file)
      await this.saveConfig(m, cfg, `已恢复 ${file}，请重建模型`)
    },
    async restoreConfig(m) {
      try {
        await this.$confirm(`放弃对“${m.name}”配置的修改，恢复内置配置？`, '恢复内置配置', { type: 'warning' })
      } catch (e) {
        return
      }
      try {
        this.applyStatus(await deleteModel(m.id, true), true)
        this.$delete(this.predictions, m.id)
        this.$delete(this.conditions, m.id)
        this.$message.success('已恢复内置配置')
      } catch (e) {
        this.$message.error(errorMessage(e))
      }
    },
    val(v, row, signed = false) {
      const sign = signed && v > 0 ? '+' : ''
      if (row.mode === 'absolute') return `${sign}${v.toFixed(2)} ${row.unit}`
      return `${sign}${(v * 100).toFixed(2)}%`
    },
    fmt(v, unit) {
      return `${unit === 'MPa' ? v.toFixed(3) : v.toFixed(1)} ${unit}`
    },
    /** 试算输入的步长与小数位按数据范围定（如 kg/s 的质量流量只有 0.03–0.12） */
    stepOf(i) {
      const span = i.grid.length ? Math.max(...i.grid) - Math.min(...i.grid) : 0
      const mag = Math.max(span, ...i.grid.map(Math.abs)) || 1
      return Number((10 ** Math.floor(Math.log10(mag / 20))).toPrecision(1))
    },
    precisionOf(i) {
      return Math.max(0, -Math.floor(Math.log10(this.stepOf(i))))
    },
    applyStatus(st, keepProfile = false) {
      this.models = st.models
      if (st.builders) this.builders = st.builders
      this.job = st.job || { state: 'idle' }
      const p = {}
      for (const m of st.models) {
        const saved = { mode: 'decisive', sigma_warn: 3, sigma_alarm: 5, ...m.setting }
        // 有未保存的修改时保留用户正在改的值，新出现的模型用保存的方案
        p[m.id] = keepProfile && this.profileDirty && this.profile[m.id] ? this.profile[m.id] : saved
      }
      this.profile = p
      if (!keepProfile) this.profileDirty = false
      for (const m of st.models) {
        if (!m.table || this.conditions[m.id]) continue
        const c = {}
        for (const i of m.table.inputs) {
          c[i.name] = i.grid.length ? +((Math.min(...i.grid) + Math.max(...i.grid)) / 2).toPrecision(4) : 0
        }
        this.$set(this.conditions, m.id, c)
      }
      if (!st.models.some(m => m.id === this.selectedId)) {
        this.selectedId = ''
        if (st.models.length) this.select(st.models[0])
      }
    },
    async load() {
      const wasRunning = this.running
      try {
        this.applyStatus(await getSimulationStatus(), true)
        if (wasRunning && this.job.state === 'done' && this.job.result) {
          const r = this.job.result
          this.$message.success(`已建立“${this.job.model_name}”：${r.model}，${r.files} 个正常数据文件`)
          this.$delete(this.predictions, this.job.model_id)
          const m = this.models.find(x => x.id === this.job.model_id)
          if (m && m.id === this.selectedId && this.tab === 'predict') this.runPredict(m)
        } else if (wasRunning && this.job.state === 'failed') {
          this.$message.error(`建立模型失败：${this.job.error}`)
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
    openEditor(m) {
      this.editor = { visible: true, model: m ? m.config : null }
    },
    async onSaved(model) {
      this.editor.visible = false
      this.$delete(this.predictions, model.id)
      this.$delete(this.conditions, model.id)
      this.applyStatus(await getSimulationStatus(), true)
      this.select(this.models.find(m => m.id === model.id))
    },
    async removeModel(m) {
      const builtin = m.source !== 'custom'
      try {
        await this.$confirm(builtin
          ? `删除模型“${m.name}”？删除后不再参与诊断。`
          : `删除模型“${m.name}”及其结果？删除后不能恢复。`, '删除模型', { type: 'warning', confirmButtonText: '删除' })
      } catch (e) {
        return
      }
      try {
        const st = await deleteModel(m.id)
        this.$delete(this.predictions, m.id)
        this.$delete(this.conditions, m.id)
        if (this.selectedId === m.id) this.selectedId = ''
        this.applyStatus(st, true)
        this.$message.success(`已删除“${m.name}”`)
      } catch (e) {
        this.$message.error(errorMessage(e))
      }
    },
    openBuild(m) {
      this.build = { visible: true, model: m, engine: m.engine, path: '' }
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
        this.$message.info(`正在建立“${this.build.model.name}”`)
        this.timer = setTimeout(this.load, 800)
      } catch (e) {
        this.$message.error(errorMessage(e))
      }
    },
    async reset(m) {
      try {
        await this.$confirm(`删除“${m.name}”重建的结果，恢复使用默认结果？`, '恢复默认结果', { type: 'warning' })
      } catch (e) {
        return
      }
      this.applyStatus(await resetModelTable(m.id), true)
      this.$delete(this.predictions, m.id)
      if (this.tab === 'predict') this.runPredict(this.models.find(x => x.id === m.id))
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
      const x = m.table.inputs.find(i => i.name === this.curveVar) ||
        m.table.inputs.find(i => i.role === 'main') || m.table.inputs[0]
      if (!this.curveVar) this.curveVar = x.name
      const out = m.table.outputs[0]
      const lo = Math.min(...x.grid)
      const hi = Math.max(...x.grid)
      const xs = Array.from({ length: 11 }, (_, k) => lo + ((hi - lo) * k) / 10)
      const results = await Promise.all(xs.map(v => predictModel(m.id, { ...this.conditions[m.id], [x.name]: v })))
      const curve = xs.map((v, k) => [v, (results[k].expected.find(e => e.name === out.name) || {}).value])
        .filter(p => p[1] !== undefined)
      await this.$nextTick()
      const dom = this.$refs.curve
      if (!dom || this.selectedId !== m.id) return
      if (this.chart && this.chart.getDom() !== dom) {
        this.chart.dispose()
        this.chart = null
      }
      if (!this.chart) this.chart = echarts.init(dom)
      const now = this.predictions[m.id].expected.find(e => e.name === out.name)
      this.chart.setOption({
        title: { text: `${out.name}随${x.name}变化`, left: 0, textStyle: { fontSize: 13, fontWeight: 500, color: '#1e2b3c' } },
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
          lineStyle: { color: '#0b1626', width: 1.6 },
          areaStyle: { color: 'rgba(11, 107, 203, 0.06)' },
          markPoint: now ? {
            symbol: 'circle',
            symbolSize: 9,
            itemStyle: { color: '#0b6bcb' },
            label: { show: true, position: 'top', formatter: `${now.value.toFixed(1)} ${out.unit}`, color: '#0b6bcb' },
            data: [{ coord: [this.conditions[m.id][x.name], now.value] }]
          } : undefined
        }]
      }, true)
      this.chart.resize()
    },
    resize() {
      if (this.chart) this.chart.resize()
    }
  }
}
</script>
<style lang="scss" scoped>
$ink: #0b1626;
$steel: #1e2b3c;
$mist: #6b7a90;
$paper: #f3f5f8;
$rule: #dfe5ec;
$accent: #0b6bcb;
$ok: #12805c;
$caution: #b26a00;
$off: #8a96a6;

.sim-page {
  padding: 20px 24px 28px;
  color: $steel;
  min-height: calc(100vh - 50px);
  background: $paper;
}

.sim-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  h2 {
    margin: 0;
    font-size: 22px;
    font-weight: 600;
    color: $ink;
    letter-spacing: 0.02em;
  }
}
.head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.sim-body {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  min-height: 420px;
}

/* ---------- 模型列表 ---------- */
.rail {
  position: sticky;
  top: 16px;
  display: flex;
  flex-direction: column;
  background: $ink;
  border-radius: 10px;
  padding: 8px;
  max-height: calc(100vh - 140px);
  overflow-y: auto;
}
.rail-item {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: #c7d2e0;
  padding: 12px 12px 12px 16px;
  border-radius: 6px;
  cursor: pointer;
  font: inherit;
  transition: background 0.15s;
  &::before {
    content: '';
    position: absolute;
    left: 4px;
    top: 12px;
    bottom: 12px;
    width: 3px;
    border-radius: 2px;
    background: var(--tone);
  }
  & + & {
    margin-top: 2px;
  }
  &:hover {
    background: rgba(255, 255, 255, 0.05);
  }
  &:focus-visible {
    outline: 2px solid #38bdf8;
    outline-offset: -2px;
  }
  &.active {
    background: #fff;
    color: $steel;
    .rail-name {
      color: $ink;
    }
    .rail-method,
    .rail-meta {
      color: $mist;
    }
  }
  &.ok { --tone: #{$ok}; }
  &.reference { --tone: #{$caution}; }
  &.off { --tone: #{$off}; }
  &.pending { --tone: repeating-linear-gradient(180deg, #{$caution} 0 4px, transparent 4px 7px); }
}
.rail-name {
  font-size: 14px;
  font-weight: 600;
  color: #eef3fa;
  line-height: 1.4;
}
.rail-method {
  font-size: 12px;
  color: #8ea2bb;
}
.rail-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px 6px;
  font-size: 12px;
  color: #8ea2bb;
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--tone);
  }
  .sep {
    width: 1px;
    height: 10px;
    background: currentColor;
    opacity: 0.4;
  }
}
.rail-progress {
  height: 2px;
  background: rgba(255, 255, 255, 0.12);
  margin-top: 6px;
  span {
    display: block;
    height: 100%;
    background: #38bdf8;
    transition: width 0.3s;
  }
}
.rail-empty {
  color: #8ea2bb;
  padding: 16px;
  font-size: 13px;
}
.profile-bar {
  position: sticky;
  bottom: -8px;
  margin: 8px -8px -8px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: #fde68a;
  background: #13243b;
  border-top: 1px solid rgba(253, 230, 138, 0.25);
  border-radius: 0 0 10px 10px;
}

/* ---------- 详情 ---------- */
.sheet {
  background: #fff;
  border: 1px solid $rule;
  border-radius: 10px;
  padding: 22px 26px 26px;
  min-width: 0;
}
.sheet-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 420px;
}
.sheet-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  h3 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    color: $ink;
  }
}
.title-block {
  min-width: 0;
}
.desc {
  margin: 6px 0 10px;
  color: $mist;
  font-size: 13px;
  line-height: 1.6;
  max-width: 72ch;
}
.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.badge {
  font-size: 12px;
  line-height: 20px;
  padding: 0 8px;
  border-radius: 10px;
  background: #eef2f7;
  color: #3b4a5e;
  &.custom,
  &.override {
    background: #fff4e0;
    color: $caution;
  }
  &.mono {
    font-family: Menlo, Consolas, monospace;
    background: transparent;
    border: 1px solid $rule;
    color: $mist;
  }
}
.sheet-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.facts {
  display: grid;
  grid-template-columns: repeat(2, max-content);
  margin: 18px 0 4px;
  border-top: 1px solid $rule;
  border-bottom: 1px solid $rule;
  .fact {
    padding: 12px 16px;
    min-width: 0;
    & + .fact {
      border-left: 1px solid $rule;
    }
    &:first-child {
      padding-left: 0;
    }
  }
  dt {
    font-size: 12px;
    color: $mist;
    margin-bottom: 6px;
  }
  dd {
    margin: 0;
    font-size: 13px;
    color: $steel;
    small {
      display: block;
      color: $mist;
      font-size: 12px;
      margin-top: 2px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
  .mode-select {
    width: 120px;
  }
  .sigma {
    display: flex;
    align-items: center;
    gap: 4px;
    .el-input-number {
      width: 82px;
    }
    .unit {
      color: $mist;
    }
  }
}
.job {
  margin-top: 12px;
  font-size: 12px;
  color: $mist;
}

.sheet-tabs {
  margin-top: 10px;
  ::v-deep .el-tabs__item {
    font-size: 14px;
    height: 44px;
    line-height: 44px;
  }
  ::v-deep .el-tabs__active-bar {
    background: $ink;
  }
  ::v-deep .el-tabs__item.is-active {
    color: $ink;
    font-weight: 600;
  }
}

/* 精度 */
.spec-table {
  font-size: 13px;
}
.spec-row {
  display: grid;
  grid-template-columns: minmax(180px, 2fr) 110px 130px 130px minmax(110px, 1fr);
  align-items: center;
  gap: 12px;
  padding: 10px 4px;
  border-bottom: 1px solid $rule;
  &.open {
    border-bottom-color: transparent;
  }
  .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
}
.spec-header {
  padding-top: 4px;
  font-size: 12px;
  color: $mist;
}
.spec-out {
  display: flex;
  flex-direction: column;
  min-width: 0;
  b {
    color: $ink;
    font-weight: 600;
  }
  small {
    font-size: 12px;
    color: $mist;
  }
}
.spec-tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
.spec-missing {
  grid-column: 2 / -1;
  color: $mist;
  font-size: 12px;
}
.spec-detail {
  padding: 4px 4px 14px;
  border-bottom: 1px solid $rule;
  background: linear-gradient(#f7f9fb, #fff 40px);
}
.method-tag {
  display: inline-block;
  padding: 0 6px;
  line-height: 18px;
  font-size: 12px;
  border-radius: 3px;
  border: 1px solid $rule;
  color: $mist;
  &.formula {
    border-color: #c9dcf2;
    color: $accent;
  }
}
.metric-value {
  font-size: 15px;
  font-weight: 600;
  color: $steel;
  &.good {
    color: $ok;
  }
  &.poor {
    color: $caution;
  }
}
.flag {
  color: $caution;
  font-size: 12px;
  i {
    margin-right: 2px;
  }
}
.excluded-line {
  font-size: 12px;
  color: $mist;
  margin-bottom: 4px;
}
.excluded {
  margin: 0 4px 4px 0;
}
.exclude-bar {
  position: sticky;
  bottom: 0;
  margin-top: 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}

/* 变量与输出 */
.block-title {
  margin: 18px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: $ink;
  &:first-child {
    margin-top: 4px;
  }
}
.plain-table {
  ::v-deep th {
    background: #f7f9fb;
    color: $mist;
    font-weight: 500;
  }
}
.rules {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 8px 16px;
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  dt {
    color: $mist;
  }
  dd {
    margin: 0;
  }
}

/* 标定 / 试算 */
.source-line {
  font-size: 12px;
  color: $mist;
  margin: 10px 0 0;
}
.predict {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 24px;
}
.predict-form {
  ::v-deep .el-form-item {
    margin-bottom: 12px;
  }
  ::v-deep .el-form-item__label {
    padding-bottom: 2px;
    line-height: 1.6;
  }
  ::v-deep .el-input-number {
    width: 100%;
  }
}
.expect {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-top: 4px;
  th {
    text-align: left;
    font-weight: 400;
    color: $mist;
    padding: 6px 0;
    border-bottom: 1px solid $rule;
  }
  td {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    padding: 6px 0;
    border-bottom: 1px solid $rule;
  }
}
.curve-head {
  margin-top: 14px;
  font-size: 12px;
  color: $mist;
}
.curve {
  width: 100%;
  height: 260px;
  margin-top: 6px;
}
.video {
  width: 100%;
  max-width: 760px;
  border-radius: 6px;
  background: #000;
}

.muted {
  color: $mist;
}
.small {
  font-size: 12px;
}
.warn {
  color: $caution;
}
::v-deep .danger-item {
  color: #c0392b;
}

@media (max-width: 1100px) {
  .sim-body {
    grid-template-columns: 1fr;
  }
  .rail {
    position: static;
    max-height: none;
  }
  .predict {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 760px) {
  .spec-row {
    grid-template-columns: 1fr auto auto;
  }
  .spec-header,
  .spec-row > :nth-child(2),
  .spec-row > :nth-child(4) {
    display: none;
  }
}
@media (max-width: 640px) {
  .sheet-head {
    flex-direction: column;
  }
  .facts {
    grid-template-columns: 1fr;
    .fact + .fact {
      border-left: 0;
      padding-left: 0;
      border-top: 1px solid $rule;
    }
  }
}
@media (prefers-reduced-motion: reduce) {
  .rail-item,
  .rail-progress span {
    transition: none;
  }
}
</style>
