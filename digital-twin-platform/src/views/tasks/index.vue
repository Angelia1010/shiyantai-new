<template>
  <div class="app-container">
    <div class="page-header">
      <h2 class="page-title">任务列表</h2>
    </div>
    <el-card class="box-card" :body-style="{ padding: '20px' }">
      <el-form :inline="true" :model="filters" size="small">
        <el-form-item label="关键字">
          <el-input v-model="filters.keyword" placeholder="任务ID或文件名" clearable @keyup.enter.native="search" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部" clearable>
            <el-option v-for="(label, value) in STATUS_LABELS" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="创建日期">
          <el-date-picker
            v-model="filters.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="timestamp"
          />
        </el-form-item>
        <el-form-item>
          <el-button @click="reset">重置</el-button>
          <el-button type="primary" @click="search">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="box-card" :body-style="{ padding: '20px' }">
      <div class="btn-row">
        <el-button v-if="selected.length" type="danger" size="small" @click="removeTasks(selected)">
          批量删除 ({{ selected.length }})
        </el-button>
        <el-button v-if="selected.length" type="success" size="small" @click="downloadMany(selected)">
          批量下载 ({{ selected.length }})
        </el-button>
        <el-button type="primary" size="small" @click="$router.push('/autoDiagnosis')">新建诊断</el-button>
        <el-button size="small" icon="el-icon-data-line" @click="trendVisible = true">诊断趋势</el-button>
      </div>

      <el-table
        v-loading="loading"
        :data="tasks"
        border
        row-key="task_id"
        height="calc(100vh - 430px)"
        @selection-change="selected = $event"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="task_id" label="任务ID" width="200" />
        <el-table-column label="创建时间" width="170">
          <template slot-scope="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="方式" width="90">
          <template slot-scope="{ row }">{{ MODE_LABELS[row.mode] || row.mode }}</template>
        </el-table-column>
        <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="path" label="目录" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template slot-scope="{ row }">
            <el-tooltip v-if="row.status === 'Failed'" :content="row.error || ''" placement="top">
              <el-tag type="danger" size="small">失败</el-tag>
            </el-tooltip>
            <el-tag v-else :type="row.status === 'Completed' ? 'success' : 'info'" size="small">
              {{ STATUS_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="诊断结果" width="100">
          <template slot-scope="{ row }">
            <el-tag v-if="row.result" :type="RESULT_TAG[row.result]" size="small">{{ resultLabel(row.result) }}</el-tag>
            <span v-else>--</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template slot-scope="{ row }">
            <template v-if="row.status === 'Completed'">
              <el-button size="mini" type="primary" @click="viewReport(row)">查看</el-button>
              <el-button size="mini" @click="download(row)">下载</el-button>
            </template>
            <el-button size="mini" @click="removeTasks([row])">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pagination"
        :current-page="page"
        :page-sizes="[20, 50, 100, 200]"
        :page-size="pageSize"
        layout="total, sizes, prev, pager, next, jumper"
        :total="total"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </el-card>

    <el-dialog title="诊断趋势" :visible.sync="trendVisible" width="80%" top="5vh" destroy-on-close>
      <history-trend v-if="trendVisible" />
    </el-dialog>

    <el-dialog title="诊断报告" :visible.sync="reportDialog.visible" width="70%" top="5vh">
      <div v-if="reportDialog.report" class="report-content">
        <el-descriptions title="基本信息" :column="3" border size="small" style="margin-bottom: 20px">
          <el-descriptions-item label="任务ID">{{ reportDialog.report.product_info.serial }}</el-descriptions-item>
          <el-descriptions-item label="数据文件">{{ reportDialog.report.product_info.file_name }}</el-descriptions-item>
          <el-descriptions-item label="诊断日期">{{ reportDialog.report.product_info.diag_date }}</el-descriptions-item>
          <el-descriptions-item label="操作员">{{ reportDialog.report.product_info.operator }}</el-descriptions-item>
          <el-descriptions-item label="诊断结果">
            <el-tag :type="RESULT_TAG[reportDialog.report.result]" size="small">{{ resultLabel(reportDialog.report.result) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="试验工况">{{ (reportDialog.report.condition || {}).label || '—' }}</el-descriptions-item>
          <el-descriptions-item label="结论" :span="3">{{ reportDialog.report.summary || '—' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">原因分析</div>
        <cause-list :causes="reportDialog.report.causes || []" :history="reportDialog.report.history" style="margin-bottom: 20px" />

        <template v-if="shownFindings.length">
          <div class="section-title">检查项</div>
          <el-table :data="shownFindings" border size="small" style="margin-bottom: 20px">
            <el-table-column label="级别" width="70">
              <template slot-scope="{ row }">
                <el-tag :type="SEVERITY_TAG[row.severity]" size="mini">{{ SEVERITY_LABELS[row.severity] }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="问题" width="160" />
            <el-table-column prop="label" label="对象" width="140" />
            <el-table-column prop="detail" label="说明" />
          </el-table>
        </template>

        <template v-if="reportDialog.report.model">
          <div class="section-title">仿真模型对比</div>
          <model-compare :model="reportDialog.report.model" style="margin-bottom: 20px" />
        </template>

        <div class="section-title">检测明细</div>
        <el-table :data="reportDialog.report.indicators" border size="small" style="margin-bottom: 20px">
          <el-table-column prop="name" label="项目" />
          <el-table-column prop="reference" label="判定标准 / 来源" />
          <el-table-column label="结果">
            <template slot-scope="{ row }">
              <span :class="{ 'abnormal-value': row.abnormal }">{{ row.value }}</span>
            </template>
          </el-table-column>
        </el-table>

        <div class="section-title">处理建议</div>
        <el-card shadow="never" class="advice">{{ reportDialog.report.repair_advice }}</el-card>
        <div v-if="reportDialog.report.algorithm" class="algo-note">
          诊断算法 {{ reportDialog.report.algorithm.version }}，
          {{ reportDialog.report.algorithm.baseline ? `健康基准：${reportDialog.report.algorithm.baseline.source}` : '未使用健康基准' }}
        </div>
      </div>
      <div v-else class="loading-text">加载中...</div>
      <span slot="footer">
        <el-button @click="reportDialog.visible = false">关闭</el-button>
        <el-button type="primary" :disabled="!reportDialog.row" @click="download(reportDialog.row)">下载报告</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script>
import { deleteTasks, downloadReport, getReport, listTasks } from '@/api/tasks'
import { RESULT_TAG, SEVERITY_LABELS, resultLabel } from '@/utils/report'
import CauseList from '@/components/CauseList'
import ModelCompare from '@/components/ModelCompare'
import HistoryTrend from './HistoryTrend'

const STATUS_LABELS = { Created: '待诊断', Completed: '已完成', Failed: '失败' }
const MODE_LABELS = { auto: '自动诊断', realtime: '实时监控', file: '选择文件' }
const SEVERITY_TAG = { info: 'info', notice: 'info', warning: 'warning', abnormal: 'danger' }
const REFRESH_INTERVAL_MS = 10000
const DAY_MS = 24 * 3600 * 1000

export default {
  name: 'Tasks',
  components: { CauseList, HistoryTrend, ModelCompare },
  data() {
    return {
      STATUS_LABELS,
      MODE_LABELS,
      RESULT_TAG,
      SEVERITY_LABELS,
      SEVERITY_TAG,
      filters: { keyword: '', status: '', dateRange: null },
      tasks: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      selected: [],
      reportDialog: { visible: false, report: null, row: null },
      trendVisible: false
    }
  },
  computed: {
    /** 报告中需要展示的发现（不含“提示”级别） */
    shownFindings() {
      const report = this.reportDialog.report
      return ((report && report.findings) || []).filter(f => f.severity !== 'info')
    }
  },
  created() {
    this.load()
  },
  mounted() {
    this.startRefresh()
  },
  beforeDestroy() {
    clearInterval(this.refreshTimer)
  },
  methods: {
    resultLabel,
    startRefresh() {
      clearInterval(this.refreshTimer)
      // 定时刷新当前页，及时看到自动诊断产生的新任务
      this.refreshTimer = setInterval(() => this.load(true), REFRESH_INTERVAL_MS)
    },
    async load(quiet = false) {
      const params = { page: this.page, page_size: this.pageSize, keyword: this.filters.keyword, status: this.filters.status }
      if (this.filters.dateRange) {
        params.start_time = this.filters.dateRange[0]
        params.end_time = this.filters.dateRange[1] + DAY_MS // 包含结束日期当天
      }
      if (!quiet) this.loading = true
      try {
        const { items, total } = await listTasks(params)
        this.tasks = items
        this.total = total
      } catch (e) {
        // 提示已由请求拦截器显示
      } finally {
        this.loading = false
      }
    },
    handleSizeChange(size) {
      this.pageSize = size
      this.search()
    },
    handlePageChange(page) {
      this.page = page
      this.load()
    },
    search() {
      this.page = 1
      this.load()
    },
    reset() {
      this.filters = { keyword: '', status: '', dateRange: null }
      this.search()
    },
    formatTime(ms) {
      if (!ms) return '-'
      const d = new Date(ms)
      const pad = n => String(n).padStart(2, '0')
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    },
    async viewReport(row) {
      this.reportDialog = { visible: true, report: null, row }
      try {
        this.reportDialog.report = await getReport(row.task_id)
      } catch (e) {
        this.reportDialog.visible = false
      }
    },
    download(row) {
      downloadReport(row.task_id).catch(() => {})
    },
    async downloadMany(rows) {
      const completed = rows.filter(r => r.status === 'Completed')
      if (!completed.length) {
        this.$message.warning('选中的任务中没有已完成的任务')
        return
      }
      for (const row of completed) {
        await downloadReport(row.task_id).catch(() => {})
      }
    },
    async removeTasks(rows) {
      try {
        await this.$confirm(`确定要删除选中的 ${rows.length} 个任务吗？`, '删除确认', { type: 'warning' })
      } catch (e) {
        return // 取消
      }
      const { deleted } = await deleteTasks(rows.map(r => r.task_id))
      this.$message.success(`已删除 ${deleted} 个任务`)
      if (this.tasks.length === rows.length && this.page > 1) this.page -= 1
      this.load()
    }
  }
}
</script>

<style lang="scss" scoped>
.box-card {
  margin-bottom: 20px;
}
.btn-row {
  margin-bottom: 15px;
  text-align: right;
}
.pagination {
  margin-top: 15px;
  text-align: right;
}
.section-title {
  font-weight: bold;
  margin-bottom: 10px;
}
.advice {
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.8;
}
.algo-note {
  margin-top: 10px;
  color: #909399;
  font-size: 12px;
}
.abnormal-value {
  color: #f56c6c;
  font-weight: bold;
}
.loading-text {
  text-align: center;
  padding: 40px;
  color: #999;
}
</style>
