<template>
  <div ref="root" class="dashboard">
    <!-- 状态栏 -->
    <header class="topbar">
      <span :class="['pill', live.state]"><i class="dot" />{{ liveStateText }}</span>
      <span class="status-msg" :title="live.path || ''">{{ liveMessage }}</span>
      <button class="link-btn" @click="openPathDialog">
        <i class="el-icon-folder-opened" /> {{ live.path ? '数据目录' : '设置数据目录' }}
      </button>
      <div class="stats">
        <div class="stat"><span>诊断记录</span><b>{{ records.length }}</b></div>
        <div :class="['stat', { bad: abnormalCount }]"><span>异常</span><b>{{ abnormalCount }}</b></div>
        <div :class="['stat', { bad: alarmComponents.length }]"><span>告警部件</span><b>{{ alarmComponents.length }}</b></div>
      </div>
      <span class="clock">{{ clock }}</span>
      <button class="icon-btn" :title="isFullscreen ? '退出大屏' : '大屏显示'" @click="toggleFullscreen">
        <i :class="isFullscreen ? 'el-icon-copy-document' : 'el-icon-full-screen'" />
      </button>
    </header>

    <!-- 三维模型 -->
    <section class="stage">
      <test-bench-view
        ref="bench"
        :feature-map="featureMap"
        :alarms="alarmComponents"
        @loaded="parts = $event"
        @select="selectedPart = $event"
      />
    </section>

    <!-- 右侧：诊断 -->
    <aside class="panel diagnosis">
      <div class="panel-title">最新诊断</div>
      <div v-if="diagnosisStatus" class="diag-status"><i v-if="diagnosisStatus.includes('正在')" class="el-icon-loading" />自动诊断：{{ diagnosisStatus }}</div>
      <div v-if="latestResult" :class="['verdict', latestResult.result]">
        <div class="verdict-head">
          <span class="verdict-badge">{{ latestResult.statusText }}</span>
          <span class="verdict-time">{{ latestResult.timestamp }}</span>
        </div>
        <div class="verdict-file" :title="latestResult.fileName">{{ latestResult.fileName }}</div>
        <div class="verdict-fault">{{ latestResult.diagnosis.fault_name || '—' }}</div>
        <div class="verdict-actions">
          <button v-if="alarmComponents.length" class="text-btn danger" @click="locateAlarm">定位异常部件</button>
          <button class="text-btn" @click="openDetail(latestResult)">查看详情</button>
        </div>
      </div>
      <div v-else class="empty-card">
        <i class="el-icon-data-analysis" />
        <div>暂无诊断结果</div>
        <small>运行自动诊断后在此显示结论</small>
      </div>

      <template v-if="meterDeviations.length">
        <div class="panel-title sub">流量计偏差（阈值 15%）</div>
        <div v-for="m in meterDeviations" :key="m.name" class="deviation">
          <div class="deviation-top">
            <span>{{ m.name }}</span>
            <span :class="{ bad: m.abnormal }">{{ m.text }}</span>
          </div>
          <div class="deviation-track">
            <div class="deviation-bar" :class="{ bad: m.abnormal }" :style="{ width: m.width + '%' }" />
            <div class="deviation-limit" :style="{ left: limitPosition + '%' }" />
          </div>
        </div>
      </template>

      <div class="panel-title sub">设备部件<span class="counter">{{ parts.length }} 个</span></div>
      <div class="parts">
        <button
          v-for="p in parts"
          :key="p.key"
          :class="['part', { active: selectedPart === p.key, bad: alarmComponents.includes(p.key) }]"
          @click="$refs.bench.focus(p.key)"
        >
          <i class="part-dot" />{{ p.label }}
        </button>
        <div v-if="!parts.length" class="empty small">模型加载中...</div>
      </div>

      <div class="panel-title sub">
        诊断记录
        <span class="counter">{{ records.length }} 条<template v-if="abnormalCount">，异常 {{ abnormalCount }}</template></span>
      </div>
      <div class="records">
        <div
          v-for="r in records"
          :key="r.taskId"
          :class="['record', r.result]"
          @click="openDetail(r)"
        >
          <span class="record-dot" />
          <div class="record-body">
            <div class="record-file" :title="r.fileName">{{ r.fileName }}</div>
            <div class="record-meta">{{ r.timestamp }} · {{ r.statusText }}</div>
          </div>
        </div>
        <div v-if="!records.length" class="empty">暂无记录</div>
      </div>
    </aside>

    <!-- 下左：关键测点 -->
    <section class="panel metrics">
      <div class="panel-title">
        关键测点
        <span class="group-legend">
          <span v-for="group in metricGroups" :key="group.title" :class="['tag', group.key]">{{ group.title }}</span>
        </span>
      </div>
      <div class="metric-grid">
        <template v-for="group in metricGroups">
          <div
            v-for="field in group.fields"
            :key="field"
            :class="['metric', group.key, { empty: !featureMap[field] }]"
            :title="field"
          >
            <svg class="spark" viewBox="0 0 100 24" preserveAspectRatio="none">
              <polyline v-if="history[field].length > 1" :points="sparkline(field)" />
            </svg>
            <div class="metric-name">{{ field }}</div>
            <div class="metric-value">{{ latest(field) }}<small>{{ unit(field) }}</small></div>
          </div>
        </template>
      </div>
    </section>

    <!-- 下右：趋势 -->
    <section class="panel trend">
      <div class="trend-head">
        <div class="panel-title">趋势</div>
        <div class="tabs">
          <button
            v-for="(group, key) in trendGroups"
            :key="key"
            :class="['tab', { active: trendKey === key }]"
            @click="trendKey = key"
          >{{ group.label }}</button>
        </div>
      </div>
      <div class="trend-body">
        <trend-chart :series="trendSeries" :unit="trendGroups[trendKey].unit" />
        <div v-if="!trendSeries.length" class="trend-empty">
          <i class="el-icon-s-data" />暂无{{ trendGroups[trendKey].label }}数据
        </div>
      </div>
    </section>

    <!-- 诊断详情 -->
    <transition name="fade">
      <div v-if="detail" class="modal" @click.self="detail = null">
        <div class="modal-card">
          <div class="modal-head">
            <span>诊断详情 · {{ detail.fileName }}</span>
            <i class="el-icon-close" @click="detail = null" />
          </div>
          <div v-if="detail.loading" class="empty">加载中...</div>
          <div v-else class="modal-body">
            <div class="kv"><span>诊断结果</span><b :class="detail.result">{{ detail.statusText }}</b></div>
            <div class="kv"><span>诊断时间</span><b>{{ detail.timestamp }}</b></div>
            <div class="kv"><span>故障类型</span><b>{{ detail.diagnosis.fault_name || '—' }}</b></div>
            <div class="kv"><span>故障定位</span><b>{{ detail.diagnosis.location || '—' }}</b></div>
            <div class="section-title">指标</div>
            <table class="indicators">
              <tr v-for="(item, i) in detail.indicators" :key="i" :class="{ bad: item.abnormal }">
                <td>{{ item.name }}</td>
                <td>{{ item.reference }}</td>
                <td>{{ item.value }}</td>
              </tr>
            </table>
            <div class="section-title">分析与建议</div>
            <pre class="advice">{{ detail.repairAdvice }}</pre>
          </div>
          <div class="modal-foot">
            <button class="text-btn" @click="download(detail.taskId)">下载 Word 报告</button>
          </div>
        </div>
      </div>
    </transition>
    <!-- 数据目录设置 -->
    <transition name="fade">
      <div v-if="pathDialog.visible" class="modal" @click.self="pathDialog.visible = false">
        <div class="modal-card path-card">
          <div class="modal-head">
            <span>实时数据目录</span>
            <i class="el-icon-close" @click="pathDialog.visible = false" />
          </div>
          <div class="modal-body">
            <p class="path-hint">
              填写试验台写入数据文件的目录（服务器上能访问到的完整路径，共享目录的映射盘符或网络路径均可），
              其下各级子目录会一起监控。设置后会保存，服务重启后自动恢复。
            </p>
            <input
              v-model.trim="pathDialog.value"
              class="path-input"
              placeholder="例如 Z:/试验数据 或 //192.168.1.20/data"
              @keyup.enter="savePath"
            >
            <p v-if="pathDialog.error" class="path-error">{{ pathDialog.error }}</p>
            <template v-if="pathDialog.dirs.length">
              <div class="dir-title">已登记的数据目录（点击选用）</div>
              <div v-for="dir in pathDialog.dirs" :key="dir.path" class="dir-item">
                <span class="dir-path" :title="dir.path" @click="pathDialog.value = dir.path">
                  <i class="el-icon-folder" />{{ dir.path }}
                </span>
                <span v-if="dir.preset" class="dir-tag">预置</span>
                <i v-else class="el-icon-delete dir-remove" title="取消登记" @click="removeDir(dir.path)" />
              </div>
            </template>
          </div>
          <div class="modal-foot">
            <button class="text-btn" @click="pathDialog.visible = false">取消</button>
            <button class="primary-btn" :disabled="pathDialog.saving || !pathDialog.value" @click="savePath">
              {{ pathDialog.saving ? '保存中...' : '开始监控' }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script>
/**
 * 工作台：实时监控。
 *
 * 实时数据：每秒向文件服务取最新的特征帧（/live/frames），由后端增量读取试验台正在写入的文件，
 *   与“自动诊断”页面是否打开无关，任何电脑打开工作台都能看到。
 * 诊断结果：“自动诊断”运行时通过 BroadcastChannel 推送；没有推送时显示最近的诊断任务。
 */
import screenfull from 'screenfull'
import { getDataDirs, getLiveFrames, removeDataDir, setWatchPath } from '@/api/files'
import { downloadReport, getReport, listTasks } from '@/api/tasks'
import { errorMessage } from '@/utils/request'
import { MessageType, openChannel } from '@/utils/broadcastChannel'
import { fieldUnit, formatValue } from '@/utils/features'
import { resultLabel, summarizeReport } from '@/utils/report'
import { DIAGNOSIS_TARGETS } from './scene/components'
import TestBenchView from './TestBenchView.vue'
import TrendChart from './TrendChart.vue'

const POLL_INTERVAL_MS = 1000
const HISTORY_LENGTH = 90 // 迷你曲线和趋势图保留的帧数（每帧 1 秒）
const LIVE_STATE_TEXT = { off: '未配置', waiting: '等待数据', live: '采集中' }
const MAX_RECORDS = 100
const DEVIATION_LIMIT = 15 // %
const DEVIATION_SCALE = 30 // 偏差条满格对应的百分比

const METRIC_GROUPS = [
  { key: 'pump', title: '被试件', fields: ['燃油泵实际转速', '电传实际转速', '电传扭矩'] },
  { key: 'supply', title: '供油', fields: ['供油压力1-1', '供油压力1-2', '供油温度1-1', '供油流量1-1'] },
  { key: 'return', title: '回油', fields: ['回油压力1-1', '回油压力1-2', '回油温度1-1', '回油流量1-1', '回油流量1-2'] }
]

const TREND_GROUPS = {
  pressure: { label: '压力', unit: 'MPa', fields: ['供油压力1-1', '供油压力1-2', '回油压力1-1', '回油压力1-2', 'P1进口压力'] },
  temperature: { label: '温度', unit: '°C', fields: ['供油温度1-1', '供油温度1-2', '回油温度1-1', '回油温度1-2', 'T20加热出口温度'] },
  flow: { label: '流量', unit: 'L/h', fields: ['供油流量1-1', '供油流量1-2', '回油流量1-1', '回油流量1-2', '齿轮流量计'] },
  speed: { label: '转速', unit: 'rpm', fields: ['燃油泵实际转速', '电传实际转速'] }
}

const TRACKED_FIELDS = [...new Set([
  ...METRIC_GROUPS.flatMap(g => g.fields),
  ...Object.values(TREND_GROUPS).flatMap(g => g.fields)
])]

function formatTime(ms) {
  const d = new Date(ms)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default {
  name: 'Dashboard',
  components: { TestBenchView, TrendChart },
  data() {
    return {
      featureMap: {},
      history: Object.fromEntries(TRACKED_FIELDS.map(f => [f, []])),
      live: { state: 'off', path: null, file: null, frameTime: '' },
      pathDialog: { visible: false, value: '', saving: false, error: '', dirs: [] },
      diagnosisStatus: '',
      records: [],
      latestResult: null,
      alarmComponents: [],
      detail: null,
      parts: [],
      selectedPart: null,
      trendKey: 'pressure',
      clock: '',
      isFullscreen: false,
      metricGroups: METRIC_GROUPS,
      trendGroups: TREND_GROUPS,
      limitPosition: (DEVIATION_LIMIT / DEVIATION_SCALE) * 100
    }
  },
  computed: {
    liveStateText() {
      return LIVE_STATE_TEXT[this.live.state] || '未配置'
    },
    liveMessage() {
      const { state, path, file, frameTime } = this.live
      if (state === 'off') return '尚未配置实时数据目录，点击右侧按钮设置试验台写入数据的目录'
      if (state === 'live') return `正在读取 ${file}（数据时间 ${frameTime}）`
      const last = file ? `，最近文件 ${file}` : ''
      return `监控 ${path}，等待试验台写入数据${last}`
    },
    hasData() {
      return Object.keys(this.featureMap).length > 0
    },
    abnormalCount() {
      return this.records.filter(r => r.result === 'abnormal').length
    },
    trendSeries() {
      return TREND_GROUPS[this.trendKey].fields
        .filter(f => this.history[f].length)
        .map(f => ({ name: f, data: this.history[f] }))
    },
    // 从最新报告里取两个回路流量计的偏差
    meterDeviations() {
      if (!this.latestResult) return []
      return this.latestResult.indicators
        .filter(i => i.name.endsWith('流量偏差'))
        .map(i => {
          const pct = parseFloat(i.value)
          return {
            name: i.name.replace(' 流量偏差', ''),
            text: i.value,
            abnormal: !!i.abnormal,
            width: Number.isNaN(pct) ? 0 : Math.min(100, (pct / DEVIATION_SCALE) * 100)
          }
        })
    }
  },
  created() {
    this.lastSeq = 0
    this.currentFile = null
    this.channel = openChannel(this.handleMessage)
    this.pollLive()
    this.tick()
    this.clockTimer = setInterval(this.tick, 1000)
    if (screenfull.enabled) screenfull.on('change', this.onFullscreenChange)
    this.loadRecentTasks()
  },
  beforeDestroy() {
    this.destroyed = true
    clearTimeout(this.pollTimer)
    clearInterval(this.clockTimer)
    this.channel.close()
    if (screenfull.enabled) screenfull.off('change', this.onFullscreenChange)
  },
  methods: {
    // ------------------------------------------------------------ 数据接收
    handleMessage({ type, payload }) {
      if (type === MessageType.DIAGNOSIS_STATUS) {
        this.diagnosisStatus = payload.message
      } else if (type === MessageType.DIAGNOSIS_RESULT) {
        this.addResult(payload)
      }
    },

    /** 每秒取一次新帧；首次（或服务重启后）取最近 HISTORY_LENGTH 帧填满曲线。 */
    async pollLive() {
      try {
        const first = this.lastSeq === 0
        const data = await getLiveFrames(this.lastSeq, first ? HISTORY_LENGTH : 300)
        if (data.latest_seq < this.lastSeq) {
          // 文件服务重启过，序号从头开始：下一轮重新拉取
          this.lastSeq = 0
          this.resetHistory()
        } else {
          data.frames.forEach(this.applyFrame)
          this.lastSeq = data.latest_seq
        }
        this.live = { ...this.live, state: data.state, file: data.file, path: data.path }
      } catch (e) {
        this.live = { ...this.live, state: 'off' }
      } finally {
        if (!this.destroyed) this.pollTimer = setTimeout(this.pollLive, POLL_INTERVAL_MS)
      }
    },
    applyFrame(frame) {
      if (frame.file !== this.currentFile) {
        // 换了一个数据文件（新的试验工况），曲线重新开始
        this.currentFile = frame.file
        this.resetHistory()
      }
      this.featureMap = frame.stats
      this.live.frameTime = frame.time
      for (const field of TRACKED_FIELDS) {
        const stat = frame.stats[field]
        if (!stat) continue
        const series = this.history[field]
        series.push(stat.avg)
        if (series.length > HISTORY_LENGTH) series.shift()
      }
    },
    resetHistory() {
      for (const field of TRACKED_FIELDS) this.history[field] = []
    },
    openPathDialog() {
      this.pathDialog = { visible: true, value: this.live.path || '', saving: false, error: '', dirs: [] }
      this.loadDirs()
    },
    async loadDirs() {
      try {
        const { preset, registered } = await getDataDirs()
        this.pathDialog.dirs = [
          ...registered.map(path => ({ path, preset: false })),
          ...preset.map(path => ({ path, preset: true }))
        ]
      } catch (e) {
        this.pathDialog.dirs = []
      }
    },
    async removeDir(path) {
      try {
        await this.$confirm(`取消登记后将不能再访问该目录：${path}`, '取消登记', { type: 'warning' })
      } catch (e) {
        return // 用户取消
      }
      await removeDataDir(path)
      this.loadDirs()
    },
    async savePath() {
      if (!this.pathDialog.value || this.pathDialog.saving) return
      this.pathDialog.saving = true
      this.pathDialog.error = ''
      try {
        const status = await setWatchPath(this.pathDialog.value, true)
        this.live = { ...this.live, state: status.state, path: status.path, file: status.file }
        this.pathDialog.visible = false
        this.$message.success(`开始监控：${status.path}`)
      } catch (e) {
        this.pathDialog.error = errorMessage(e)
      } finally {
        this.pathDialog.saving = false
      }
    },
    addResult(summary) {
      this.records = [summary, ...this.records.filter(r => r.taskId !== summary.taskId)].slice(0, MAX_RECORDS)
      this.latestResult = summary
      this.alarmComponents = summary.result === 'abnormal' ? this.alarmTargets(summary) : []
    },
    alarmTargets(summary) {
      const keys = new Set()
      for (const item of summary.indicators) {
        if (!item.abnormal) continue
        for (const [meter, component] of Object.entries(DIAGNOSIS_TARGETS)) {
          if (item.name.startsWith(meter)) keys.add(component)
        }
      }
      return [...keys]
    },
    async loadRecentTasks() {
      try {
        const { items } = await listTasks({ page: 1, page_size: 10, status: 'Completed' })
        if (this.records.length) return // 已收到实时结果
        this.records = items.map(t => ({
          taskId: t.task_id,
          fileName: t.file_name,
          result: t.result,
          statusText: resultLabel(t.result),
          timestamp: formatTime(t.created_at),
          fromHistory: true
        }))
      } catch (e) {
        // 提示已由请求拦截器显示
      }
    },

    // ------------------------------------------------------------ 展示
    latest(field) {
      const stat = this.featureMap[field]
      return stat ? formatValue(stat.avg) : '--'
    },
    unit: fieldUnit,
    sparkline(field) {
      const data = this.history[field]
      if (data.length < 2) return ''
      let min = Infinity
      let max = -Infinity
      for (const v of data) {
        if (v < min) min = v
        if (v > max) max = v
      }
      const span = max - min || 1
      const step = 100 / (HISTORY_LENGTH - 1)
      const offset = HISTORY_LENGTH - data.length
      return data.map((v, i) => `${((offset + i) * step).toFixed(1)},${(22 - ((v - min) / span) * 20).toFixed(1)}`).join(' ')
    },
    tick() {
      const d = new Date()
      const pad = n => String(n).padStart(2, '0')
      this.clock = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    },
    toggleFullscreen() {
      if (screenfull.enabled) screenfull.toggle(this.$refs.root)
    },
    onFullscreenChange() {
      this.isFullscreen = screenfull.isFullscreen
    },
    locateAlarm() {
      if (this.alarmComponents.length) this.$refs.bench.focus(this.alarmComponents[0])
    },
    async openDetail(record) {
      if (!record.fromHistory) {
        this.detail = record
        return
      }
      this.detail = { ...record, loading: true }
      try {
        const report = await getReport(record.taskId)
        this.detail = { ...summarizeReport(record.taskId, record.fileName, report), timestamp: record.timestamp }
      } catch (e) {
        this.detail = null
      }
    },
    download(taskId) {
      if (taskId) downloadReport(taskId).catch(() => {})
    }
  }
}
</script>

<style lang="scss" scoped>
$bg: #070e1a;
$panel: rgba(12, 24, 42, 0.86);
$border: rgba(56, 189, 248, 0.16);
$text: #c7d2e0;
$muted: #7891ad;
$bright: #eef6ff;
$accent: #38bdf8;
$blue: #2f6bff;
$ok: #22c55e;
$bad: #ef4444;
$warn: #f59e0b;

.dashboard {
  height: 100%;
  min-height: 600px;
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr) 320px;
  grid-template-rows: 46px minmax(0, 1fr) 236px;
  grid-template-areas:
    'top top top'
    'stage stage diagnosis'
    'metrics trend diagnosis';
  gap: 10px;
  padding: 10px;
  background:
    radial-gradient(ellipse at 50% 0%, rgba(37, 99, 235, 0.12), transparent 60%),
    $bg;
  color: $text;
  font-size: 13px;
  overflow: hidden;
}

/* ---------- 状态栏 ---------- */
.topbar {
  grid-area: top;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 12px;
  background: $panel;
  border: 1px solid $border;
  border-radius: 8px;
}
.status-msg {
  min-width: 0;
  color: $muted;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.link-btn {
  flex-shrink: 0;
  background: transparent;
  cursor: pointer;
  color: $accent;
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid rgba(56, 189, 248, 0.4);
  border-radius: 4px;
  &:hover { background: rgba(56, 189, 248, 0.12); }
}
.stats {
  margin-left: auto;
  display: flex;
  gap: 18px;
  flex-shrink: 0;
}
.stat {
  display: flex;
  align-items: baseline;
  gap: 6px;
  span { color: $muted; font-size: 12px; }
  b {
    color: $bright;
    font-size: 16px;
    font-variant-numeric: tabular-nums;
  }
  &.bad b { color: $bad; }
}
.pill {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  color: $muted;
  border: 1px solid rgba(120, 150, 190, 0.25);
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: $muted;
  }
  &.live {
    color: $ok;
    border-color: rgba(34, 197, 94, 0.35);
    .dot {
      background: $ok;
      box-shadow: 0 0 6px $ok;
      animation: blink 1.6s ease-in-out infinite;
    }
  }
  &.waiting {
    color: #7dd3fc;
    border-color: rgba(56, 189, 248, 0.35);
    .dot { background: #38bdf8; }
  }
}
@keyframes blink {
  50% { opacity: 0.3; }
}
.clock {
  flex-shrink: 0;
  padding-left: 14px;
  border-left: 1px solid $border;
  color: $text;
  font-variant-numeric: tabular-nums;
}
.icon-btn {
  flex-shrink: 0;
  border: 1px solid $border;
  background: transparent;
  color: $text;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: pointer;
  &:hover { color: $bright; border-color: $accent; }
}

/* ---------- 面板 ---------- */
.panel {
  position: relative;
  background: $panel;
  border: 1px solid $border;
  border-radius: 8px;
  padding: 12px 14px;
  min-height: 0;
  // 顶部高光线
  &::before {
    content: '';
    position: absolute;
    top: -1px;
    left: 14px;
    width: 64px;
    height: 2px;
    background: linear-gradient(90deg, $accent, transparent);
  }
}
.panel-title {
  position: relative;
  font-size: 14px;
  font-weight: 600;
  color: $bright;
  margin-bottom: 10px;
  padding-left: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  letter-spacing: 0.5px;
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    width: 3px;
    height: 12px;
    margin-top: -6px;
    border-radius: 2px;
    background: $accent;
    box-shadow: 0 0 6px $accent;
  }
  &.sub { margin-top: 18px; }
}
.counter {
  font-weight: normal;
  color: $muted;
  font-size: 12px;
  letter-spacing: 0;
}
.empty {
  color: $muted;
  text-align: center;
  padding: 16px 0;
  &.small { padding: 8px 0; font-size: 12px; }
}
.empty-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 18px 0;
  border: 1px dashed $border;
  border-radius: 8px;
  color: $text;
  i { font-size: 26px; color: rgba(56, 189, 248, 0.5); margin-bottom: 4px; }
  small { color: $muted; font-size: 12px; }
}

/* ---------- 关键测点 ---------- */
$pump: #a78bfa;
$supply: #38bdf8;
$return: #fbbf24;

.metrics {
  grid-area: metrics;
  display: flex;
  flex-direction: column;
}
.group-legend {
  display: flex;
  gap: 10px;
  font-weight: normal;
  letter-spacing: 0;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: $muted;
  &::before {
    content: '';
    width: 8px;
    height: 3px;
    border-radius: 2px;
  }
  &.pump::before { background: $pump; }
  &.supply::before { background: $supply; }
  &.return::before { background: $return; }
}
.metric-grid {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(124px, 1fr));
  grid-auto-rows: 50px;
  gap: 6px;
  margin-right: -8px;
  padding-right: 8px;
}
.metric {
  position: relative;
  overflow: hidden;
  padding: 6px 9px;
  border-radius: 6px;
  background: rgba(56, 189, 248, 0.04);
  border: 1px solid rgba(56, 189, 248, 0.1);
  border-top: 2px solid var(--group-color);
  transition: border-color 0.15s, background 0.15s;
  &.pump { --group-color: #{$pump}; }
  &.supply { --group-color: #{$supply}; }
  &.return { --group-color: #{$return}; }
  &:hover { background: rgba(56, 189, 248, 0.08); }
  &.empty .metric-value { color: #4d6380; }
}
.metric-name {
  position: relative;
  color: $muted;
  font-size: 12px;
  line-height: 16px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.metric-value {
  position: relative;
  color: $bright;
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  small {
    margin-left: 3px;
    font-size: 11px;
    font-weight: normal;
    color: $muted;
  }
}
// 迷你曲线作为卡片背景
.spark {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  height: 60%;
  opacity: 0.55;
  polyline {
    fill: none;
    stroke: var(--group-color);
    stroke-width: 1.2;
    vector-effect: non-scaling-stroke;
  }
}

/* ---------- 三维模型 ---------- */
.stage {
  grid-area: stage;
  position: relative;
  min-height: 0;
  border: 1px solid $border;
  border-radius: 8px;
  box-shadow: inset 0 0 40px rgba(56, 189, 248, 0.06);
}

/* ---------- 设备部件 ---------- */
.parts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.part {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 4px 9px;
  border-radius: 4px;
  border: 1px solid rgba(56, 189, 248, 0.15);
  background: rgba(56, 189, 248, 0.04);
  color: $text;
  font-size: 12px;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  &:hover { border-color: rgba(56, 189, 248, 0.45); color: $bright; }
  &.active {
    border-color: $accent;
    color: $bright;
    background: rgba(56, 189, 248, 0.16);
  }
  &.bad {
    border-color: rgba(239, 68, 68, 0.6);
    color: #ffb4b4;
    .part-dot { background: $bad; box-shadow: 0 0 6px $bad; }
  }
}
.part-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(56, 189, 248, 0.6);
}

/* ---------- 右：诊断 ---------- */
.diagnosis {
  grid-area: diagnosis;
  display: flex;
  flex-direction: column;
}
.verdict {
  padding: 12px;
  border-radius: 8px;
  border: 1px solid $border;
  background: rgba(255, 255, 255, 0.025);
  &.normal { border-left: 3px solid $ok; background: rgba(34, 197, 94, 0.05); }
  &.abnormal { border-left: 3px solid $bad; background: rgba(239, 68, 68, 0.08); }
  &.inconclusive { border-left: 3px solid $warn; }
}
.verdict-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.verdict-badge {
  font-size: 18px;
  font-weight: 700;
  color: $bright;
  .normal & { color: $ok; }
  .abnormal & { color: $bad; }
  .inconclusive & { color: $warn; }
}
.verdict-time,
.verdict-file {
  color: $muted;
  font-size: 12px;
}
.verdict-file {
  margin-top: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.verdict-fault {
  margin-top: 4px;
  color: $bright;
}
.verdict-actions {
  margin-top: 10px;
  display: flex;
  gap: 12px;
}
.text-btn {
  border: none;
  background: none;
  padding: 0;
  color: $accent;
  cursor: pointer;
  font-size: 12px;
  &.danger { color: #ff7a7a; }
  &:hover { text-decoration: underline; }
}
.deviation {
  margin-bottom: 10px;
}
.deviation-top {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 4px;
  font-variant-numeric: tabular-nums;
  .bad { color: $bad; }
}
.deviation-track {
  position: relative;
  height: 6px;
  border-radius: 3px;
  background: rgba(120, 150, 190, 0.15);
}
.deviation-bar {
  height: 100%;
  border-radius: 3px;
  background: $ok;
  &.bad { background: $bad; }
}
.deviation-limit {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 12px;
  background: $warn;
}
.records {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.record {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
  &:hover { background: rgba(56, 189, 248, 0.06); }
}
.record-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: $muted;
  .normal & { background: $ok; }
  .abnormal & { background: $bad; }
  .inconclusive & { background: $warn; }
}
.record-body {
  min-width: 0;
}
.record-file {
  color: $bright;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.record-meta {
  color: $muted;
  font-size: 12px;
}

/* ---------- 下：趋势 ---------- */
.trend {
  grid-area: trend;
  display: flex;
  flex-direction: column;
}
.trend-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  .panel-title { margin-bottom: 0; }
}
.tabs {
  display: inline-flex;
  gap: 2px;
  background: rgba(56, 189, 248, 0.05);
  border: 1px solid $border;
  border-radius: 6px;
  padding: 2px;
}
.tab {
  border: none;
  background: transparent;
  color: $muted;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 4px;
  cursor: pointer;
  &.active {
    color: $bright;
    background: rgba(56, 189, 248, 0.22);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.55);
  }
}
.trend-body {
  position: relative;
  flex: 1;
  min-height: 0;
}
.trend-empty {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: $muted;
  pointer-events: none;
  i { font-size: 20px; color: rgba(56, 189, 248, 0.45); }
}

/* ---------- 详情弹窗 ---------- */
.modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
}
.modal-card {
  width: min(720px, 92vw);
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  background: #0c1828;
  border: 1px solid $border;
  border-radius: 10px;
  color: $text;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid $border;
  color: $bright;
  font-weight: 600;
  i { cursor: pointer; color: $muted; }
}
.modal-body {
  padding: 14px 18px;
  overflow-y: auto;
}
.path-card {
  width: min(560px, 92vw);
}
.path-hint {
  margin: 0 0 12px;
  color: $muted;
  font-size: 12px;
  line-height: 1.7;
}
.path-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid $border;
  background: rgba(56, 189, 248, 0.05);
  color: $bright;
  font-size: 13px;
  outline: none;
  &:focus { border-color: $accent; }
}
.dir-title {
  margin: 16px 0 6px;
  color: $muted;
  font-size: 12px;
}
.dir-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 4px;
  &:hover { background: rgba(56, 189, 248, 0.06); }
}
.dir-path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: $text;
  cursor: pointer;
  i { margin-right: 6px; color: $accent; }
  &:hover { color: $bright; }
}
.dir-tag {
  font-size: 11px;
  color: $muted;
  border: 1px solid $border;
  border-radius: 3px;
  padding: 0 5px;
}
.dir-remove {
  color: $muted;
  cursor: pointer;
  &:hover { color: $bad; }
}
.path-error {
  margin: 8px 0 0;
  color: $bad;
  font-size: 12px;
}
.primary-btn {
  margin-left: 16px;
  padding: 6px 16px;
  border: none;
  border-radius: 4px;
  background: $blue;
  color: #fff;
  cursor: pointer;
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}
.diag-status {
  margin: -4px 0 10px;
  color: $muted;
  font-size: 12px;
  i { margin-right: 4px; }
}
.modal-foot {
  padding: 12px 18px;
  border-top: 1px solid $border;
  text-align: right;
}
.kv {
  display: flex;
  gap: 16px;
  padding: 4px 0;
  span { width: 72px; color: $muted; }
  b { font-weight: 500; color: $bright; }
  b.normal { color: $ok; }
  b.abnormal { color: $bad; }
  b.inconclusive { color: $warn; }
}
.section-title {
  margin: 14px 0 8px;
  color: $bright;
  font-weight: 600;
}
.indicators {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  td {
    padding: 6px 8px;
    border-bottom: 1px solid $border;
  }
  td:last-child {
    text-align: right;
    color: $bright;
    font-variant-numeric: tabular-nums;
  }
  tr.bad td:last-child { color: $bad; }
}
.advice {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.7;
  color: $text;
}
.fade-enter-active,
.fade-leave-active { transition: opacity 0.2s; }
.fade-enter,
.fade-leave-to { opacity: 0; }

/* 窄屏：改为上下排列 */
@media (max-width: 1280px) {
  .dashboard {
    grid-template-columns: minmax(0, 1fr) 280px;
    grid-template-rows: 46px minmax(440px, 1fr) 236px 236px;
    grid-template-areas:
      'top top'
      'stage diagnosis'
      'metrics diagnosis'
      'trend trend';
    overflow-y: auto;
  }
  .stats { display: none; }
}
</style>
