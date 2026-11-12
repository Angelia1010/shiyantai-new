<template>
  <div class="app-container simulation-page">
    <div class="page-header">
      <h2 class="page-title">仿真模型</h2>
      <div>
        <el-dropdown v-if="deletedBuiltins.length" trigger="click" @command="restoreBuiltin">
          <el-button size="small" icon="el-icon-refresh-left">恢复已删除的内置模型（{{ deletedBuiltins.length }}）</el-button>
          <el-dropdown-menu slot="dropdown">
            <el-dropdown-item v-for="d in deletedBuiltins" :key="d.id" :command="d">{{ d.name }}</el-dropdown-item>
          </el-dropdown-menu>
        </el-dropdown>
        <el-button size="small" icon="el-icon-setting" @click="openDerived">派生测点</el-button>
        <el-button size="small" type="primary" icon="el-icon-plus" @click="openEditor(null)">新建模型</el-button>
      </div>
    </div>

    <el-card shadow="never" class="box-card">
      <div slot="header" class="card-head">
        <span>
          模型与诊断方案
          <el-tooltip placement="right">
            <div slot="content">
              点击模型查看详细信息（输入、输出、规则、基准表与标定、工况试算）。<br>
              参与结论：偏离超过阈值时判预警/异常；仅作参考：只写进报告；关闭：不做该模型的对比。<br>
              阈值 = max(下限, 倍数 × 标定离散 σ)，倍数越大越不容易报。诊断方案自动诊断与手动诊断共用。
            </div>
            <i class="el-icon-question tip" />
          </el-tooltip>
        </span>
        <el-button size="mini" type="primary" :disabled="!profileDirty" @click="saveProfile">保存方案</el-button>
      </div>
      <el-table v-loading="loading" :data="models" size="small" border class="model-table" empty-text="还没有仿真模型，点击右上角“新建模型”"
                @row-click="openDetail">
        <el-table-column label="模型" min-width="220">
          <template slot-scope="{ row }">
            <span class="model-name">{{ row.name }}</span>
            <el-tag size="mini" :type="row.source === 'builtin' ? '' : 'info'" class="src-tag">{{ SOURCE_LABELS[row.source] }}</el-tag>
            <div class="muted small ellipsis">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="方式" width="110">
          <template slot-scope="{ row }">
            {{ ENGINE_LABELS[row.engine] || row.engine }}
            <div v-if="row.methods && row.methods.length" class="muted small">{{ row.methods.map(m => METHOD_LABELS[m] || m).join(' + ') }}</div>
          </template>
        </el-table-column>
        <el-table-column label="变量 / 输出" width="150">
          <template slot-scope="{ row }">
            {{ row.config.inputs.length }} 个变量 / {{ outputColumns(row.config).length }} 个测点
            <div class="muted small">{{ systemsOf(row.config).join('、') }}</div>
          </template>
        </el-table-column>
        <el-table-column label="基准表" min-width="150">
          <template slot-scope="{ row }">
            <template v-if="row.table">
              <span v-if="row.table.stale" class="warn">需要重建</span>
              <span v-else>{{ row.table.is_default ? '默认表' : '已重建' }}</span>
              <div class="muted small">{{ row.table.created }}</div>
            </template>
            <span v-else class="warn">还没有基准表</span>
          </template>
        </el-table-column>
        <el-table-column label="参与方式" width="130">
          <template slot-scope="{ row }">
            <div @click.stop>
              <el-select v-model="profile[row.id].mode" size="mini" @change="profileDirty = true">
                <el-option v-for="(label, value) in MODE_LABELS" :key="value" :label="label" :value="value" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="预警 / 异常倍数（σ）" width="220">
          <template slot-scope="{ row }">
            <div @click.stop>
              <el-input-number v-model="profile[row.id].sigma_warn" size="mini" :min="1" :max="20" :step="0.5"
                               controls-position="right" style="width: 90px" @change="profileDirty = true" />
              /
              <el-input-number v-model="profile[row.id].sigma_alarm" size="mini" :min="1" :max="20" :step="0.5"
                               controls-position="right" style="width: 90px" @change="profileDirty = true" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" align="center">
          <template slot-scope="{ row }">
            <div @click.stop>
              <el-button type="text" size="mini" @click="openDetail(row)">详情</el-button>
              <el-button type="text" size="mini" @click="openEditor(row)">编辑</el-button>
              <el-button type="text" size="mini" class="danger" @click="removeModel(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 模型详情 -->
    <el-drawer :visible.sync="detail.visible" size="72%" :with-header="false" @closed="onDetailClosed">
      <div v-if="current" class="detail">
        <div class="detail-head">
          <div>
            <span class="detail-title">{{ current.name }}</span>
            <el-tag size="mini" :type="current.source === 'builtin' ? '' : 'info'" class="src-tag">{{ SOURCE_LABELS[current.source] }}</el-tag>
            <el-tag size="mini" type="success" class="src-tag">{{ MODE_LABELS[(current.setting || {}).mode || 'decisive'] }}</el-tag>
            <div class="muted small">{{ current.id }} · {{ current.description }}</div>
          </div>
          <div class="detail-actions">
            <el-button size="mini" icon="el-icon-edit" @click="openEditor(current)">编辑配置</el-button>
            <el-button v-if="current.source === 'override'" size="mini" @click="restoreConfig(current)">恢复内置配置</el-button>
            <el-button v-if="current.table && !current.table.is_default" size="mini" :disabled="running" @click="reset(current)">恢复默认表</el-button>
            <el-button size="mini" type="primary" :disabled="running" @click="openBuild(current)">{{ current.table ? '重建基准表' : '建立基准表' }}</el-button>
            <el-button size="mini" type="danger" plain @click="removeModel(current)">删除模型</el-button>
            <el-button size="mini" icon="el-icon-close" circle @click="detail.visible = false" />
          </div>
        </div>

        <div v-if="job.state === 'running' && job.model_id === current.id" class="job">
          <div class="muted">正在建立：{{ job.stage }} {{ job.total ? `${job.done}/${job.total}` : '' }}</div>
          <el-progress :percentage="jobPercent" :stroke-width="10" />
        </div>
        <div v-else-if="job.state === 'done' && job.model_id === current.id && job.result" class="muted small job">
          上次重建：{{ job.result.created }}，{{ job.operator }} 用 {{ job.source }}（{{ job.result.files }} 个文件）
        </div>
        <el-alert v-else-if="job.state === 'failed' && job.model_id === current.id" class="note" type="error"
                  :closable="false" :title="`上次建立失败：${job.error}`" />

        <el-tabs v-model="detail.tab" class="detail-tabs">
          <!-- 模型信息 -->
          <el-tab-pane label="模型信息" name="info">
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="模型方式">{{ ENGINE_LABELS[current.engine] || current.engine }}</el-descriptions-item>
              <el-descriptions-item label="默认参与方式">{{ MODE_LABELS[current.config.default_mode || 'decisive'] }}</el-descriptions-item>
              <el-descriptions-item label="三维部件" :span="2">{{ componentNames(current.config.components).join('、') || '—' }}</el-descriptions-item>
              <el-descriptions-item label="适用条件" :span="2">
                <template v-if="(current.config.active_if || []).length">
                  <div v-for="(c, k) in current.config.active_if" :key="k">{{ conditionText(c) }}</div>
                </template>
                <span v-else>始终适用</span>
              </el-descriptions-item>
              <el-descriptions-item label="阈值" :span="2">{{ thresholdText(current.config) }}</el-descriptions-item>
            </el-descriptions>

            <div class="section-head sub">变量</div>
            <el-table :data="current.config.inputs" size="mini" border>
              <el-table-column prop="name" label="名称" width="110" />
              <el-table-column label="取法 / 测点" min-width="220">
                <template slot-scope="{ row }">{{ inputSource(row) }}</template>
              </el-table-column>
              <el-table-column label="备用测点" width="130">
                <template slot-scope="{ row }">{{ (row.fallback_columns || []).join('、') || '—' }}</template>
              </el-table-column>
              <el-table-column label="单位换算" width="130">
                <template slot-scope="{ row }">{{ convText(row) }}</template>
              </el-table-column>
              <el-table-column prop="unit" label="单位" width="70" />
              <el-table-column v-if="current.engine === 'surrogate'" label="角色" width="110">
                <template slot-scope="{ row }">
                  {{ ROLE_LABELS[row.role || 'auto'] }}
                  <span v-if="(row.role || 'auto') === 'auto' && current.table && current.table.roles && current.table.roles[row.name]" class="muted">
                    （{{ ROLE_LABELS[current.table.roles[row.name]] }}）
                  </span>
                </template>
              </el-table-column>
              <el-table-column v-else label="网格" min-width="160">
                <template slot-scope="{ row }">{{ (row.grid || []).join(' / ') }}</template>
              </el-table-column>
              <el-table-column label="有效范围" width="110">
                <template slot-scope="{ row }">{{ row.valid && row.valid.length ? row.valid.join(' ~ ') : '—' }}</template>
              </el-table-column>
            </el-table>

            <div class="section-head sub">输出（测点）</div>
            <el-table :data="current.config.outputs" size="mini" border>
              <el-table-column label="所属系统" width="150">
                <template slot-scope="{ row }">{{ row.system || '—' }}</template>
              </el-table-column>
              <el-table-column prop="name" label="名称" min-width="120" />
              <el-table-column v-if="current.engine === 'surrogate'" label="计算方式" width="90">
                <template slot-scope="{ row }">{{ METHOD_LABELS[row.method || 'autofit'] || row.method }}</template>
              </el-table-column>
              <el-table-column label="类型" width="60">
                <template slot-scope="{ row }">{{ KIND_LABELS[row.kind] || row.kind }}</template>
              </el-table-column>
              <el-table-column prop="unit" label="单位" width="60" />
              <el-table-column label="对应测点" min-width="170">
                <template slot-scope="{ row }">{{ (row.columns || []).join('、') }}</template>
              </el-table-column>
              <el-table-column label="残差" width="60">
                <template slot-scope="{ row }">{{ row.residual === 'absolute' ? '绝对' : '相对' }}</template>
              </el-table-column>
              <el-table-column label="单测点偏离" width="90">
                <template slot-scope="{ row }">{{ row.single === 'notice' ? '补充依据' : '参与结论' }}</template>
              </el-table-column>
              <el-table-column label="三维部件" width="140">
                <template slot-scope="{ row }">{{ componentNames([row.component]).join('') || '—' }}</template>
              </el-table-column>
            </el-table>

            <div class="section-head sub">判定规则</div>
            <div class="rule">
              <div>单测点偏离：各测点扣除标定偏差后，偏离超过阈值判预警 / 异常。</div>
              <div v-if="groupRule(current.config)">
                整体偏移：{{ groupOutputs(current.config).join('、') }} 中至少 {{ groupRule(current.config).min_columns || 3 }} 个测点彼此一致、整体偏离时，
                判为“{{ MEANING_LABELS[groupRule(current.config).meaning] }}”<template v-if="groupRule(current.config).driver">（沿 {{ groupRule(current.config).driver }} 判断）</template><template v-if="groupRule(current.config).input">（对应输入 {{ groupRule(current.config).input }}）</template>。
              </div>
            </div>

            <template v-if="current.engine === 'amesim' || (current.config.amesim && current.config.amesim.parameters && current.config.amesim.parameters.length)">
              <div class="section-head sub">AMESim</div>
              <el-descriptions :column="2" size="small" border>
                <el-descriptions-item label="模型文件">{{ current.config.amesim.model_file }}</el-descriptions-item>
                <el-descriptions-item label="服务地址">{{ current.config.amesim.url || '—' }}</el-descriptions-item>
                <el-descriptions-item label="参数映射" :span="2">
                  <div v-for="(p, k) in current.config.amesim.parameters" :key="k">
                    {{ p.input }}{{ p.derive ? `（${DERIVE_LABELS[p.derive]}）` : '' }} → {{ Array.isArray(p.params) ? p.params.join('、') : (p.params || 'input.data') }}
                  </div>
                </el-descriptions-item>
                <el-descriptions-item label="输出变量" :span="2">
                  <div v-for="(v, k) in current.config.amesim.variables" :key="k">{{ k }} ← {{ v }}</div>
                </el-descriptions-item>
              </el-descriptions>
            </template>
          </el-tab-pane>

          <!-- 模型公式 -->
          <el-tab-pane v-if="current.table && current.table.kind === 'formula'" label="模型公式" name="formulas">
            <div class="formula-head muted small">
              每个输出的公式与检验结果（{{ current.table.calibration.files }} 个正常数据文件，{{ current.table.calibration.method }}）。
              <template v-if="excludedFiles.length">
                已排除 {{ excludedFiles.length }} 个文件：
                <el-tag v-for="f in excludedFiles" :key="f" size="mini" closable class="excluded" @close="includeFile(f)">{{ f }}</el-tag>
              </template>
            </div>
            <div v-for="o in current.config.outputs" :key="o.name" class="formula-card">
              <div class="formula-card-head">
                <b>{{ o.name }}</b> <span class="muted">{{ o.unit }}</span>
                <span v-if="o.system" class="muted small">· {{ o.system }}</span>
                <span class="grow" />
                <el-button v-if="formulaOf(o.name) && formulaOf(o.name).method !== 'formula'" size="mini" type="text"
                           @click="toCustomFormula(o.name)">转为自定义公式</el-button>
              </div>
              <fit-result v-if="formulaOf(o.name)" :result="formulaOf(o.name)" selectable @pick="onPick(o.name, $event)" />
              <el-alert v-else-if="current.table.calibration.failed_outputs[o.name]" type="error" :closable="false"
                        :title="`未建立：${current.table.calibration.failed_outputs[o.name]}`" />
              <span v-else class="muted small">没有该输出的结果（配置修改后请重建）</span>
            </div>
            <div v-if="pickedCount" class="exclude-bar">
              已选 {{ pickedCount }} 个可疑样本
              <el-button size="mini" type="warning" @click="excludePicked">排除这些样本并重建</el-button>
            </div>
          </el-tab-pane>

          <!-- 基准表与标定 -->
          <el-tab-pane label="基准表与标定" name="table">
            <template v-if="current.table">
              <el-descriptions :column="2" size="small" border>
                <el-descriptions-item label="模型">
                  <el-tag size="mini">{{ current.table.model.label }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="建立时间">{{ current.table.created }}</el-descriptions-item>
                <el-descriptions-item label="工况网格" :span="2">
                  <span v-for="i in current.table.inputs" :key="i.name" class="grid-item">
                    {{ i.name }}（{{ i.source }}）：{{ i.grid.join(' / ') }} {{ i.unit }}
                  </span>
                </el-descriptions-item>
                <el-descriptions-item label="标定" :span="2">
                  {{ current.table.calibration.files }} 个正常数据文件，{{ current.table.calibration.method }}
                </el-descriptions-item>
                <el-descriptions-item label="来源" :span="2">
                  {{ current.table.is_default ? '随代码提供的默认表（2026-11 正常数据）' : current.table.source }}
                </el-descriptions-item>
              </el-descriptions>
              <el-alert v-if="current.table.stale" class="note" type="warning" :closable="false" show-icon
                        title="模型配置已修改（输入或输出变了），这张基准表已作废，重建前该模型不参与诊断" />
              <div class="section-head sub">
                <span>
                  标定结果（模型 vs 正常数据）
                  <el-tooltip placement="right">
                    <div slot="content">
                      固有偏差：正常时该测点比模型预期高/低多少（随工况变化，此处为平均值），诊断时先扣除。<br>
                      离散 σ：扣除后的波动，决定阈值；σ 越小，模型能发现的偏离越小。
                    </div>
                    <i class="el-icon-question tip" />
                  </el-tooltip>
                </span>
              </div>
              <el-table :data="current.table.calibration.columns" size="small" border>
                <el-table-column prop="column" label="测点" min-width="140" />
                <el-table-column prop="output" label="模型输出" min-width="120" />
                <el-table-column label="固有偏差" width="110" align="right">
                  <template slot-scope="{ row }">{{ val(row.bias, row, true) }}</template>
                </el-table-column>
                <el-table-column label="离散σ" width="100" align="right">
                  <template slot-scope="{ row }">{{ val(row.std, row) }}</template>
                </el-table-column>
                <el-table-column label="预警 / 异常" width="170" align="right">
                  <template slot-scope="{ row }">±{{ val(row.warn, row) }} / ±{{ val(row.alarm, row) }}</template>
                </el-table-column>
                <el-table-column label="提示" min-width="160">
                  <template slot-scope="{ row }"><span v-if="row.warning" class="warn small">{{ row.warning }}</span></template>
                </el-table-column>
              </el-table>
            </template>
            <el-empty v-else description="还没有基准表，点击右上角“建立基准表”" :image-size="70" />
          </el-tab-pane>

          <!-- 工况试算 -->
          <el-tab-pane label="工况试算" name="predict" :disabled="!current.table">
            <el-row v-if="current.table && conditions[current.id]" :gutter="16">
              <el-col :span="10">
                <el-form size="small" label-width="90px" @submit.native.prevent>
                  <el-form-item v-for="i in current.table.inputs" :key="i.name" :label="i.name">
                    <el-input-number v-model="conditions[current.id][i.name]" :step="stepOf(i)" :precision="precisionOf(i)" controls-position="right" />
                    <span class="unit">{{ i.unit }}</span>
                  </el-form-item>
                  <el-form-item>
                    <el-button type="primary" @click="runPredict(current)">计算预期值</el-button>
                  </el-form-item>
                </el-form>
                <div v-if="current.table.inputs.length > 1" class="small muted">
                  曲线横轴：
                  <el-select v-model="curveVar" size="mini" style="width: 130px" @change="drawCurve(current)">
                    <el-option v-for="i in current.table.inputs" :key="i.name" :label="i.name" :value="i.name" />
                  </el-select>
                </div>
                <div ref="curve" class="curve" />
              </el-col>
              <el-col :span="14">
                <template v-if="predictions[current.id]">
                  <el-alert v-if="predictions[current.id].outside.length" type="warning" :closable="false"
                            :title="`超出基准表范围：${predictions[current.id].outside.join('、')}`" />
                  <el-table :data="predictions[current.id].expected" size="small" border>
                    <el-table-column prop="name" label="模型输出" />
                    <el-table-column label="预期值" align="right">
                      <template slot-scope="{ row }">{{ fmt(row.value, row.unit) }}</template>
                    </el-table-column>
                  </el-table>
                </template>
              </el-col>
            </el-row>
          </el-tab-pane>

          <el-tab-pane v-if="current.config.media && current.config.media.video" label="仿真动画" name="media">
            <video class="video" controls preload="metadata" :src="publicPath + current.config.media.video">您的浏览器不支持视频播放。</video>
            <div class="muted small">{{ current.config.media.caption }}</div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>

    <el-dialog :title="`重建基准表：${build.model ? build.model.name : ''}`" :visible.sync="build.visible" width="560px" append-to-body>
      <el-form v-if="build.model" label-width="110px" size="small">
        <el-form-item label="模型引擎">
          <el-radio-group v-model="build.engine">
            <el-radio v-for="e in build.model.engines" :key="e.type" :label="e.type" :disabled="!e.ready">{{ e.label }}</el-radio>
          </el-radio-group>
          <div v-for="e in notReady" :key="e.type" class="warn small">{{ e.label }}：请先在“编辑配置”的 AMESim 页填写模型文件与变量路径</div>
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

    <el-dialog title="派生测点" :visible.sync="derived.visible" width="760px" append-to-body>
      <div class="muted small derived-hint">
        派生测点由采集列换算得到，如涡轮流量计转速 f（Hz）由流量 q（L/h）按 q = K·f + q0 反算。修改后，用到这些测点的模型需要重建；三维与工作台刷新页面后生效。
      </div>
      <el-table :data="derived.items" size="mini" border>
        <el-table-column prop="name" label="派生测点" width="150" />
        <el-table-column prop="source" label="源测点" width="110" />
        <el-table-column width="150">
          <template slot="header">K（每 {{ derived.items[0] ? derived.items[0].unit || '单位' : '' }}）</template>
          <template slot-scope="{ row }"><el-input v-model="row.K" size="mini" /></template>
        </el-table-column>
        <el-table-column label="q0" width="120">
          <template slot-scope="{ row }"><el-input v-model="row.q0" size="mini" /></template>
        </el-table-column>
        <el-table-column label="下限" width="80">
          <template slot-scope="{ row }"><el-input v-model="row.min" size="mini" /></template>
        </el-table-column>
        <el-table-column label="换算">
          <template slot-scope="{ row }"><span class="small">({{ row.source }} − {{ row.q0 }}) ÷ {{ row.K }}</span></template>
        </el-table-column>
      </el-table>
      <span slot="footer">
        <el-button @click="derived.visible = false">取消</el-button>
        <el-button type="primary" :loading="derived.saving" @click="saveDerivedItems">保存</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import { addDataDir, getDataDirs } from '@/api/files'
import {
  ENGINE_LABELS, KIND_LABELS, MEANING_LABELS, METHOD_LABELS, MODE_LABELS, ROLE_LABELS, buildModelTable, deleteModel,
  getDerived, getSimulationStatus, predictModel, resetModelTable, restoreBuiltinModel, saveDerived, saveDiagnosisProfile,
  updateModel
} from '@/api/simulation'
import { setDerivedFields } from '@/utils/features'
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
      deletedBuiltins: [],
      builders: [],
      derived: { visible: false, items: [], saving: false },
      curveVar: '',
      picks: {},
      job: { state: 'idle' },
      profile: {},
      profileDirty: false,
      detail: { visible: false, id: '', tab: 'info' },
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
      return this.models.find(m => m.id === this.detail.id) || null
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
    'detail.tab'(tab) {
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
    openDetail(row) {
      this.detail = { visible: true, id: row.id, tab: 'info' }
      this.picks = {}
      this.curveVar = ''
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
    /** 自动拟合的结果转为自定义公式（系数固定），之后可在编辑页手工修改 */
    async toCustomFormula(name) {
      const m = this.current
      const f = this.formulaOf(name)
      try {
        await this.$confirm(`把“${name}”的自动拟合结果转为自定义公式（系数固定）？之后可以在“编辑配置”中修改公式，需要重建模型后生效。`,
          '转为自定义公式', { type: 'info' })
      } catch (e) {
        return
      }
      const cfg = JSON.parse(JSON.stringify(m.config))
      const o = cfg.outputs.find(x => x.name === name)
      o.method = 'formula'
      o.formula = {
        expression: f.expression,
        coefficients: Object.fromEntries(Object.entries(f.coefficients).map(([k, v]) => [k, { value: v, fit: false }]))
      }
      if (await this.saveConfig(m, cfg, '已转为自定义公式，请重建模型')) this.openBuild(this.current)
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
    async openDerived() {
      try {
        const { items } = await getDerived()
        this.derived.items = items.map(i => ({
          ...i,
          K: +(1 / i.scale).toPrecision(8),
          q0: +(-(i.offset || 0) / i.scale).toPrecision(8),
          min: i.min === undefined ? '' : i.min
        }))
        this.derived.visible = true
      } catch (e) {
        this.$message.error(errorMessage(e))
      }
    },
    async saveDerivedItems() {
      this.derived.saving = true
      try {
        const items = this.derived.items.map(i => {
          const K = Number(i.K)
          const q0 = Number(i.q0 || 0)
          if (!K) throw new Error(`${i.name} 的 K 不能为 0`)
          return { name: i.name, source: i.source, scale: 1 / K, offset: -q0 / K, min: i.min === '' ? undefined : Number(i.min) }
        })
        const saved = await saveDerived(items)
        setDerivedFields(saved.items)
        this.derived.visible = false
        this.applyStatus(await getSimulationStatus(), true)
        this.$message.success('已保存；用到这些测点的模型已标记为需要重建')
      } catch (e) {
        this.$message.error(errorMessage(e))
      } finally {
        this.derived.saving = false
      }
    },
    onDetailClosed() {
      if (this.chart) {
        this.chart.dispose()
        this.chart = null
      }
    },
    async restoreBuiltin(d) {
      try {
        this.applyStatus(await restoreBuiltinModel(d.id), true)
        this.$message.success(`已恢复内置模型“${d.name}”`)
      } catch (e) {
        this.$message.error(errorMessage(e))
      }
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
      this.deletedBuiltins = st.deleted_builtins || []
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
      if (this.detail.visible && !st.models.some(m => m.id === this.detail.id)) this.detail.visible = false
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
          if (m && this.detail.visible && m.id === this.detail.id && this.detail.tab === 'predict') this.runPredict(m)
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
    openEditor(m) {
      this.editor = { visible: true, model: m ? m.config : null }
    },
    async onSaved(model) {
      this.editor.visible = false
      this.$delete(this.predictions, model.id)
      this.$delete(this.conditions, model.id)
      this.applyStatus(await getSimulationStatus(), true)
      this.detail = { visible: true, id: model.id, tab: 'info' }
    },
    async removeModel(m) {
      const builtin = m.source !== 'custom'
      try {
        await this.$confirm(builtin
          ? `删除模型“${m.name}”？删除后不再参与诊断；内置模型可以在页面右上角“恢复已删除的内置模型”中恢复。`
          : `删除模型“${m.name}”及其基准表？删除后不能恢复。`, '删除模型', { type: 'warning', confirmButtonText: '删除' })
      } catch (e) {
        return
      }
      try {
        const st = await deleteModel(m.id)
        this.$delete(this.predictions, m.id)
        this.$delete(this.conditions, m.id)
        if (this.detail.id === m.id) this.detail.visible = false
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
      if (this.detail.tab === 'predict') this.runPredict(this.models.find(x => x.id === m.id))
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
      if (!dom || this.detail.id !== m.id) return
      if (this.chart && this.chart.getDom() !== dom) {
        this.chart.dispose()
        this.chart = null
      }
      if (!this.chart) this.chart = echarts.init(dom)
      const now = this.predictions[m.id].expected.find(e => e.name === out.name)
      this.chart.setOption({
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
      this.chart.resize()
    },
    resize() {
      if (this.chart) this.chart.resize()
    }
  }
}
</script>

<style scoped>
.model-table >>> .el-table__row {
  cursor: pointer;
}
.model-name {
  font-weight: 600;
}
.ellipsis {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.danger {
  color: #f56c6c;
}
.detail {
  padding: 18px 22px;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
}
.detail-title {
  font-size: 18px;
  font-weight: 600;
}
.detail-actions {
  flex-shrink: 0;
}
.detail-tabs {
  margin-top: 8px;
}
.section-head.sub {
  margin: 16px 0 8px;
}
.rule {
  line-height: 1.9;
  color: #606266;
}
.page-header {
  margin-bottom: 12px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.tip {
  margin-left: 4px;
  color: #909399;
  cursor: help;
}
.src-tag {
  margin-left: 6px;
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
.formula-head {
  margin-bottom: 8px;
}
.excluded {
  margin: 0 4px 4px 0;
}
.formula-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.formula-card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.grow {
  flex: 1;
}
.exclude-bar {
  position: sticky;
  bottom: 0;
  background: #fffbeb;
  border: 1px solid #fde68a;
  padding: 8px 12px;
  border-radius: 6px;
}
.derived-hint {
  margin-bottom: 8px;
}
.video {
  max-width: 720px;
  width: 100%;
  border-radius: 4px;
  background: #000;
}
</style>
