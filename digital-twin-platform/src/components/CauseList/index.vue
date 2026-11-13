<template>
  <div :class="['cause-list', { dark }]">
    <div v-if="!causes.length" class="cause-empty">未发现需要处理的故障</div>
    <div v-for="(c, i) in causes" :key="i" :class="['cause', c.severity]">
      <div class="cause-head">
        <el-tag :type="SEVERITY_TAG[c.severity]" size="mini" :effect="dark ? 'dark' : 'light'">
          {{ SEVERITY_LABELS[c.severity] }}
        </el-tag>
        <span class="cause-name">{{ c.name }}</span>
        <span v-if="c.confidence != null" class="cause-confidence" title="在各种可能的解释中，这一解释与数据相符的相对可能性">
          可能性约 {{ Math.round(c.confidence * 100) }}%
        </span>
      </div>
      <div class="cause-text">{{ c.explanation }}</div>
      <div v-if="c.alternatives && c.alternatives.length" class="cause-alt">
        其他可能：{{ c.alternatives.join('；') }}
      </div>
      <div class="cause-advice"><i class="el-icon-s-tools"></i> {{ c.advice }}</div>
      <div v-if="c.evidence && c.evidence.length" class="cause-evidence">
        <a class="toggle" @click="toggle(i)">
          判断依据（{{ c.evidence.length }} 项）<i :class="open[i] ? 'el-icon-arrow-up' : 'el-icon-arrow-down'"></i>
        </a>
        <ul v-if="open[i]">
          <li v-for="(e, j) in c.evidence" :key="j">{{ e }}</li>
        </ul>
      </div>
    </div>

    <div v-if="historyNotes.length" class="history">
      <div class="history-title"><i class="el-icon-data-line"></i> 历史趋势（基于最近 {{ history.tests }} 次诊断）</div>
      <div v-for="(t, i) in historyNotes" :key="i" class="history-item">{{ t }}</div>
    </div>
  </div>
</template>

<script>
import { SEVERITY_LABELS } from '@/utils/report'

const SEVERITY_TAG = { info: 'info', notice: 'info', warning: 'warning', abnormal: 'danger' }

/** 诊断报告的“原因分析”：每个原因 = 名称 + 解释 + 其他可能 + 建议，依据（检查发现）可展开。 */
export default {
  name: 'CauseList',
  props: {
    causes: { type: Array, default: () => [] },
    history: { type: Object, default: null },
    dark: { type: Boolean, default: false }
  },
  data() {
    return { open: {}, SEVERITY_TAG, SEVERITY_LABELS }
  },
  computed: {
    historyNotes() {
      if (!this.history) return []
      const notes = (this.history.findings || []).map(f => f.detail)
      if (this.history.mass_split) notes.push(this.history.mass_split.text)
      return notes
    }
  },
  methods: {
    toggle(i) {
      this.$set(this.open, i, !this.open[i])
    }
  }
}
</script>

<style scoped>
.cause {
  padding: 8px 10px;
  margin-bottom: 8px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 2px;
  font-size: 13px;
  line-height: 1.6;
}
.cause.abnormal {
  border-left-color: #f56c6c;
  background: #fef0f0;
}
.cause-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cause-name {
  font-weight: 600;
}
.cause-text {
  margin-top: 4px;
  color: #606266;
}
.cause-alt {
  margin-top: 2px;
  color: #909399;
  font-size: 12px;
}
.cause-advice {
  margin-top: 4px;
  color: #303133;
}
.cause-evidence .toggle {
  font-size: 12px;
  color: #409eff;
  cursor: pointer;
}
.cause-evidence ul {
  margin: 4px 0 0;
  padding-left: 18px;
  color: #606266;
  font-size: 12px;
}
.cause-empty {
  color: #67c23a;
  font-size: 13px;
  padding: 4px 0;
}
.cause-confidence {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}

.history {
  margin-top: 6px;
  padding: 8px 10px;
  background: #f4f4f5;
  border-radius: 2px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}
.history-title {
  font-weight: 600;
  margin-bottom: 2px;
}

/* 驾驶舱深色主题 */
.dark .cause {
  background: rgba(230, 162, 60, 0.08);
  color: #cfe3ff;
}
.dark .cause.abnormal {
  background: rgba(245, 108, 108, 0.1);
}
.dark .cause-text,
.dark .cause-evidence ul,
.dark .history {
  color: #9fb4d0;
}
.dark .cause-advice {
  color: #dce9ff;
}
.dark .history {
  background: rgba(255, 255, 255, 0.04);
}
.dark .cause-empty {
  color: #4ade80;
}
</style>
