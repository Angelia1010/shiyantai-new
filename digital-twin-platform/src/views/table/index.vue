<template>
  <div class="app-container">
    <el-card class="box-card" :body-style="{ padding: '20px' }">
      <!-- 查询区域 -->
      <el-form :inline="true" :model="formData" class="demo-form-inline">
        <el-form-item label="任务名称">
          <el-input v-model="formData.nameOrCode" placeholder="请输入名称" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="formData.status" placeholder="请选择状态">
            <el-option
              v-for="item in optionList"
              :key="item.id"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <!-- 查询按钮 -->
      <div class="query-btn">
        <el-button size="small" @click="cancel">重置</el-button>
        <el-button type="primary" size="small" @click="getList">查询</el-button>
      </div>
    </el-card>

    <el-card class="box-card" :body-style="{ padding: '20px' }">
      <!-- 下载和添加任务按钮 -->
      <div class="btn-row">
        <el-button type="primary" size="small" @click="addTask"
          >添加任务</el-button
        >
      </div>
      <!-- 表格 -->
      <div class="table-container">
        <el-table
          ref="multipleTable"
          :data="tableData"
          tooltip-effect="dark"
          style="width: 100%"
          height="calc(100vh - 400px)"
          @selection-change="handleSelectionChange"
          border
        >
          <el-table-column type="selection" width="55" />
          <el-table-column prop="task_id" label="名称" width="120" />
          <el-table-column
            label="任务方式"
            width="60px"
            :header-cell-style="{ 'max-width': '60px' }"
            :cell-style="{ 'max-width': '60px' }"
          >
            <template slot-scope="scope">{{
              scope.row.type === "0" ? "默认" : "可选"
            }}</template>
          </el-table-column>
          <el-table-column label="工作目录">
            <template slot-scope="scope">{{ scope.row.path }}</template>
          </el-table-column>
          <el-table-column label="文件名">
            <template slot-scope="scope">
              <div v-for="file in scope.row.files.split(',')" :key="file">
                {{ file }}
              </div>
            </template>
          </el-table-column>

          <el-table-column label="操作">
            <template slot-scope="{ row }">
              <el-button size="mini" @click="deleteJob(row)">删除</el-button>
              <template v-if="row.status === 'Completed'">
                <el-button size="mini" @click="download(row)">下载</el-button>
                <el-button size="mini" type="primary" @click="viewReport(row)">查看</el-button>
              </template>
              <el-button v-else size="mini" disabled>诊断中</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

    <!-- 诊断报告预览弹窗 -->
    <el-dialog
      title="诊断报告"
      :visible.sync="reportDialog.visible"
      width="70%"
      top="5vh"
    >
      <div v-if="reportDialog.data" class="report-content">
        <!-- 产品信息 -->
        <el-descriptions title="基本信息" :column="3" border size="small" style="margin-bottom:20px">
          <el-descriptions-item label="报告名称">{{ reportDialog.data.product_info.name }}</el-descriptions-item>
          <el-descriptions-item label="诊断日期">{{ reportDialog.data.product_info.diag_date }}</el-descriptions-item>
          <el-descriptions-item label="操作员">{{ reportDialog.data.product_info.operator }}</el-descriptions-item>
        </el-descriptions>

        <!-- 指标表格 -->
        <div style="margin-bottom:20px">
          <div class="section-title">诊断指标</div>
          <el-table :data="reportDialog.data.indicators" border size="small">
            <el-table-column prop="name" label="指标名称" />
            <el-table-column prop="reference" label="参考值" />
            <el-table-column prop="value" label="实测值" />
          </el-table>
        </div>

        <!-- 诊断结论 -->
        <div style="margin-bottom:20px">
          <div class="section-title">诊断结论</div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="故障类型">{{ reportDialog.data.diagnosis.fault_name }}</el-descriptions-item>
            <el-descriptions-item label="位置">{{ reportDialog.data.diagnosis.location }}</el-descriptions-item>
            <el-descriptions-item label="分析说明">{{ reportDialog.data.diagnosis.analysis }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 维修建议 -->
        <div>
          <div class="section-title">维修建议</div>
          <el-card shadow="never" style="white-space:pre-wrap;font-size:13px;line-height:1.8">{{ reportDialog.data.repair_advice }}</el-card>
        </div>
      </div>
      <div v-else style="text-align:center;padding:40px;color:#999">加载中...</div>
      <span slot="footer">
        <el-button @click="reportDialog.visible = false">关闭</el-button>
        <el-button type="primary" @click="download(reportDialog.row)">下载报告</el-button>
      </span>
    </el-dialog>
      <!-- 分页 -->
      <el-pagination
        :current-page="page.currentPage"
        :page-sizes="[100, 200, 300, 400]"
        :page-size="page.pageSize"
        layout="total, sizes, prev, pager, next, jumper"
        :total="page.total"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </el-card>
  </div>
</template>

<script>
import {
  fetchList,
  downloadFile,
  stopJob,
  startJob,
  deleteJob,
  fetchReportPreview,
} from "@/api/article";
export default {
  data() {
    return {
      // 查询区域数据
      formData: {
        nameOrCode: "",
        status: "",
      },
      // 状态下拉框狂数据
      optionList: [
        {
          id: 0,
          label: "全部",
          value: "",
        },
        {
          id: 1,
          label: "未运行",
          value: "Stop",
        },
        {
          id: 2,
          label: "运行中",
          value: "Pending",
        },
      ],
      // 保存页码和每页多少条
      page: {
        total: 0,
        pageSize: 100,
        currentPage: 1,
      },
      // 记录多选的数据
      multipleSelection: [],
      // 表格数据
      tableData: [],
      // 诊断报告弹窗
      reportDialog: {
        visible: false,
        data: null,
        row: null,
      },
    };
  },
  created() {
    this.getList();
  },
  mounted() {
    this.startAutoRefresh();
  },
  deactivated() {
    console.log("Component deactivated, interval cleared.");
    clearInterval(this.refreshInterval);
  },
  destroyed() {
    console.log("Component destroyed, interval cleared.");
    clearInterval(this.refreshInterval);
  },
  methods: {
    getList() {
      this.listLoading = true;
      const req = {
        nameOrCode: this.formData.nameOrCode,
        status: this.formData.status,
        page: this.page.currentPage,
        pageSize: this.page.pageSize,
      };
      fetchList(req).then((response) => {
        this.tableData = response.tasks;
        this.page.total = response.total_count;
        this.listLoading = false;
      });
    },
    // 选择表格中的复选框触发的函数
    handleSelectionChange(val) {
      this.multipleSelection = val;
    },
    // 下载
    download(row) {
      downloadFile(row.task_id);
    },
    // 查看诊断报告
    viewReport(row) {
      this.reportDialog.visible = true;
      this.reportDialog.data = null;
      this.reportDialog.row = row;
      fetchReportPreview(row.task_id)
        .then((res) => {
          this.reportDialog.data = res;
        })
        .catch(() => {
          this.$message.error("获取诊断报告失败");
          this.reportDialog.visible = false;
        });
    },
    // 改变每页多少条的时候触发
    handleSizeChange(pageSize) {
      this.page = {
        ...this.page,
        pageSize: pageSize,
      };
      // 调获取列表接口
      this.getTableList();
    },
    // 查看当前第几页数的时候触发
    handleCurrentChange(currentPage) {
      this.page = {
        ...this.page,
        currentPage: currentPage,
      };
      // 调获取列表接口
      this.getTableList();
    },
    // 获取列表接口
    getTableList() {},
    // 取消
    cancel() {
      // 清空查询区域数据
      this.formData = {
        ...this.formDat,
        nameOrCode: "",
        status: "",
        dateVal: "",
        dateVal2: "",
      };
    },
    // 确定
    confirm() {
      // 调用获取列表接口
      this.getList();
    },
    addTask() {
      this.$router.push(`/example/tree`);
    },
    stopJob(row) {
      stopJob(row.task_id)
        .then((response) => {
          this.$message.success("任务已停止！");
          this.getList();
        })
        .catch((error) => {
          this.$message.success("任务停止失败！");
        });
    },
    startJob(row) {
      startJob(row.task_id)
        .then((response) => {
          this.$message.success("任务已启动！");
          this.getList();
        })
        .catch((error) => {
          this.$message.error(error);
        });
    },
    deleteJob(row) {
      deleteJob(row.task_id)
        .then((response) => {
          this.$message.success("任务已删除！");
          this.getList();
        })
        .catch((error) => {
          this.$message.error(error);
        });
    },
    startAutoRefresh() {
      clearInterval(this.refreshInterval);
      this.refreshInterval = setInterval(() => {
        this.getList();
      }, 5000);
    },
  },
};
</script>
<style lang="scss" scoped>
.box-card {
  width: 100%;
  ::v-deep .el-form {
    .el-form-item {
      margin-right: 0;
      margin-bottom: 0;
      width: calc(100% / 3);
      margin-bottom: 15px;
      .el-form-item__label {
        width: 80px;
      }
      .el-form-item__content {
        width: calc(100% - 120px);
        max-width: 300px;

        .el-select,
        .el-date-editor {
          width: 100%;
        }
      }
    }
  }
  ::v-deep .el-table {
    // border: 1px solid #ebeef5;
    // padding: 20px;
    th {
      background-color: #ecf5ff;
    }
  }
}
.box-card + .box-card {
  margin-top: 20px;
}
::v-deep .el-pagination {
  float: right;
  margin: 15px 0 15px 0;
}
.btn-row {
  margin-bottom: 15px;
  display: flex;
  justify-content: flex-end; // Align the button to the right
}
.query-btn {
  display: flex;
  justify-content: flex-end;
}
.table-container {
  overflow-y: auto; // Ensure vertical scrolling
}
.section-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid #409eff;
}
.report-content {
  max-height: 70vh;
  overflow-y: auto;
  padding-right: 8px;
}
</style>
