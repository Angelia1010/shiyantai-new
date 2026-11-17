<template>
  <div class="schematic">
    <svg viewBox="0 0 1000 215" class="schematic-svg" role="img" aria-label="诊断信号管路示意图">
      <defs>
        <marker id="flow-arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0 L10 5 L0 10 Z" fill="#a8abb2" />
        </marker>
      </defs>

      <!-- 油箱 → 增压泵的循环回路 -->
      <path d="M940 130 V198 H60 V130" class="loop-line" />
      <text x="500" y="211" class="loop-text" text-anchor="middle">油箱 → 增压泵（循环）</text>

      <!-- 主油路：供油段 / 回油段 -->
      <line x1="100" y1="110" x2="450" y2="110" :class="['pipe', pipeClass('供油管路')]" />
      <line x1="570" y1="110" x2="900" y2="110" :class="['pipe', pipeClass('回油管路')]" />
      <line x1="118" y1="110" x2="128" y2="110" class="arrow" marker-end="url(#flow-arrow)" />
      <line x1="418" y1="110" x2="428" y2="110" class="arrow" marker-end="url(#flow-arrow)" />
      <line x1="590" y1="110" x2="600" y2="110" class="arrow" marker-end="url(#flow-arrow)" />
      <line x1="878" y1="110" x2="888" y2="110" class="arrow" marker-end="url(#flow-arrow)" />
      <text x="275" y="86" class="segment-text" text-anchor="middle">供油段</text>
      <text x="745" y="86" class="segment-text" text-anchor="middle">回油段</text>

      <!-- 设备 -->
      <g class="device">
        <rect x="20" y="90" width="80" height="40" rx="4" />
        <text x="60" y="115" text-anchor="middle">增压泵</text>
      </g>
      <g :class="['device', deviceClass('被试件1高低压双联泵')]">
        <rect x="450" y="82" width="120" height="56" rx="4" />
        <text x="510" y="115" text-anchor="middle">被试泵</text>
      </g>
      <g class="device">
        <rect x="900" y="90" width="80" height="40" rx="4" />
        <text x="940" y="115" text-anchor="middle">油箱</text>
      </g>
      <line x1="510" y1="82" x2="510" y2="46" :class="['drive', deviceClass('电传系统')]" />

      <!-- 测点 -->
      <g
        v-for="n in nodes"
        :key="n.key"
        :class="['node', n.state, { selected: n.column === selected }]"
        tabindex="0"
        role="button"
        :aria-label="`${n.name}：${n.stateText}`"
        @click="$emit('select', n.column)"
        @keydown.enter="$emit('select', n.column)"
      >
        <title>{{ n.title }}</title>
        <circle :cx="n.x" :cy="n.y" r="15" class="hit" />
        <circle :cx="n.x" :cy="n.y" r="9" class="dot" :style="{ fill: n.color }" />
        <circle v-if="n.column === selected" :cx="n.x" :cy="n.y" r="14" class="ring" />
        <template v-if="n.key === 'speed'">
          <text :x="n.x + 22" :y="n.y - 3" class="name">{{ n.name }}</text>
          <text :x="n.x + 22" :y="n.y + 13" class="value">{{ n.value }}</text>
        </template>
        <template v-else>
          <text :x="n.x" :y="n.y + 34" class="name" text-anchor="middle">{{ n.name }}</text>
          <text :x="n.x" :y="n.y + 50" class="value" text-anchor="middle">{{ n.value }}</text>
          <text v-if="n.deviation" :x="n.x" :y="n.y + 65" class="deviation" text-anchor="middle" :style="{ fill: n.state === 'normal' ? null : n.color }">
            {{ n.deviation }}
          </text>
        </template>
      </g>
    </svg>

    <div class="legend">
      <span v-for="s in legend" :key="s" class="legend-item">
        <i :style="{ background: STATE_COLOR[s] }"></i>{{ STATE_TEXT[s] }}
      </span>
      <span class="legend-hint">点击测点查看对应曲线</span>
    </div>
  </div>
</template>

<script>
import { SHORT_NAMES, STATE_COLOR, STATE_TEXT, deviationText, fmt, signalState } from '@/utils/diagnosisCurves'

const POSITIONS = {
  control_pressure: [150, 110],
  supply_temperature: [225, 110],
  supply_flow: [300, 110],
  inlet_pressure: [385, 110],
  speed: [510, 34],
  outlet_pressure: [630, 110],
  return_temperature: [705, 110],
  return_flow: [780, 110],
  back_pressure: [860, 110]
}

export default {
  name: 'PipelineSchematic',
  props: {
    curves: { type: Object, required: true },
    causes: { type: Array, default: () => [] },
    selected: { type: String, default: null }
  },
  data() {
    return { STATE_COLOR, STATE_TEXT }
  },
  computed: {
    nodes() {
      return (this.curves.signals || []).filter(s => POSITIONS[s.key]).map(s => {
        const state = signalState(s)
        const [x, y] = POSITIONS[s.key]
        const value = s.mean == null ? '—' : `${fmt(s.mean, s)} ${s.unit}`
        const deviation = s.residual != null ? deviationText(s) : ''
        return {
          key: s.key, column: s.column, x, y, state, color: STATE_COLOR[state],
          name: SHORT_NAMES[s.key] || s.label, value, deviation, stateText: STATE_TEXT[state],
          title: `${s.label}（${s.position || ''}）\n${STATE_TEXT[state]}${deviation ? '，相对正常预期 ' + deviation : ''}` +
            (s.findings && s.findings.length ? '\n' + s.findings.join('；') : '')
        }
      })
    },
    /** 原因分析中涉及的部件 → 等级 */
    componentSeverity() {
      const out = {}
      this.causes.forEach(c => {
        if (!c.component) return
        if (out[c.component] !== 'abnormal') out[c.component] = c.severity
      })
      return out
    },
    legend() {
      const used = new Set(this.nodes.map(n => n.state))
      return ['normal', 'affected', 'warning', 'abnormal', 'unusable'].filter(s => s === 'normal' || used.has(s))
    }
  },
  methods: {
    deviceClass(component) {
      const sev = this.componentSeverity[component]
      return sev === 'abnormal' || sev === 'warning' ? `is-${sev}` : ''
    },
    pipeClass(component) {
      return this.deviceClass(component)
    }
  }
}
</script>

<style scoped>
.schematic-svg {
  width: 100%;
  max-height: 240px;
  display: block;
}
.pipe {
  stroke: #c0c4cc;
  stroke-width: 6;
  stroke-linecap: round;
}
.pipe.is-warning { stroke: #f3d19e; }
.pipe.is-abnormal { stroke: #fab6b6; }
.arrow { stroke: transparent; }
.loop-line {
  fill: none;
  stroke: #dcdfe6;
  stroke-width: 2;
  stroke-dasharray: 6 5;
}
.loop-text, .segment-text {
  font-size: 12px;
  fill: #909399;
}
.device rect {
  fill: #f4f4f5;
  stroke: #909399;
  stroke-width: 1;
}
.device text {
  font-size: 14px;
  fill: #303133;
}
.device.is-warning rect { fill: #fdf6ec; stroke: #e6a23c; stroke-width: 2; }
.device.is-abnormal rect { fill: #fef0f0; stroke: #f56c6c; stroke-width: 2; }
.drive {
  stroke: #909399;
  stroke-width: 2;
  stroke-dasharray: 4 3;
}
.drive.is-warning { stroke: #e6a23c; }
.drive.is-abnormal { stroke: #f56c6c; }
.node { cursor: pointer; outline: none; }
.node .hit { fill: transparent; }
.node .dot { stroke: #fff; stroke-width: 2; }
.node .ring { fill: none; stroke: #409eff; stroke-width: 2; }
.node:focus-visible .hit { stroke: #409eff; stroke-width: 2; }
.node.affected .dot { stroke: #d4880f; stroke-dasharray: 3 2; }
.node .name { font-size: 13px; fill: #303133; }
.node .value { font-size: 12px; fill: #606266; }
.node .deviation { font-size: 12px; fill: #909399; }
.node.abnormal .name, .node.warning .name { font-weight: 600; }
.node:hover .name { fill: #409eff; }
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12px;
  color: #606266;
  padding: 4px 4px 0;
}
.legend-item i {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  margin-right: 5px;
  vertical-align: 0;
}
.legend-hint {
  margin-left: auto;
  color: #909399;
}
</style>
