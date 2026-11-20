<template>
  <div :class="['model-compare', { dark }]">
    <div v-if="!list.length" class="meta">没有可用的仿真模型基准表，未做模型对比</div>
    <div v-for="m in list" :key="m.id || m.name" class="model">
      <div class="head">
        <b>{{ m.name }}</b>
        <span v-if="m.mode" :class="['mode', m.mode]">{{ MODE_LABELS[m.mode] || m.mode }}</span>
        <span class="meta">{{ m.model }}</span>
      </div>
      <template v-if="m.available">
        <div class="meta">
          工况：{{ conditionText(m) }}
          <span v-if="m.outside && m.outside.length" class="warn">（超出基准表范围：{{ m.outside.join('、') }}）</span>
        </div>
        <div v-if="m.group" :class="['group', m.group.severity]">{{ groupText(m) }}</div>
        <table class="rows">
          <thead>
            <tr><th>测点</th><th>实测</th><th>模型预期</th><th>偏差</th><th>预警范围</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in m.rows" :key="r.column" :class="r.severity">
              <td>{{ r.column }}<span v-if="r.excluded" class="tag">互校异常</span></td>
              <td>{{ fmt(r.measured, r.unit) }}</td>
              <td>{{ fmt(r.expected, r.unit) }}</td>
              <td class="num">{{ residual(r) }}</td>
              <td class="num">{{ limit(r) }}</td>
            </tr>
          </tbody>
        </table>
      </template>
      <div v-else class="meta">未做对比：{{ (m.notes || []).join('；') || '工况不完整' }}</div>
    </div>
  </div>
</template>

<script>
import { MODE_LABELS } from '@/api/simulation'

const MEANING = {
  pump: '流量计彼此一致，整体',
  reference: '各流量计相对模型一致',
  input: '各测点相对模型一致'
}

/** 报告中的仿真模型对比（report.models）：每个模型各测点的实测 vs 模型预期。 */
export default {
  name: 'ModelCompare',
  props: {
    models: { type: Array, default: () => [] },
    dark: { type: Boolean, default: false }
  },
  data() {
    return { MODE_LABELS }
  },
  computed: {
    list() {
      return this.models || []
    }
  },
  methods: {
    num(v) {
      return Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(1) : v.toFixed(3)
    },
    conditionText(m) {
      return Object.entries(m.condition || {}).map(([k, v]) => `${k} ${this.num(v)}`).join('、')
    },
    fmt(v, unit) {
      if (v === null || v === undefined) return '—'
      return `${unit === 'MPa' ? v.toFixed(3) : v.toFixed(1)} ${unit}`
    },
    residual(r) {
      const sign = r.residual > 0 ? '+' : ''
      return r.mode === 'absolute' ? `${sign}${r.residual.toFixed(1)} ${r.unit}` : `${sign}${(r.residual * 100).toFixed(2)}%`
    },
    limit(r) {
      return r.mode === 'absolute' ? `±${r.warn.toFixed(1)} ${r.unit}` : `±${(r.warn * 100).toFixed(1)}%`
    },
    groupText(m) {
      const g = m.group
      const v = g.mode === 'absolute' ? `${Math.abs(g.residual).toFixed(1)} ℃` : `${Math.abs(g.residual * 100).toFixed(2)}%`
      let text = `${MEANING[g.meaning] || ''}偏${g.residual < 0 ? '低' : '高'} ${v}`
      if (g.meaning === 'pump' && g.pressures_checked) {
        text += `，与流量相关的压力${g.pressures_follow ? '同步变化（实际流量变了）' : '未随之变化（更像测量偏差）'}`
      } else if (g.meaning === 'reference') {
        text += '：参考量（质量流量计或燃油密度）偏差'
      } else if (g.meaning === 'input') {
        text += '：模型输入测点偏差'
      }
      return text
    }
  }
}
</script>

<style scoped>
.model-compare {
  font-size: 13px;
}
.model + .model {
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px dashed #dcdfe6;
}
.head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.mode {
  font-size: 11px;
  padding: 0 6px;
  border-radius: 3px;
  line-height: 18px;
  background: #f0f9eb;
  color: #67c23a;
}
.mode.reference {
  background: #fdf6ec;
  color: #e6a23c;
}
.meta {
  color: #909399;
  font-size: 12px;
  margin-bottom: 6px;
}
.meta .warn {
  color: #e6a23c;
}
.group {
  padding: 6px 10px;
  margin-bottom: 8px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 0;
}
.group.abnormal {
  border-left-color: #f56c6c;
  background: #fef0f0;
}
.rows {
  width: 100%;
  border-collapse: collapse;
}
.rows th,
.rows td {
  padding: 4px 8px;
  border-bottom: 1px solid #ebeef5;
  text-align: left;
}
.rows th {
  color: #909399;
  font-weight: normal;
  font-size: 12px;
}
.rows .num {
  font-variant-numeric: tabular-nums;
}
.rows tr.warning td {
  color: #e6a23c;
}
.rows tr.abnormal td {
  color: #f56c6c;
}
.tag {
  margin-left: 4px;
  font-size: 11px;
  color: #909399;
}
.dark .rows th,
.dark .rows td {
  border-bottom-color: rgba(56, 189, 248, 0.12);
  color: #c7d2e0;
}
.dark .rows th,
.dark .meta {
  color: #7891ad;
}
.dark .model + .model {
  border-top-color: rgba(56, 189, 248, 0.16);
}
.dark .group {
  background: rgba(230, 162, 60, 0.08);
  color: #cfe3ff;
}
.dark .group.abnormal {
  background: rgba(245, 108, 108, 0.1);
}
.dark .mode {
  background: rgba(103, 194, 58, 0.15);
}
.dark .mode.reference {
  background: rgba(230, 162, 60, 0.15);
}
</style>
