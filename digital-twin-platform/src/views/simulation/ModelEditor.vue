<template>
  <el-dialog :title="isNew ? '新建仿真模型' : `编辑模型：${form.name}`" :visible="visible" width="1180px" top="3vh" append-to-body
             :close-on-click-modal="false" @close="$emit('close')">
    <el-tabs v-model="tab" class="editor">
      <!-- 基本信息 -->
      <el-tab-pane label="基本信息" name="basic">
        <el-form label-width="110px" size="small">
          <el-form-item label="模型编号" required>
            <el-input v-model.trim="form.id" :disabled="!isNew" placeholder="英文字母开头，如 filter_dp" style="width: 260px" />
          </el-form-item>
          <el-form-item label="模型名称" required>
            <el-input v-model.trim="form.name" placeholder="如：过滤器压差模型" style="width: 360px" />
          </el-form-item>
          <el-form-item label="说明">
            <el-input v-model="form.description" placeholder="对应哪部分、输入什么、输出什么" />
          </el-form-item>
          <el-form-item label="模型方式" required>
            <el-radio-group v-model="form.engine">
              <el-radio label="surrogate">数据拟合</el-radio>
              <el-radio label="amesim">仿真（AMESim）</el-radio>
            </el-radio-group>
            <el-tooltip placement="right" content="数据拟合：由正常数据拟合出各输出与变量的关系，建立模型时只需选正常数据目录；仿真：在“AMESim”页填写模型文件、参数与变量路径，建立模型时由 AMESim 逐个工况仿真">
              <i class="el-icon-question tip" />
            </el-tooltip>
          </el-form-item>
          <el-form-item label="三维部件">
            <el-select v-model="form.components" multiple filterable placeholder="诊断出问题时在三维模型上告警的部件" style="width: 100%">
              <el-option v-for="(c, key) in components" :key="key" :label="c.label" :value="key" />
            </el-select>
          </el-form-item>
          <el-form-item label="默认参与方式">
            <el-select v-model="form.default_mode" style="width: 160px">
              <el-option label="参与结论" value="decisive" />
              <el-option label="仅作参考" value="reference" />
              <el-option label="关闭" value="off" />
            </el-select>
          </el-form-item>
          <el-form-item label="适用条件">
            <el-table :data="form.active_if" size="mini" border style="width: 100%">
              <el-table-column label="测点" min-width="180">
                <template slot-scope="{ row }">
                  <el-select v-model="row.column" filterable allow-create size="mini" style="width: 100%">
                    <el-option v-for="c in columns" :key="c" :label="c" :value="c" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="不低于" width="100">
                <template slot-scope="{ row }"><el-input v-model="row.min" size="mini" /></template>
              </el-table-column>
              <el-table-column label="不高于" width="100">
                <template slot-scope="{ row }"><el-input v-model="row.max" size="mini" /></template>
              </el-table-column>
              <el-table-column label="说明" min-width="140">
                <template slot-scope="{ row }"><el-input v-model.trim="row.note" size="mini" placeholder="如：大流量管路工作" /></template>
              </el-table-column>
              <el-table-column width="50">
                <template slot-scope="{ $index }">
                  <el-button type="text" icon="el-icon-delete" @click="form.active_if.splice($index, 1)" />
                </template>
              </el-table-column>
            </el-table>
            <el-button size="mini" icon="el-icon-plus" class="add" @click="form.active_if.push({ column: '', min: '', max: '', note: '' })">添加条件</el-button>
            <el-tooltip placement="right" content="测点均值满足全部条件时模型才参与诊断、才用于标定（如小流量管路模型只在小流量管路有流量时适用）；不填则始终适用">
              <i class="el-icon-question tip" />
            </el-tooltip>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <!-- 变量 -->
      <el-tab-pane label="变量" name="inputs">
        <div class="tab-hint muted">
          变量是模型的输入，{{ isSurrogate ? '公式里直接用变量名' : '建表时按网格逐点运行模型' }}。单位换算：取得的值 × 系数 + 偏移，换成公式需要的单位（如 kg/h → kg/s：× 0.000277778）。
        </div>
        <el-table :data="form.inputs" size="mini" border>
          <el-table-column label="名称" width="110">
            <template slot-scope="{ row }"><el-input v-model.trim="row.name" size="mini" /></template>
          </el-table-column>
          <el-table-column label="来源" width="140">
            <template slot-scope="{ row }">
              <el-select v-model="row.source" size="mini">
                <el-option label="单个测点" value="single" />
                <el-option label="多个测点取中位数" value="multi" />
                <el-option label="由油温算燃油密度" value="density" />
                <el-option label="由油温算运动黏度" value="viscosity" />
                <el-option label="常数" value="constant" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="测点 / 数值" min-width="190">
            <template slot-scope="{ row }">
              <el-select v-if="row.source === 'multi'" v-model="row.columns" multiple filterable allow-create size="mini" style="width: 100%">
                <el-option v-for="c in columns" :key="c" :label="c" :value="c" />
              </el-select>
              <el-select v-else-if="row.source === 'density' || row.source === 'viscosity'" v-model="row.temperature_column" filterable
                         allow-create size="mini" placeholder="油温测点" style="width: 100%">
                <el-option v-for="c in columns" :key="c" :label="c" :value="c" />
              </el-select>
              <el-input v-else-if="row.source === 'constant'" v-model="row.constant" size="mini" placeholder="数值" />
              <el-select v-else v-model="row.column" filterable allow-create size="mini" style="width: 100%">
                <el-option v-for="c in columns" :key="c" :label="c" :value="c" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="备用测点" width="120">
            <template slot-scope="{ row }">
              <el-select v-if="row.source !== 'multi' && row.source !== 'constant'" v-model="row.fallback" filterable allow-create clearable
                         size="mini" placeholder="主测点无效时用" style="width: 100%">
                <el-option v-for="c in columns" :key="c" :label="c" :value="c" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="单位换算（× 系数 + 偏移）" width="190">
            <template slot-scope="{ row }">
              <div v-if="row.source !== 'constant'" class="conv">
                ×<el-input v-model="row.scale" size="mini" placeholder="1" />
                +<el-input v-model="row.offset" size="mini" placeholder="0" />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="单位" width="70">
            <template slot-scope="{ row }"><el-input v-model.trim="row.unit" size="mini" /></template>
          </el-table-column>
          <el-table-column v-if="isSurrogate && usesRoles" width="110">
            <template slot="header">
              角色
              <el-tooltip placement="top">
                <div slot="content">
                  自动拟合按角色确定公式结构：主变量最高三次、次变量二次、环境变量（油温等）一次，加交叉项。<br>
                  自动：按数据建议（与输出最相关的为主变量，温度类为环境变量，不变的不使用）。
                </div>
                <i class="el-icon-question tip" />
              </el-tooltip>
            </template>
            <template slot-scope="{ row }">
              <el-select v-model="row.role" size="mini">
                <el-option v-for="(label, value) in ROLE_LABELS" :key="value" :label="label" :value="value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column v-if="!isSurrogate" width="150">
            <template slot="header">
              网格
              <el-tooltip content="建表时运行模型的工况点，逗号分隔，应覆盖正常数据的工况范围" placement="top"><i class="el-icon-question tip" /></el-tooltip>
            </template>
            <template slot-scope="{ row }"><el-input v-model="row.grid" size="mini" placeholder="1000, 2000, 3000" /></template>
          </el-table-column>
          <el-table-column width="100">
            <template slot="header">
              有效范围
              <el-tooltip content="超出时认为该测点读数无效（如断路），改用备用测点；可不填" placement="top"><i class="el-icon-question tip" /></el-tooltip>
            </template>
            <template slot-scope="{ row }"><el-input v-model="row.valid" size="mini" placeholder="下限,上限" /></template>
          </el-table-column>
          <el-table-column width="44">
            <template slot-scope="{ $index }">
              <el-button type="text" icon="el-icon-delete" :disabled="form.inputs.length <= 1" @click="form.inputs.splice($index, 1)" />
            </template>
          </el-table-column>
        </el-table>
        <el-button size="mini" icon="el-icon-plus" class="add" @click="form.inputs.push(blankInput())">添加变量</el-button>
      </el-tab-pane>

      <!-- 输出 -->
      <el-tab-pane label="输出" name="outputs">
        <div v-if="isSurrogate" class="preview-bar">
          <span class="muted">验证用的正常数据目录：</span>
          <el-autocomplete v-model="previewPath" :fetch-suggestions="suggestDirs" size="mini" placeholder="设备正常时采集的数据目录（完整路径）"
                           style="width: 420px" />
          <el-button size="mini" type="primary" plain :loading="previewing === '*'" :disabled="!previewPath" @click="runPreview(null)">全部验证</el-button>
          <span class="muted small">展开每个输出可编辑公式、单独验证；验证不保存任何东西</span>
        </div>
        <el-table ref="outputs" :data="form.outputs" size="mini" border row-key="_key" :expand-row-keys="expanded"
                  @expand-change="onExpand">
          <el-table-column v-if="isSurrogate" type="expand" width="30">
            <template slot-scope="{ row }">
              <div class="method-panel">
                <div v-if="!builderOf(row.method)" class="builtin-note">
                  <i class="el-icon-lock" /> 内置模型：该输出的计算由后端配置，可以验证精度
                </div>
                <el-form v-else inline size="mini" class="options">
                  <el-form-item v-if="builders.length > 1" label="计算方式">
                    <el-select v-model="row.method" style="width: 130px" @change="onMethod(row)">
                      <el-option v-for="b in builders" :key="b.kind" :label="b.label" :value="b.kind" :disabled="!b.available" />
                    </el-select>
                  </el-form-item>
                  <el-form-item v-for="opt in builderOf(row.method).options" :key="opt.key" :label="opt.label">
                    <el-select v-if="opt.type === 'select'" v-model="row.options[row.method][opt.key]" style="width: 110px">
                      <el-option v-for="c in opt.choices" :key="String(c.value)" :label="c.label" :value="c.value" />
                    </el-select>
                    <el-input-number v-else-if="opt.type === 'number'" v-model="row.options[row.method][opt.key]" :min="opt.min" :max="opt.max"
                                     :step="opt.key === 'ridge' ? 0.0001 : 1" :precision="opt.key === 'ridge' ? 4 : 0"
                                     controls-position="right" style="width: 110px" />
                    <el-input v-else v-model="row.options[row.method][opt.key]" style="width: 220px" />
                    <el-tooltip v-if="opt.help" :content="opt.help" placement="top"><i class="el-icon-question tip" /></el-tooltip>
                  </el-form-item>
                  <div class="muted small">{{ builderOf(row.method).description }}</div>
                </el-form>
                <div class="panel-actions">
                  <el-button size="mini" type="primary" :loading="previewing === row.name" :disabled="!previewPath || !row.name"
                             @click="runPreview(row)">{{ builderOf(row.method) ? '试拟合' : '验证精度' }}</el-button>
                  <span v-if="!previewPath" class="muted small">先在上方选择正常数据目录</span>
                </div>
                <fit-result v-if="previews[row.name]" :result="previews[row.name]" />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="名称" width="120">
            <template slot-scope="{ row }"><el-input v-model.trim="row.name" size="mini" /></template>
          </el-table-column>
          <el-table-column label="类型" width="76">
            <template slot-scope="{ row }">
              <el-select v-model="row.kind" size="mini">
                <el-option v-for="(label, value) in KIND_LABELS" :key="value" :label="label" :value="value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="单位" width="64">
            <template slot-scope="{ row }"><el-input v-model.trim="row.unit" size="mini" /></template>
          </el-table-column>
          <el-table-column label="所属系统" width="120">
            <template slot-scope="{ row }">
              <el-select v-model="row.system" filterable allow-create clearable size="mini">
                <el-option v-for="name in SYSTEMS" :key="name" :label="name" :value="name" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column width="70">
            <template slot="header">
              残差
              <el-tooltip content="相对：偏差 ÷ 预期值，适合流量、转速等；绝对：直接相减，适合温度和接近 0 的量（如油箱压力）" placement="top"><i class="el-icon-question tip" /></el-tooltip>
            </template>
            <template slot-scope="{ row }">
              <el-select v-model="row.residual" size="mini">
                <el-option label="相对" value="relative" />
                <el-option label="绝对" value="absolute" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column min-width="180">
            <template slot="header">
              对应测点
              <el-tooltip content="同一处的多只表可以一起选，各自与同一个预期值比较" placement="top"><i class="el-icon-question tip" /></el-tooltip>
            </template>
            <template slot-scope="{ row }">
              <el-select v-model="row.columns" multiple filterable allow-create size="mini" style="width: 100%">
                <el-option v-for="c in columns" :key="c" :label="c" :value="c" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column width="96">
            <template slot="header">
              单测点偏离
              <el-tooltip content="参与结论：该测点偏离时判预警/异常；补充依据：只作为其他原因的依据（如已有互校的流量计）" placement="top"><i class="el-icon-question tip" /></el-tooltip>
            </template>
            <template slot-scope="{ row }">
              <el-select v-model="row.single" size="mini">
                <el-option label="参与结论" value="decisive" />
                <el-option label="补充依据" value="notice" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="三维部件" width="120">
            <template slot-scope="{ row }">
              <el-select v-model="row.component" clearable filterable size="mini">
                <el-option v-for="(c, key) in components" :key="key" :label="c.label" :value="key" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column width="56">
            <template slot="header">
              随流量
              <el-tooltip content="与流量相关的压力：判断“实际流量变化”时用来确认" placement="top"><i class="el-icon-question tip" /></el-tooltip>
            </template>
            <template slot-scope="{ row }"><el-checkbox v-model="row.flow_dependent" :disabled="row.kind !== 'pressure'" /></template>
          </el-table-column>
          <el-table-column width="44">
            <template slot-scope="{ $index }">
              <el-button type="text" icon="el-icon-delete" :disabled="form.outputs.length <= 1" @click="form.outputs.splice($index, 1)" />
            </template>
          </el-table-column>
        </el-table>
        <el-button size="mini" icon="el-icon-plus" class="add" @click="addOutput">添加输出</el-button>
      </el-tab-pane>

      <!-- 判定规则 -->
      <el-tab-pane label="判定规则" name="rules">
        <el-form label-width="130px" size="small">
          <el-form-item label="阈值倍数（σ）">
            预警 <el-input-number v-model="form.sigma_warn" :min="1" :max="20" :step="0.5" controls-position="right" style="width: 100px" />
            异常 <el-input-number v-model="form.sigma_alarm" :min="1" :max="20" :step="0.5" controls-position="right" style="width: 100px" />
            <el-tooltip content="阈值 = max(下限, 倍数 × 标定离散 σ)" placement="right"><i class="el-icon-question tip" /></el-tooltip>
          </el-form-item>
          <el-form-item v-for="kind in usedKinds" :key="kind" :label="`${KIND_LABELS[kind]}阈值下限`">
            预警 <el-input-number v-model="form.floors[kind].warn" :min="0" :step="kind === 'temperature' ? 0.5 : 0.5" :precision="1"
                                 controls-position="right" style="width: 100px" />
            异常 <el-input-number v-model="form.floors[kind].alarm" :min="0" :step="0.5" :precision="1"
                                 controls-position="right" style="width: 100px" />
            <span class="unit">{{ kind === 'temperature' ? '℃（绝对偏差）' : '%（相对偏差）' }}</span>
          </el-form-item>
          <el-form-item v-for="kind in absKinds" :key="`abs-${kind}`" :label="`${KIND_LABELS[kind]}绝对阈值下限`">
            预警 <el-input-number v-model="form.floorsAbs[kind].warn" :min="0" :step="0.01" :precision="3"
                                 controls-position="right" style="width: 110px" />
            异常 <el-input-number v-model="form.floorsAbs[kind].alarm" :min="0" :step="0.01" :precision="3"
                                 controls-position="right" style="width: 110px" />
            <span class="unit">与测点同单位（残差为“绝对”的{{ KIND_LABELS[kind] }}输出使用）</span>
          </el-form-item>
          <el-divider content-position="left">整体偏移</el-divider>
          <el-form-item label="启用">
            <el-switch v-model="form.groupEnabled" />
            <el-tooltip placement="right" content="一组测点彼此一致、整体偏离模型预期时，判为一个整体原因，而不是每个测点各报一次">
              <i class="el-icon-question tip" />
            </el-tooltip>
          </el-form-item>
          <template v-if="form.groupEnabled">
            <el-form-item label="参与的输出">
              <el-select v-model="form.group.outputs" multiple style="width: 100%">
                <el-option v-for="o in form.outputs" :key="o.name" :label="o.name" :value="o.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="含义">
              <el-select v-model="form.group.meaning" style="width: 380px">
                <el-option v-for="(label, value) in MEANING_LABELS" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.group.meaning === 'pump'" label="决定流量的输入">
              <el-select v-model="form.group.driver" clearable placeholder="默认第一个输入">
                <el-option v-for="i in form.inputs" :key="i.name" :label="i.name" :value="i.name" />
              </el-select>
              <el-tooltip placement="right" content="判断“实际流量变化”时沿这个输入求压力随流量的变化（如被试泵由电传转速决定流量）">
                <i class="el-icon-question tip" />
              </el-tooltip>
            </el-form-item>
            <el-form-item v-if="form.group.meaning === 'input'" label="对应的输入">
              <el-select v-model="form.group.input">
                <el-option v-for="i in form.inputs" :key="i.name" :label="i.name" :value="i.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="至少几个测点一致">
              <el-input-number v-model="form.group.min_columns" :min="1" :max="20" controls-position="right" />
            </el-form-item>
            <el-form-item label="三维部件">
              <el-select v-model="form.group.component" clearable filterable>
                <el-option v-for="(c, key) in components" :key="key" :label="c.label" :value="key" />
              </el-select>
            </el-form-item>
          </template>
        </el-form>
      </el-tab-pane>

      <!-- AMESim -->
      <el-tab-pane label="AMESim" name="amesim" :disabled="form.engine !== 'amesim'">
        <el-form label-width="130px" size="small">
          <el-form-item label="模型文件" required>
            <el-input v-model.trim="form.amesim.model_file" placeholder="放在 AMESim 服务模型目录中的 .ame 文件名" style="width: 360px" />
          </el-form-item>
          <el-form-item label="服务地址">
            <el-input v-model.trim="form.amesim.url" placeholder="http://127.0.0.1:5003" style="width: 260px" />
          </el-form-item>
          <el-form-item label="仿真时长 / 稳态取末段">
            <el-input-number v-model="form.amesim.stop_time_s" :min="1" controls-position="right" style="width: 110px" /> 秒 /
            <el-input-number v-model="form.amesim.steady_tail_s" :min="0.1" controls-position="right" style="width: 110px" /> 秒
          </el-form-item>
          <el-divider content-position="left">输入怎样设置到模型</el-divider>
          <el-table :data="form.amesim.parameters" size="mini" border>
            <el-table-column label="输入" width="130">
              <template slot-scope="{ row }">
                <el-select v-model="row.input" size="mini">
                  <el-option v-for="i in form.inputs" :key="i.name" :label="i.name" :value="i.name" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="换算" width="110">
              <template slot-scope="{ row }">
                <el-select v-model="row.derive" clearable size="mini" placeholder="不换算">
                  <el-option label="油温" value="temperature" />
                  <el-option label="由油温算密度" value="density" />
                  <el-option label="由油温算黏度" value="viscosity" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="设置方式" width="150">
              <template slot-scope="{ row }">
                <el-select v-model="row.kind" size="mini">
                  <el-option label="部件参数" value="component" />
                  <el-option label="全局参数" value="global" />
                  <el-option label="写入 input.data 表格" value="input_table" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="参数路径（多个用逗号分隔）">
              <template slot-scope="{ row }">
                <el-input v-if="row.kind !== 'input_table'" v-model="row.params" size="mini" placeholder="如 speed@pmover01" />
                <span v-else class="muted">写入 {{ row.points || 150 }} 个点的常值表格</span>
              </template>
            </el-table-column>
            <el-table-column width="50">
              <template slot-scope="{ $index }">
                <el-button type="text" icon="el-icon-delete" @click="form.amesim.parameters.splice($index, 1)" />
              </template>
            </el-table-column>
          </el-table>
          <el-button size="mini" icon="el-icon-plus" class="add" @click="form.amesim.parameters.push({ input: '', kind: 'component', params: '' })">添加参数映射</el-button>
          <el-divider content-position="left">输出对应的模型变量</el-divider>
          <el-form-item v-for="o in form.outputs" :key="o.name" :label="o.name || '（未命名输出）'">
            <el-input v-model.trim="form.amesim.variables[o.name]" placeholder="如 qout@pump01" style="width: 360px" />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <span slot="footer">
      <span v-if="!isNew" class="muted footer-note">修改了输入或输出后，原基准表作废，需要重建后才参与诊断</span>
      <el-button @click="$emit('close')">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </span>
  </el-dialog>
</template>

<script>
import { COMPONENTS } from '@/views/dashboard/scene/components'
import { getDataDirs } from '@/api/files'
import {
  KIND_LABELS, MEANING_LABELS, ROLE_LABELS, createModel, getColumns, previewModel, updateModel
} from '@/api/simulation'
import { errorMessage } from '@/utils/request'
import FitResult from './FitResult'

// 后端未返回构建器列表时的默认（与 pump_test_bench/app/simulation/builders 一致）
const DEFAULT_BUILDERS = [
  {
    kind: 'autofit', label: '自动拟合', available: true, description: '按变量角色确定公式结构，用正常数据拟合',
    options: [
      { key: 'max_degree', label: '主变量最高次数', type: 'number', default: 3, min: 1, max: 4 },
      { key: 'interactions', label: '交叉项', type: 'select', default: true, choices: [{ value: true, label: '使用' }, { value: false, label: '不使用' }] },
      { key: 'ridge', label: '正则强度', type: 'number', default: 0.0001, min: 0, max: 1 }
    ]
  },
]
let keySeq = 0

// 标准台的系统划分（与 pump_test_bench/config/signals.json 一致），可在“所属系统”中另填
const SYSTEMS = ['油箱系统', '离心泵驱动电机', '供油系统', '传动系统', '被试件', '回油系统（大流量管路）', '回油系统（小流量管路）']
const DEFAULT_ABS_FLOORS = { flow: [5, 10], pressure: [0.02, 0.04], temperature: [3, 5], torque: [1, 2], speed: [20, 40], other: [1, 2] }

const DEFAULT_FLOORS = {
  flow: [2.5, 4], pressure: [4, 7], temperature: [3, 5], torque: [15, 25], speed: [2, 4], other: [5, 8]
}

function toText(list) {
  return (list || []).join(', ')
}

function inputSource(i) {
  if (i.derived === 'density' || i.derived === 'viscosity') return i.derived
  if (i.constant !== undefined && i.constant !== null && !i.column && !(i.columns && i.columns.length)) return 'constant'
  return i.columns && i.columns.length ? 'multi' : 'single'
}

/** 各构建器的选项：已保存的值优先，其余用默认值 */
function builderOptions(o, builders) {
  const out = {}
  for (const b of builders) {
    const saved = o[b.kind] || {}
    out[b.kind] = Object.fromEntries((b.options || []).map(opt => [opt.key, saved[opt.key] !== undefined ? saved[opt.key] : opt.default]))
  }
  return out
}


/** 模型配置 → 表单 */
function toForm(cfg, builders = DEFAULT_BUILDERS) {
  const rule = (cfg.rules || {}).group_shift
  const th = cfg.thresholds || {}
  const floors = {}
  for (const kind of Object.keys(DEFAULT_FLOORS)) {
    const pct = kind === 'temperature' ? 1 : 100
    const w = (th.floor_warn || {})[kind]
    const a = (th.floor_alarm || {})[kind]
    floors[kind] = {
      warn: w === undefined ? DEFAULT_FLOORS[kind][0] : +(w * pct).toFixed(2),
      alarm: a === undefined ? DEFAULT_FLOORS[kind][1] : +(a * pct).toFixed(2)
    }
  }
  const floorsAbs = {}
  for (const kind of Object.keys(DEFAULT_ABS_FLOORS)) {
    const w = (th.floor_warn_abs || {})[kind]
    const a = (th.floor_alarm_abs || {})[kind]
    floorsAbs[kind] = { warn: w === undefined ? DEFAULT_ABS_FLOORS[kind][0] : w, alarm: a === undefined ? DEFAULT_ABS_FLOORS[kind][1] : a }
  }
  const ame = cfg.amesim || {}
  return {
    id: cfg.id || '',
    name: cfg.name || '',
    description: cfg.description || '',
    engine: (cfg.engine && cfg.engine.type) || 'surrogate',
    components: [...(cfg.components || [])],
    default_mode: cfg.default_mode || 'decisive',
    active_if: (cfg.active_if || []).map(c => ({ column: c.column || '', min: c.min === undefined ? '' : c.min, max: c.max === undefined ? '' : c.max, note: c.note || '' })),
    inputs: (cfg.inputs || []).map(i => ({
      name: i.name,
      source: inputSource(i),
      constant: i.constant === undefined || i.constant === null ? '' : String(i.constant),
      scale: i.scale === undefined ? '' : String(i.scale),
      offset: i.offset === undefined ? '' : String(i.offset),
      role: i.role || 'auto',
      column: i.column || '',
      columns: [...(i.columns || [])],
      temperature_column: i.temperature_column || '',
      fallback: (i.fallback_columns || [])[0] || '',
      unit: i.unit || '',
      grid: toText(i.grid),
      valid: toText(i.valid)
    })),
    outputs: (cfg.outputs || []).map(o => ({
      name: o.name,
      kind: o.kind || 'other',
      unit: o.unit || '',
      columns: [...(o.columns || [])],
      system: o.system || '',
      residual: o.residual || (o.kind === 'temperature' ? 'absolute' : 'relative'),
      single: o.single || 'decisive',
      component: o.component || '',
      flow_dependent: !!o.flow_dependent,
      component_by_column: o.component_by_column,
      method: o.method || 'autofit',
      options: builderOptions(o, builders),
      _key: `o${++keySeq}`
    })),
    groupEnabled: !!rule,
    group: {
      outputs: rule ? (rule.outputs || [rule.output]) : [],
      meaning: (rule && rule.meaning) || 'pump',
      input: (rule && rule.input) || '',
      driver: (rule && rule.driver) || '',
      min_columns: (rule && rule.min_columns) || 3,
      component: (rule && rule.component) || ''
    },
    sigma_warn: th.sigma_warn || 3,
    sigma_alarm: th.sigma_alarm || 5,
    floors,
    floorsAbs,
    amesim: {
      model_file: ame.model_file && !String(ame.model_file).includes('待填写') ? ame.model_file : '',
      url: ame.url || 'http://127.0.0.1:5003',
      stop_time_s: ame.stop_time_s || 20,
      steady_tail_s: ame.steady_tail_s || 5,
      parameters: (ame.parameters || []).map(p => ({ ...p, params: Array.isArray(p.params) ? p.params.join(', ') : (p.params || '') })),
      variables: Object.fromEntries(Object.entries(ame.variables || {}).map(([k, v]) => [k, String(v).includes('待填写') ? '' : v]))
    }
  }
}

export default {
  name: 'ModelEditor',
  components: { FitResult },
  props: {
    visible: { type: Boolean, default: false },
    // 编辑时为模型配置（status.models[i].config），新建时为 null
    model: { type: Object, default: null },
    // 数据代理模型的构建器（status.builders）
    builders: { type: Array, default: () => DEFAULT_BUILDERS }
  },
  data() {
    return {
      tab: 'basic',
      form: toForm({}),
      columns: [],
      saving: false,
      components: COMPONENTS,
      SYSTEMS,
      ROLE_LABELS,
      previewPath: '',
      previewing: '',
      previews: {},
      expanded: [],
      KIND_LABELS,
      MEANING_LABELS
    }
  },
  computed: {
    isNew() {
      return !this.model
    },
    isSurrogate() {
      return this.form.engine === 'surrogate'
    },
    usesRoles() {
      return this.form.outputs.some(o => o.method === 'autofit')
    },
    usedKinds() {
      return [...new Set(this.form.outputs.map(o => o.kind))]
    },
    // 有“绝对”残差输出的类型（温度本来就是绝对偏差，用上面的下限）
    absKinds() {
      return [...new Set(this.form.outputs.filter(o => o.residual === 'absolute' && o.kind !== 'temperature').map(o => o.kind))]
    }
  },
  watch: {
    visible: {
      handler(v) {
        if (!v) return
        this.tab = 'basic'
        this.previews = {}
        this.expanded = []
        this.form = toForm(this.model || {
          inputs: [this.blankInputCfg()],
          outputs: [{ name: '', kind: 'flow', unit: 'L/h', columns: [] }]
        }, this.builders)
        if (!this.columns.length) getColumns().then(r => { this.columns = r.columns }).catch(() => {})
      },
      immediate: true
    }
  },
  methods: {
    blankInputCfg() {
      return { name: '', column: '', unit: '', grid: [] }
    },
    blankInput() {
      return {
        name: '', source: 'single', column: '', columns: [], temperature_column: '', fallback: '', unit: '', grid: '', valid: '',
        constant: '', scale: '', offset: '', role: 'auto'
      }
    },
    blankOutput() {
      return {
        name: '', kind: 'pressure', unit: 'MPa', columns: [], system: '', residual: 'relative', single: 'decisive', component: '',
        flow_dependent: false, method: 'autofit',
        options: builderOptions({}, this.builders), _key: `o${++keySeq}`
      }
    },
    addOutput() {
      const o = this.blankOutput()
      this.form.outputs.push(o)
      if (this.isSurrogate) this.expanded = [...this.expanded, o._key]
    },
    builderOf(kind) {
      return this.builders.find(b => b.kind === kind)
    },
    onMethod(row) {
      if (!row.options[row.method] && this.builderOf(row.method)) {
        this.$set(row.options, row.method, builderOptions({}, [this.builderOf(row.method)])[row.method] || {})
      }
      this.$delete(this.previews, row.name)
      if (!this.expanded.includes(row._key)) this.expanded = [...this.expanded, row._key]
    },
    onExpand(row, rows) {
      this.expanded = rows.map(r => r._key)
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
    /** 验证 / 试拟合：row 为空时验证全部输出。不保存。 */
    async runPreview(row) {
      this.previewing = row ? row.name : '*'
      try {
        const cfg = this.toConfig()
        if (!cfg.id) cfg.id = 'preview'
        const r = await previewModel(cfg, this.previewPath.trim(), row ? [row.name] : undefined)
        for (const [name, result] of Object.entries(r.outputs)) this.$set(this.previews, name, result)
        if (!row) this.expanded = this.form.outputs.map(o => o._key)
        const note = Object.entries(r.roles || {}).map(([n, role]) => `${n}·${ROLE_LABELS[role] || role}`).join('，')
        this.$message.success(`已用 ${r.files} 个正常数据文件验证` + (note && this.usesRoles ? `；变量角色：${note}` : ''))
      } catch (e) {
        this.$message.error(errorMessage(e))
      } finally {
        this.previewing = ''
      }
    },
    /** 表单 → 模型配置（保留表单不管的字段，如 media、order、ordiam 档位表） */
    toConfig() {
      const f = this.form
      const base = this.model ? JSON.parse(JSON.stringify(this.model)) : {}
      const cfg = {
        ...base,
        id: f.id,
        name: f.name,
        description: f.description,
        engine: { ...(base.engine || {}), type: f.engine },
        components: f.components,
        default_mode: f.default_mode,
        active_if: f.active_if.filter(c => c.column).map(c => {
          const out = { column: c.column }
          if (c.min !== '' && c.min !== null) out.min = Number(c.min)
          if (c.max !== '' && c.max !== null) out.max = Number(c.max)
          if (c.note) out.note = c.note
          return out
        }),
        inputs: f.inputs.map((i, k) => {
          const old = (base.inputs || [])[k] || {}
          const out = { ...old, name: i.name, unit: i.unit, grid: i.grid, valid: i.valid }
          for (const key of ['column', 'columns', 'derived', 'temperature_column', 'aggregate', 'constant', 'scale', 'offset', 'role']) {
            delete out[key]
          }
          if (i.source === 'multi') out.columns = i.columns
          else if (i.source === 'density' || i.source === 'viscosity') {
            out.derived = i.source
            out.temperature_column = i.temperature_column
          } else if (i.source === 'constant') {
            out.constant = i.constant
          } else out.column = i.column
          if (i.source !== 'constant') {
            if (String(i.scale).trim() !== '') out.scale = i.scale
            if (String(i.offset).trim() !== '') out.offset = i.offset
          }
          if (f.engine === 'surrogate') out.role = i.role || 'auto'
          out.fallback_columns = i.source !== 'multi' && i.source !== 'constant' && i.fallback ? [i.fallback] : []
          return out
        }),
        outputs: f.outputs.map(o => {
          const out = { name: o.name, kind: o.kind, unit: o.unit, columns: o.columns, single: o.single, residual: o.residual }
          if (o.system) out.system = o.system
          if (o.component) out.component = o.component
          if (o.flow_dependent && o.kind === 'pressure') out.flow_dependent = true
          if (o.component_by_column) out.component_by_column = o.component_by_column
          if (f.engine === 'surrogate') {
            // 内置模型的输出（后端配置的计算方式）原样提交方式名，内容由后端按输出名称补回
            out.method = o.method
            for (const [kind, opts] of Object.entries(o.options || {})) out[kind] = { ...opts }
          }
          return out
        }),
        rules: f.groupEnabled ? {
          group_shift: {
            outputs: f.group.outputs,
            meaning: f.group.meaning,
            min_columns: f.group.min_columns,
            ...(f.group.meaning === 'input' ? { input: f.group.input } : {}),
            ...(f.group.meaning === 'pump' && f.group.driver ? { driver: f.group.driver } : {}),
            ...(f.group.component ? { component: f.group.component } : {})
          }
        } : {},
        thresholds: {
          ...(base.thresholds || {}),
          sigma_warn: f.sigma_warn,
          sigma_alarm: f.sigma_alarm,
          floor_warn: Object.fromEntries(this.usedKinds.map(k => [k, f.floors[k].warn / (k === 'temperature' ? 1 : 100)])),
          floor_alarm: Object.fromEntries(this.usedKinds.map(k => [k, f.floors[k].alarm / (k === 'temperature' ? 1 : 100)])),
          floor_warn_abs: Object.fromEntries(this.absKinds.map(k => [k, f.floorsAbs[k].warn])),
          floor_alarm_abs: Object.fromEntries(this.absKinds.map(k => [k, f.floorsAbs[k].alarm]))
        },
        amesim: {
          ...(base.amesim || {}),
          model_file: f.amesim.model_file,
          url: f.amesim.url,
          stop_time_s: f.amesim.stop_time_s,
          steady_tail_s: f.amesim.steady_tail_s,
          parameters: f.amesim.parameters.map(p => {
            const out = { ...p }
            if (!out.derive) delete out.derive
            return out
          }),
          variables: Object.fromEntries(f.outputs.map(o => [o.name, f.amesim.variables[o.name] || '']))
        }
      }
      if (f.engine !== 'amesim' && !cfg.amesim.model_file) cfg.amesim.model_file = '待填写.ame'
      return cfg
    },
    async save() {
      this.saving = true
      try {
        const cfg = this.toConfig()
        const result = this.isNew ? await createModel(cfg) : await updateModel(this.model.id, cfg)
        this.$message.success(this.isNew ? `已新建“${result.name}”，请为它建立基准表` : `已保存“${result.name}”`)
        this.$emit('saved', result)
      } catch (e) {
        this.$message.error(errorMessage(e))
      } finally {
        this.saving = false
      }
    }
  }
}
</script>

<style scoped>
.tab-hint {
  font-size: 12px;
  margin-bottom: 8px;
}
.conv {
  display: flex;
  align-items: center;
  gap: 3px;
}
.conv .el-input {
  width: 74px;
}
.preview-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.builtin-note {
  font-size: 12px;
  color: #6b7a90;
  padding: 4px 0;
}
.method-panel {
  padding: 6px 12px 10px 24px;
}
.panel-actions {
  margin: 8px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.options .el-form-item {
  margin-bottom: 4px;
}
.small {
  font-size: 12px;
}
.editor >>> .el-tabs__content {
  max-height: 70vh;
  overflow-y: auto;
}
.add {
  margin-top: 8px;
}
.tip {
  margin-left: 6px;
  color: #909399;
  cursor: help;
}
.unit {
  margin-left: 8px;
  color: #909399;
}
.muted {
  color: #909399;
}
.footer-note {
  font-size: 12px;
  margin-right: 12px;
}
</style>
