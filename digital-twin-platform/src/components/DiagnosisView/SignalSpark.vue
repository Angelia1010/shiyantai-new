<template>
  <div
    :class="['spark', state, { selected }]"
    tabindex="0"
    role="button"
    :aria-label="`${signal.label}：${stateText}`"
    @click="$emit('select', signal.column)"
    @keydown.enter="$emit('select', signal.column)"
  >
    <div class="spark-head">
      <span class="spark-name">{{ signal.label }}</span>
      <span class="spark-state" :style="{ color: color }">{{ headline }}</span>
    </div>
    <svg :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none" class="spark-svg">
      <rect v-if="paths.segment" :x="paths.segment.x" y="0" :width="paths.segment.w" :height="H" class="seg" />
      <path v-if="paths.band" :d="paths.band" class="band" />
      <path v-if="paths.expected" :d="paths.expected" class="expected" vector-effect="non-scaling-stroke" />
      <path :d="paths.measured" class="measured" :style="{ stroke: lineColor }" vector-effect="non-scaling-stroke" />
    </svg>
    <div class="spark-foot">
      <span>实测 {{ fmt(signal.mean, signal) }}</span>
      <span v-if="signal.expected_mean != null">正常 {{ fmt(signal.expected_mean, signal) }}</span>
      <span v-else-if="signal.expected" class="muted">正常范围见曲线</span>
      <span v-else class="muted">工况输入</span>
      <span class="unit">{{ signal.unit }}</span>
    </div>
  </div>
</template>

<script>
import { STATE_COLOR, STATE_TEXT, deviationText, fmt, signalState, sparkPaths } from '@/utils/diagnosisCurves'

const W = 240
const H = 64

export default {
  name: 'SignalSpark',
  props: {
    signal: { type: Object, required: true },
    time: { type: Array, required: true },
    segment: { type: Array, default: null },
    selected: { type: Boolean, default: false }
  },
  data() {
    return { W, H }
  },
  computed: {
    state() {
      return signalState(this.signal)
    },
    stateText() {
      return STATE_TEXT[this.state]
    },
    color() {
      return STATE_COLOR[this.state]
    },
    lineColor() {
      return this.state === 'abnormal' || this.state === 'warning' ? this.color : '#409eff'
    },
    headline() {
      const d = this.signal.residual != null ? deviationText(this.signal) : ''
      if (this.state === 'normal') return d ? `正常 ${d}` : '正常'
      return d ? `${this.stateText} ${d}` : this.stateText
    },
    paths() {
      return sparkPaths(this.signal, this.time, this.segment, W, H)
    }
  },
  methods: { fmt }
}
</script>

<style scoped>
.spark {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px 10px 6px;
  cursor: pointer;
  background: #fff;
  transition: border-color 0.15s;
  outline: none;
  min-width: 0;
}
.spark:hover { border-color: #c6e2ff; }
.spark:focus-visible { box-shadow: 0 0 0 2px #a0cfff; }
.spark.warning { border-color: #f3d19e; }
.spark.abnormal { border-color: #fab6b6; background: #fffafa; }
.spark.selected { border-color: #409eff; box-shadow: 0 0 0 1px #409eff; }
.spark-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
}
.spark-name {
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.spark-state {
  font-size: 12px;
  white-space: nowrap;
}
.spark-svg {
  width: 100%;
  height: 64px;
  display: block;
  margin: 6px 0 4px;
}
.seg { fill: rgba(64, 158, 255, 0.06); }
.band { fill: rgba(144, 147, 153, 0.18); }
.expected {
  fill: none;
  stroke: #909399;
  stroke-width: 1;
  stroke-dasharray: 4 3;
}
.measured {
  fill: none;
  stroke-width: 1.5;
}
.spark-foot {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: #606266;
}
.spark-foot .unit { margin-left: auto; color: #909399; }
.muted { color: #c0c4cc; }
</style>
