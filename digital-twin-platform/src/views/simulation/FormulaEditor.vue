<template>
  <div class="formula-editor">
    <div class="toolbar">
      <span class="muted">变量：</span>
      <el-tag v-for="v in variables" :key="v.name" size="mini" class="chip" effect="plain" @click="insert(v.name)">
        {{ v.name }}<span v-if="v.unit" class="muted">（{{ v.unit }}）</span>
      </el-tag>
      <span class="muted sep">函数：</span>
      <el-tooltip v-for="(help, fn) in FUNCTION_HELP" :key="fn" :content="help" placement="top">
        <el-tag size="mini" type="info" class="chip" @click="insert(`${fn}(`)">{{ fn }}</el-tag>
      </el-tooltip>
    </div>
    <el-input ref="input" v-model="formula.expression" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
              class="expr" placeholder="如：a + b * 质量流量 + c * 密度；乘方用 ^，条件用 if(条件, 甲, 乙)" @input="sync" />
    <div v-if="formula.expression" class="preview">
      <equation-view :expression="previewText" :variables="variables.map(v => v.name)" size="small" />
    </div>
    <div class="hint muted">不是变量、也不是函数的名字都是系数，在下表中给值；勾选“由数据拟合”的系数在验证或建立模型时用正常数据求出，填的值作为初值。</div>
    <el-table v-if="names.length" :data="rows" size="mini" border class="coefs">
      <el-table-column label="系数" width="110">
        <template slot-scope="{ row }"><code>{{ row.name }}</code></template>
      </el-table-column>
      <el-table-column label="值（初值）" width="180">
        <template slot-scope="{ row }">
          <el-input v-model="formula.coefficients[row.name].value" size="mini" placeholder="数值" />
        </template>
      </el-table-column>
      <el-table-column label="方式" width="150">
        <template slot-scope="{ row }">
          <el-radio-group v-model="formula.coefficients[row.name].fit" size="mini">
            <el-radio-button :label="false">固定</el-radio-button>
            <el-radio-button :label="true">由数据拟合</el-radio-button>
          </el-radio-group>
        </template>
      </el-table-column>
      <el-table-column label="上次拟合结果">
        <template slot-scope="{ row }">
          <span v-if="fitted && fitted[row.name] !== undefined && formula.coefficients[row.name].fit">{{ fmt(fitted[row.name]) }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
import { FUNCTION_HELP, coefficientNames } from '@/api/simulation'
import EquationView from './EquationView'

export default {
  name: 'FormulaEditor',
  components: { EquationView },
  props: {
    // { expression, coefficients: { 名: { value, fit } } }，直接修改
    formula: { type: Object, required: true },
    // [{ name, unit }]
    variables: { type: Array, default: () => [] },
    // 上次验证得到的系数 { 名: 值 }
    fitted: { type: Object, default: null }
  },
  data() {
    return { FUNCTION_HELP }
  },
  computed: {
    names() {
      return coefficientNames(this.formula.expression, this.variables.map(v => v.name))
    },
    // 预览：去掉 “Y =” 前缀
    previewText() {
      return String(this.formula.expression || '').replace(/^[^=<>!()]*?(?<![<>=!])=(?!=)/, '')
    },
    rows() {
      return this.names.filter(n => this.formula.coefficients[n]).map(name => ({ name }))
    }
  },
  created() {
    if (!this.formula.coefficients) this.$set(this.formula, 'coefficients', {})
    this.sync()
  },
  methods: {
    fmt(v) {
      return Number(v).toPrecision(7).replace(/\.?0+(e|$)/, '$1')
    },
    /** 系数表跟随公式：新出现的名字加一行（默认固定，需要填值），不再出现的保留值但不显示 */
    sync() {
      for (const n of this.names) {
        if (!this.formula.coefficients[n]) this.$set(this.formula.coefficients, n, { value: '', fit: false })
      }
    },
    insert(text) {
      const el = this.$refs.input && this.$refs.input.$refs.textarea
      const expr = this.formula.expression || ''
      const pos = el ? el.selectionStart : expr.length
      const end = el ? el.selectionEnd : expr.length
      this.formula.expression = expr.slice(0, pos) + text + expr.slice(end)
      this.sync()
      this.$nextTick(() => {
        if (!el) return
        el.focus()
        el.selectionStart = el.selectionEnd = pos + text.length
      })
    }
  }
}
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}
.chip {
  cursor: pointer;
}
.sep {
  margin-left: 10px;
}
.expr >>> textarea {
  font-family: Menlo, Consolas, monospace;
}
.preview {
  margin-top: 6px;
  padding: 4px 12px;
  border-left: 3px solid #0b1626;
  background: #f7f9fb;
}
.hint {
  font-size: 12px;
  margin: 4px 0 6px;
}
.muted {
  color: #909399;
}
.coefs {
  max-width: 720px;
}
</style>
