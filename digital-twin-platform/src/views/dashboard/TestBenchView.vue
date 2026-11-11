<template>
  <div :class="['test-bench-view', 'style-' + styleName]">
    <div ref="canvasHost" class="canvas-host" />

    <!-- 四角 HUD 装饰 -->
    <span class="hud hud-tl" /><span class="hud hud-tr" /><span class="hud hud-bl" /><span class="hud hud-br" />

    <!-- 工具栏：视角 / 着色 / 标签 / 外观 -->
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
      <div class="seg">
        <button :class="['seg-btn', { active: labelsVisible }]" @click="toggleLabels">标签</button>
      </div>
      <div class="seg seg-right">
        <button
          v-for="(style, key) in styles"
          :key="key"
          :class="['seg-btn', { active: styleName === key }]"
          @click="changeStyle(key)"
        >{{ style.label }}</button>
      </div>
    </div>

    <!-- 色标 -->
    <div v-if="legend" class="legend">
      <span class="legend-title">{{ colorModes[legend.mode].label }}（{{ legend.unit }}）</span>
      <span class="legend-value">{{ format(legend.min) }}</span>
      <span class="legend-bar" :style="{ background: gradient }" />
      <span class="legend-value">{{ format(legend.max) }}</span>
    </div>
    <div v-else-if="colorMode !== 'none' && !loading" class="legend muted">暂无{{ colorModes[colorMode].label }}数据，部件以灰色显示</div>
    <div v-else-if="!loading && styleName === 'tech'" class="legend category-legend">
      <span v-for="item in categoryLegend" :key="item.category" class="legend-item">
        <i :style="{ background: item.color, boxShadow: '0 0 6px ' + item.color }" />{{ item.label }}
      </span>
    </div>
    <div v-if="!loading && !selected" class="hint">拖动旋转 · 右键平移 · 滚轮缩放 · 点击部件查看测点</div>

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
import { COLOR_MODES, LEGEND, STYLES, VIEWS } from './scene/components'
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
      styles: STYLES,
      categoryLegend: LEGEND,
      activeView: 'overview',
      colorMode: 'none',
      styleName: 'tech',
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
        this.$emit('loaded', list)
      },
      onError: message => { this.error = message },
      onHover: info => { this.hover = info },
      onSelect: key => {
        this.selectedKey = key
        this.$emit('select', key)
      },
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
    changeStyle(key) {
      this.styleName = key
      this.scene.setStyle(key)
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
      if (!this.scene) return
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
$cyan: #38bdf8;
$line: rgba(56, 189, 248, 0.22);
$glass: rgba(8, 18, 34, 0.72);

.test-bench-view {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 8px;
  background:
    radial-gradient(ellipse 70% 55% at 50% 58%, rgba(30, 90, 170, 0.35) 0%, rgba(10, 24, 44, 0) 70%),
    linear-gradient(180deg, #0a1424 0%, #0b1a30 55%, #0a1424 100%);
  &.style-real {
    background: radial-gradient(ellipse at 50% 35%, #2a3646 0%, #18212e 55%, #10161f 100%);
  }
}
.canvas-host {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}
.hud {
  position: absolute;
  width: 18px;
  height: 18px;
  border-color: $cyan;
  border-style: solid;
  border-width: 0;
  opacity: 0.7;
  pointer-events: none;
  z-index: 2;
}
.hud-tl { top: 6px; left: 6px; border-top-width: 2px; border-left-width: 2px; }
.hud-tr { top: 6px; right: 6px; border-top-width: 2px; border-right-width: 2px; }
.hud-bl { bottom: 6px; left: 6px; border-bottom-width: 2px; border-left-width: 2px; }
.hud-br { bottom: 6px; right: 6px; border-bottom-width: 2px; border-right-width: 2px; }

.toolbar {
  position: absolute;
  top: 14px;
  left: 16px;
  right: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  pointer-events: none;
  z-index: 3;
}
.seg {
  display: inline-flex;
  background: $glass;
  border: 1px solid $line;
  border-radius: 6px;
  padding: 2px;
  pointer-events: auto;
  backdrop-filter: blur(6px);
}
.seg-right {
  margin-left: auto;
}
.seg-btn {
  border: none;
  background: transparent;
  color: #8fa6c2;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  &:hover {
    color: #e6f6ff;
  }
  &.active {
    color: #e6f6ff;
    background: linear-gradient(180deg, rgba(56, 189, 248, 0.35), rgba(37, 99, 235, 0.35));
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.6);
  }
}
.legend {
  position: absolute;
  left: 16px;
  bottom: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 12px;
  z-index: 3;
}
.legend {
  background: $glass;
  border: 1px solid $line;
  color: #c7d2e0;
  &.muted {
    color: #8fa6c2;
  }
}
.category-legend {
  flex-wrap: wrap;
  max-width: calc(100% - 320px);
  gap: 6px 14px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  i {
    width: 10px;
    height: 10px;
    border-radius: 2px;
  }
}
.hint {
  position: absolute;
  right: 16px;
  bottom: 18px;
  font-size: 12px;
  color: rgba(143, 166, 194, 0.7);
  pointer-events: none;
  z-index: 3;
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
  z-index: 4;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(6, 14, 28, 0.92);
  border: 1px solid $line;
  color: #e6f6ff;
  font-size: 12px;
  pointer-events: none;
  white-space: nowrap;
}
.info-card {
  position: absolute;
  right: 16px;
  bottom: 14px;
  width: 260px;
  max-height: 60%;
  overflow-y: auto;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(6, 14, 28, 0.86);
  border: 1px solid rgba(56, 189, 248, 0.45);
  box-shadow: 0 0 24px rgba(56, 189, 248, 0.12);
  color: #c7d2e0;
  font-size: 12px;
  z-index: 3;
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
  padding-left: 8px;
  border-left: 3px solid $cyan;
  i {
    cursor: pointer;
    color: #8fa6c2;
  }
}
.info-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 5px 0;
  border-top: 1px dashed rgba(56, 189, 248, 0.14);
}
.info-name {
  color: #8fa6c2;
}
.info-value {
  color: #e6f6ff;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
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
  color: #8fa6c2;
  font-size: 13px;
  background: rgba(8, 16, 30, 0.6);
  z-index: 5;
  i {
    font-size: 32px;
    color: #f59e0b;
  }
}
.progress {
  width: 240px;
  height: 3px;
  border-radius: 2px;
  background: rgba(56, 189, 248, 0.15);
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #2563eb, $cyan);
  box-shadow: 0 0 8px $cyan;
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
  position: relative;
  padding: 3px 8px 4px;
  border-radius: 3px;
  background: rgba(6, 16, 32, 0.8);
  border: 1px solid rgba(56, 189, 248, 0.45);
  border-left: 3px solid #38bdf8;
  color: #8fb8d8;
  font-size: 11px;
  line-height: 1.35;
  white-space: nowrap;
  box-shadow: 0 0 12px rgba(56, 189, 248, 0.15);
  // 指向部件的引线
  &::after {
    content: '';
    position: absolute;
    left: 50%;
    top: 100%;
    width: 1px;
    height: 14px;
    background: linear-gradient(180deg, rgba(56, 189, 248, 0.8), rgba(56, 189, 248, 0));
  }
  &.is-active {
    border-color: #e6f6ff;
    border-left-color: #e6f6ff;
  }
  &.is-alarm {
    border-color: #ef4444;
    border-left-color: #ef4444;
    box-shadow: 0 0 14px rgba(239, 68, 68, 0.6);
    &::after {
      background: linear-gradient(180deg, rgba(239, 68, 68, 0.9), rgba(239, 68, 68, 0));
    }
  }
}
.test-bench-view .tb-label {
  &.side-up { transform: translateY(-70%); }
  &.side-left {
    transform: translate(-65%, -70%);
    &::after { left: 85%; }
  }
  &.side-right {
    transform: translate(65%, -70%);
    &::after { left: 15%; }
  }
}
.test-bench-view .tb-label__value {
  color: #e6f6ff;
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.test-bench-view.style-real .tb-label {
  border-color: rgba(200, 210, 225, 0.35);
  border-left-color: #9fb0c6;
  box-shadow: none;
}
</style>
