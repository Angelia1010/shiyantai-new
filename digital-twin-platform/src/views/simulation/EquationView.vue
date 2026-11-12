<template>
  <div :class="['equation', size]">
    <span v-if="lhs" class="lhs">{{ lhs }}</span>
    <span v-if="lhs" class="eq">=</span>
    <span class="rhs">
      <span v-for="(term, k) in terms" :key="k" class="term">
        <template v-for="(t, j) in term">
          <span v-if="t.type === 'num'" :key="j" class="num">{{ t.mant }}<template v-if="t.exp !== null"><span class="times">×</span>10<sup>{{ t.exp }}</sup></template></span>
          <span v-else-if="t.type === 'var'" :key="j" class="var">{{ t.text }}</span>
          <span v-else-if="t.type === 'coef'" :key="j" class="coef">{{ t.text }}</span>
          <span v-else-if="t.type === 'fn'" :key="j" class="fn">{{ t.text }}</span>
          <sup v-else-if="t.type === 'pow'" :key="j" class="pow">{{ t.text }}</sup>
          <span v-else-if="t.type === 'dot'" :key="j" class="dot">·</span>
          <span v-else-if="t.type === 'sign'" :key="j" class="sign">{{ t.text }}</span>
          <span v-else :key="j" class="op">{{ t.text }}</span>
        </template>
      </span>
    </span>
  </div>
</template>

<script>
/**
 * 把公式文本排成“方程”：变量、系数、数字分别着色，小数用 ×10ⁿ 表示，乘方上标，按顶层的 + − 分项换行。
 * 只做展示，不计算。
 */
const FUNCS = new Set(['exp', 'log', 'ln', 'log10', 'sqrt', 'abs', 'min', 'max', 'clip', 'if'])
const TOKEN = /\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)|([A-Za-z_一-鿿][A-Za-z0-9_一-鿿]*)|(\*\*|>=|<=|==|!=|[-+*/^(),<>]))/y

function formatNumber(text, digits) {
  const v = Number(text)
  if (!Number.isFinite(v)) return { mant: text, exp: null }
  const a = Math.abs(v)
  if (a !== 0 && (a < 1e-3 || a >= 1e6)) {
    const exp = Math.floor(Math.log10(a))
    return { mant: Number((v / 10 ** exp).toPrecision(digits || 4)).toString(), exp: String(exp).replace('-', '−') }
  }
  return { mant: Number(v.toPrecision(digits || 7)).toString(), exp: null }
}

export default {
  name: 'EquationView',
  props: {
    expression: { type: String, default: '' },
    lhs: { type: String, default: '' },
    variables: { type: Array, default: () => [] },
    size: { type: String, default: 'normal' }, // normal | small
    // 显示的有效数字（自动拟合的系数用 4 位；不给时按原值，最多 7 位）
    digits: { type: Number, default: 0 }
  },
  computed: {
    terms() {
      const vars = new Set(this.variables)
      const src = String(this.expression || '').replace(/−/g, '-')
      const toks = []
      TOKEN.lastIndex = 0
      let m
      while (TOKEN.lastIndex < src.length && (m = TOKEN.exec(src)) !== null) {
        if (m[1]) toks.push({ type: 'num', ...formatNumber(m[1], this.digits) })
        else if (m[2]) {
          const name = m[2]
          toks.push({ type: FUNCS.has(name) ? 'fn' : (vars.has(name) || /[一-鿿]/.test(name) ? 'var' : 'coef'), text: name })
        } else toks.push({ type: 'op', text: m[3] })
      }
      // 乘方：^ 后面的数字或名字改为上标；乘号改为居中点
      const out = []
      for (let i = 0; i < toks.length; i++) {
        const t = toks[i]
        if (t.type === 'op' && (t.text === '^' || t.text === '**') && toks[i + 1]) {
          const n = toks[++i]
          out.push({ type: 'pow', text: n.type === 'num' ? n.mant : n.text })
        } else if (t.type === 'op' && t.text === '*') out.push({ type: 'dot' })
        else out.push(t)
      }
      // 顶层的 + − 处分项（括号内不分），一项一组，换行发生在项之间
      const terms = [[]]
      let depth = 0
      out.forEach((t, i) => {
        if (t.type === 'op' && t.text === '(') depth++
        if (t.type === 'op' && t.text === ')') depth--
        const binary = i > 0 && !(out[i - 1].type === 'op' && out[i - 1].text !== ')')
        if (depth === 0 && t.type === 'op' && (t.text === '+' || t.text === '-') && binary) {
          terms.push([{ type: 'sign', text: t.text === '-' ? '−' : '+' }])
        } else if (t.type === 'op' && t.text === '-' && !binary) {
          terms[terms.length - 1].push({ type: 'op', text: '−' })
        } else terms[terms.length - 1].push(t)
      })
      return terms.filter(t => t.length)
    }
  }
}
</script>

<style scoped>
.equation {
  font-family: 'Cambria Math', 'STIX Two Math', 'Cambria', 'Times New Roman', 'Songti SC', serif;
  font-size: 17px;
  line-height: 1.9;
  color: #1e2b3c;
  display: flex;
  align-items: baseline;
  gap: 0 8px;
}
.equation.small {
  font-size: 14px;
  line-height: 1.75;
}
.lhs {
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-weight: 600;
  white-space: nowrap;
  color: #0b1626;
}
.eq {
  color: #6b7a90;
}
.rhs {
  display: flex;
  flex-wrap: wrap;
  gap: 0 6px;
  min-width: 0;
}
.term {
  white-space: nowrap;
}
.num {
  font-variant-numeric: tabular-nums lining-nums;
}
.times {
  margin: 0 1px;
  color: #6b7a90;
}
.var {
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 0.86em;
  color: #0b4f9c;
  font-weight: 500;
}
.coef {
  font-style: italic;
  color: #1e2b3c;
}
.fn {
  font-style: normal;
  color: #1e2b3c;
}
.pow {
  font-size: 0.68em;
  margin-left: 1px;
}
.dot {
  margin: 0 2px;
  color: #6b7a90;
}
.sign {
  margin-right: 6px;
  color: #1e2b3c;
}
.op {
  margin: 0 1px;
  color: #3b4a5e;
}
</style>
