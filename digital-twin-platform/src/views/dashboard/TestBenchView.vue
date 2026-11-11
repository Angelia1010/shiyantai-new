<template>
  <div class="test-bench-view">
    <div ref="canvasHost" class="canvas-host" />

    <!-- 工具栏：视角 / 着色 / 标签 -->
    <div class="toolbar">
      <div class="seg">
        <button
          v-for="(view, key) in views"
          :key="key"
          :class="['seg-btn', { active: activeView === key }]"
          @click="changeView(key)"
        >{{ view.label }}</button>
      </div>
      <div class="seg">
        <button
          v-for="(mode, key) in colorModes"
          :key="key"
          :class="['seg-btn', { active: colorMode === key }]"
          @click="changeColorMode(key)"
        >{{ mode.label }}</button>
      </div>
      <button :class="['seg-btn', 'single', { active: labelsVisible }]" @click="toggleLabels">标签</button>
    </div>

    <!-- 色标 -->
    <div v-if="legend" class="legend">
      <span class="legend-title">{{ colorModes[legend.mode].label }}（{{ legend.unit }}）</span>
      <span class="legend-value">{{ format(legend.min) }}</span>
      <span class="legend-bar" :style="{ background: gradient }" />
      <span class="legend-value">{{ format(legend.max) }}</span>
    </div>

    <!-- 悬停提示 -->
    <div v-if="hover" class="hover-tip" :style="{ left: hover.x + 14 + 'px', top: hover.y + 14 + 'px' }">
      {{ hover.label }}
    </div>

    <!-- 选中部件的测点 -->
    <transition name="fade">
      <div v-if="selected" class="info-card">
        <div class="info-head">
          <span>{{ selected.label }}</span>
          <i class="el-icon-close" @click="clearSelection" />
        </div>
        <div v-if="!selected.fields.length" class="info-empty">该部件没有关联测点</div>
        <div v-for="field in selected.fields" :key="field" class="info-row">
          <span class="info-name">{{ field }}</span>
          <span class="info-value">{{ fieldValue(field) }}</span>
        </div>
      </div>
    </transition>

    <!-- 加载状态 -->
    <div v-if="loading || error" class="overlay">
      <template v-if="error">
        <i class="el-icon-warning-outline" />
        <p>{{ error }}</p>
      </template>
      <template v-else>
        <div class="progress"><div class="progress-bar" :style="{ width: progress * 100 + '%' }" /></div>
        <p>正在加载试验台模型 {{ Math.round(progress * 100) }}%</p>
      </template>
    </div>
  </div>
</template>

<script>
import { COLOR_MODES, VIEWS } from './scene/components'
import { COLOR_STOPS, TestBenchScene } from './scene/TestBenchScene'
import { fieldUnit, formatValue } from '@/utils/features'

export default {
  name: 'TestBenchView',
  props: {
    // 最新一帧特征 { 测点: { avg, min, max } }
    featureMap: { type: Object, default: () => ({}) },
    // 需要告警闪烁的部件 key
    alarms: { type: Array, default: () => [] }
  },
  data() {
    return {
      views: VIEWS,
      colorModes: COLOR_MODES,
      activeView: 'overview',
      colorMode: 'none',
      labelsVisible: true,
      loading: true,
      progress: 0,
      error: '',
      legend: null,
      hover: null,
      components: {},
      selectedKey: null,
      gradient: `linear-gradient(90deg, ${COLOR_STOPS.join(', ')})`
    }
  },
  computed: {
    selected() {
      return this.selectedKey ? this.components[this.selectedKey] : null
    }
  },
  watch: {
    featureMap(map) {
      if (this.scene) this.scene.updateData(map)
    },
    alarms(keys) {
      if (this.scene) this.scene.setAlarms(keys)
    }
  },
  mounted() {
    // three.js 对象不放进 data，避免 Vue 递归做响应式
    this.scene = new TestBenchScene(this.$refs.canvasHost, {
      onProgress: p => { this.progress = p },
      onLoaded: list => {
        this.components = Object.fromEntries(list.map(c => [c.key, c]))
        this.loading = false
        this.scene.updateData(this.featureMap)
        this.scene.setAlarms(this.alarms)
      },
      onError: message => { this.error = message },
      onHover: info => { this.hover = info },
      onSelect: key => { this.selectedKey = key },
      onLegend: legend => { this.legend = legend }
    })
  },
  beforeDestroy() {
    if (this.scene) this.scene.dispose()
    this.scene = null
  },
  methods: {
    changeView(key) {
      this.activeView = key
      this.scene.setView(key)
    },
    changeColorMode(key) {
      this.colorMode = key
      this.scene.setColorMode(key)
    },
    toggleLabels() {
      this.labelsVisible = !this.labelsVisible
      this.scene.setLabelsVisible(this.labelsVisible)
    },
    clearSelection() {
      this.scene.select(null)
    },
    /** 供父组件调用：定位到某个部件（如诊断异常的流量计）。 */
    focus(key) {
      this.activeView = ''
      this.scene.focusComponent(key)
    },
    fieldValue(field) {
      const stat = this.featureMap[field]
      return stat ? `${formatValue(stat.avg)} ${fieldUnit(field)}` : '--'
    },
    format: formatValue
  }
}
</script>

<style lang="scss" scoped>
.test-bench-view {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 8px;
  background: radial-gradient(ellipse at 50% 35%, #1b2a40 0%, #111a29 55%, #0b111c 100%);
}
.canvas-host {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}
.toolbar {
  position: absolute;
  top: 12px;
  left: 12px;
  right: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  pointer-events: none;
  z-index: 2;
}
.seg {
  display: inline-flex;
  background: rgba(13, 20, 33, 0.72);
  border: 1px solid rgba(120, 150, 190, 0.18);
  border-radius: 6px;
  padding: 2px;
  pointer-events: auto;
  backdrop-filter: blur(6px);
}
.seg-btn {
  border: none;
  background: transparent;
  color: #9fb0c6;
  font-size: 12px;
  padding: 5px 10px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  &:hover {
    color: #e6edf6;
  }
  &.active {
    background: #2f6bff;
    color: #fff;
  }
  &.single {
    pointer-events: auto;
    background: rgba(13, 20, 33, 0.72);
    border: 1px solid rgba(120, 150, 190, 0.18);
    &.active {
      background: #2f6bff;
    }
  }
}
.legend {
  position: absolute;
  left: 12px;
  bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(13, 20, 33, 0.72);
  border: 1px solid rgba(120, 150, 190, 0.18);
  color: #c7d2e0;
  font-size: 12px;
  z-index: 2;
}
.legend-bar {
  width: 140px;
  height: 8px;
  border-radius: 4px;
}
.legend-value {
  font-variant-numeric: tabular-nums;
  color: #e6edf6;
}
.hover-tip {
  position: absolute;
  z-index: 3;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(8, 13, 22, 0.9);
  color: #e6edf6;
  font-size: 12px;
  pointer-events: none;
  white-space: nowrap;
}
.info-card {
  position: absolute;
  right: 12px;
  bottom: 12px;
  width: 260px;
  max-height: 60%;
  overflow-y: auto;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(13, 20, 33, 0.85);
  border: 1px solid rgba(47, 107, 255, 0.45);
  color: #c7d2e0;
  font-size: 12px;
  z-index: 2;
  backdrop-filter: blur(6px);
}
.info-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  margin-bottom: 8px;
  i {
    cursor: pointer;
    color: #9fb0c6;
  }
}
.info-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  border-top: 1px solid rgba(120, 150, 190, 0.12);
}
.info-value {
  color: #e6edf6;
  font-variant-numeric: tabular-nums;
}
.info-empty {
  color: #7d8ba0;
}
.overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #9fb0c6;
  font-size: 13px;
  background: rgba(11, 17, 28, 0.6);
  z-index: 4;
  i {
    font-size: 32px;
    color: #f59e0b;
  }
}
.progress {
  width: 240px;
  height: 4px;
  border-radius: 2px;
  background: rgba(120, 150, 190, 0.2);
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: #2f6bff;
  transition: width 0.2s;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}
.fade-enter,
.fade-leave-to {
  opacity: 0;
}
</style>

<style lang="scss">
/* 三维场景中的悬浮标签由 three.js 动态创建，不能用 scoped 样式 */
.test-bench-view .tb-label {
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(10, 16, 27, 0.78);
  border: 1px solid rgba(120, 150, 190, 0.3);
  color: #c7d2e0;
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
  &.is-alarm {
    border-color: #ef4444;
    box-shadow: 0 0 10px rgba(239, 68, 68, 0.6);
  }
}
.test-bench-view .tb-label__value {
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
