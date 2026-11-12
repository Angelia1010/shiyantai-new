<template>
  <div :class="['model-compare', { dark }]">
    <template v-if="model && model.available">
      <div class="meta">
        {{ model.model }}　工况：{{ conditionText }}
        <span v-if="model.outside && model.outside.length" class="warn">（超出基准表范围：{{ model.outside.join('、') }}）</span>
      </div>
      <div v-if="model.system" :class="['system', model.system.severity]">
        系统流量比模型预期{{ model.system.residual < 0 ? '低' : '高' }}
        {{ Math.abs(model.system.residual * 100).toFixed(2) }}%（各流量计一致）
        <template v-if="model.system.pressures_checked">
          ，与流量相关的压力{{ model.system.pressures_follow ? '同步变化' : '未随之变化' }}
        </template>
      </div>
      <table class="rows">
        <thead>
          <tr><th>测点</th><th>实测</th><th>模型预期</th><th>偏差</th><th>预警范围</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in model.rows" :key="r.column" :class="r.severity">
            <td>{{ r.column }}<span v-if="r.excluded" class="tag">互校异常</span></td>
            <td>{{ fmt(r.measured, r.unit) }}</td>
            <td>{{ fmt(r.expected, r.unit) }}</td>
            <td class="num">{{ r.residual > 0 ? '+' : '' }}{{ (r.residual * 100).toFixed(2) }}%</td>
            <td class="num">±{{ (r.warn * 100).toFixed(1) }}%</td>
          </tr>
        </tbody>
      </table>
    </template>
    <div v-else-if="model" class="meta">
      未做模型对比：{{ (model.notes || []).join('；') || '工况不完整' }}
    </div>
    <div v-else class="meta">没有仿真基准表，未做模型对比</div>
  </div>
</template>

<script>
/** 报告中的仿真模型对比（report.model）：各测点实测 vs 模型预期。 */
export default {
  name: 'ModelCompare',
  props: {
    model: { type: Object, default: null },
    dark: { type: Boolean, default: false }
  },
  computed: {
    conditionText() {
      const c = (this.model && this.model.condition) || {}
      return Object.entries(c).map(([k, v]) => `${k} ${v >= 100 ? v.toFixed(0) : v >= 1 ? v.toFixed(1) : v.toFixed(3)}`).join('、')
    }
  },
  methods: {
    fmt(v, unit) {
      if (v === null || v === undefined) return '—'
      return `${unit === 'MPa' ? v.toFixed(3) : v.toFixed(1)} ${unit}`
    }
  }
}
</script>

<style scoped>
.model-compare {
  font-size: 13px;
}
.meta {
  color: #909399;
  font-size: 12px;
  margin-bottom: 6px;
}
.meta .warn {
  color: #e6a23c;
}
.system {
  padding: 6px 10px;
  margin-bottom: 8px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 0;
}
.system.abnormal {
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
.dark .rows th {
  color: #7891ad;
}
.dark .system {
  background: rgba(230, 162, 60, 0.08);
  color: #cfe3ff;
}
.dark .system.abnormal {
  background: rgba(245, 108, 108, 0.1);
}
</style>
