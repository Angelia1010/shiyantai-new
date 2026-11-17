<template>
  <div class="report-page">
    <div class="report-head">
      <el-button size="small" icon="el-icon-arrow-left" @click="back">返回</el-button>
      <div class="report-title">
        <div class="title">诊断报告<template v-if="report"> · {{ info.file_name }}</template></div>
        <div v-if="report" class="meta">
          任务 {{ info.serial || taskId }} · 诊断时间 {{ info.diag_date || '—' }} · 操作员 {{ info.operator || '—' }}
          <template v-if="report.algorithm"> · 算法 {{ report.algorithm.version }}</template>
        </div>
      </div>
      <div class="report-actions">
        <el-button size="small" icon="el-icon-location-outline" :disabled="!locateTarget" @click="locate">在工作台定位部件</el-button>
        <el-button size="small" icon="el-icon-tickets" @click="$router.push('/tasks')">任务记录</el-button>
        <el-button size="small" type="primary" icon="el-icon-download" @click="download">下载 Word 报告</el-button>
      </div>
    </div>

    <div v-if="loading" v-loading="true" class="placeholder" />
    <el-empty v-else-if="error" :description="error" />
    <template v-else-if="report">
      <diagnosis-view v-if="hasCurves" :report="report" />
      <!-- 旧版报告（没有信号曲线）：只有结论与原因 -->
      <el-card v-else shadow="never">
        <div class="legacy-summary">
          <el-tag :type="RESULT_TAG[report.result] || 'info'" effect="dark">{{ resultLabel(report.result) }}</el-tag>
          <b>{{ report.summary }}</b>
          <span class="meta">{{ (report.condition || {}).label }}</span>
        </div>
        <cause-list :causes="report.causes || []" :history="report.history" />
        <model-compare v-if="(report.models || []).length" :models="report.models" style="margin-top: 16px" />
        <pre class="advice">{{ report.repair_advice }}</pre>
      </el-card>
      <review-list :reviews="report.reviews" />
    </template>
  </div>
</template>

<script>
import { downloadReport, getReport } from '@/api/tasks'
import { RESULT_TAG, resultLabel, summarizeReport } from '@/utils/report'
import { firstAlarmComponent, locateOnDashboard } from '@/utils/reportLinks'
import CauseList from '@/components/CauseList'
import DiagnosisView from '@/components/DiagnosisView'
import ModelCompare from '@/components/ModelCompare'
import ReviewList from '@/components/ReviewList'

export default {
  name: 'ReportPage',
  components: { CauseList, DiagnosisView, ModelCompare, ReviewList },
  data() {
    return { report: null, loading: false, error: '', RESULT_TAG }
  },
  computed: {
    taskId() {
      return this.$route.params.taskId
    },
    info() {
      return (this.report && this.report.product_info) || {}
    },
    hasCurves() {
      const c = this.report && this.report.curves
      return !!(c && (c.signals || []).length)
    },
    locateTarget() {
      return this.report ? firstAlarmComponent(summarizeReport(this.taskId, this.info.file_name, this.report)) : null
    }
  },
  watch: {
    taskId: { handler: 'load', immediate: true }
  },
  methods: {
    resultLabel,
    async load() {
      if (!this.taskId) return
      this.loading = true
      this.error = ''
      this.report = null
      try {
        this.report = await getReport(this.taskId)
        if (!this.report) this.error = '该任务还没有诊断报告'
      } catch (e) {
        this.error = '读取报告失败：任务不存在或尚未完成诊断'
      } finally {
        this.loading = false
      }
    },
    back() {
      if (window.history.length > 1) this.$router.back()
      else this.$router.push('/tasks')
    },
    locate() {
      locateOnDashboard(this.$router, this.locateTarget)
    },
    download() {
      downloadReport(this.taskId).catch(() => {})
    }
  }
}
</script>

<style scoped>
.report-page {
  padding: 16px 20px 24px;
  background: #f0f2f5;
  min-height: 100%;
}
.report-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 16px;
  margin-bottom: 12px;
}
.report-title .title {
  font-size: 17px;
  font-weight: 600;
  color: #303133;
}
.report-title .meta,
.legacy-summary .meta {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
.report-actions {
  margin-left: auto;
}
.placeholder {
  height: 320px;
}
.legacy-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.advice {
  white-space: pre-wrap;
  font-family: inherit;
  color: #606266;
  line-height: 1.7;
  margin-top: 16px;
}
</style>
