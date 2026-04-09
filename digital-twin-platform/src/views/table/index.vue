<template>
  <div class="app-container">
    <el-card class="box-card" :body-style="{ padding: '20px' }">
      <!-- 查询区域 -->
      <el-form :inline="true" :model="formData" class="demo-form-inline">
        <el-form-item label="任务ID">
          <el-input v-model="formData.nameOrCode" placeholder="请输入任务ID" />
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
        <el-form-item label="任务时间">
          <el-date-picker
            v-model="formData.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="timestamp"
          />
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
        <el-button 
          v-if="selectedTasks.length > 0"
          type="danger" 
          size="small" 
          @click="batchDelete"
        >批量删除 ({{ selectedTasks.length }})</el-button>
        <el-button 
          v-if="selectedTasks.length > 0"
          type="success" 
          size="small" 
          @click="batchDownload"
        >批量下载 ({{ selectedTasks.length }})</el-button>
        <el-button type="primary" size="small" @click="addTask"
          >添加任务</el-button
        >
      </div>
      <!-- 表格 -->
      <div class="table-container">
        <el-table
          ref="multipleTable"
          :data="groupedTableData"
          tooltip-effect="dark"
          style="width: 100%"
          height="calc(100vh - 400px)"
          @expand-change="handleExpandChange"
          border
          row-key="groupKey"
        >
          <el-table-column type="expand">
            <template slot-scope="props">
              <el-table
                :ref="'subTable_' + props.row.groupKey"
                :data="props.row.originalTasks"
                border
                style="margin: 10px 0"
                row-key="task_id"
                @selection-change="(val) => handleSubSelectionChange(val, props.row)"
              >
                <el-table-column type="selection" width="55" :reserve-selection="true" />
                <el-table-column prop="task_id" label="任务ID" width="180" />
                <el-table-column label="创建时间" width="180">
                  <template slot-scope="scope">{{ formatTimestamp(scope.row.create_time || getTaskCreateTime(scope.row.task_id)) }}</template>
                </el-table-column>
                <el-table-column
                  label="任务方式"
                  width="80px"
                >
                  <template slot-scope="scope">{{
                    scope.row.type === "0" ? "默认" : "可选"
                  }}</template>
                </el-table-column>
                <el-table-column label="文件名">
                  <template slot-scope="scope">
                    <div v-for="(file, index) in getUniqueFileNames(scope.row.files)" :key="index">
                      {{ file }}
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="100">
                  <template slot-scope="scope">
                    <el-tag v-if="scope.row.status === 'Completed'" type="success" size="small">已完成</el-tag>
                    <el-tag v-else type="warning" size="small">诊断中</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="220">
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
            </template>
          </el-table-column>
          
          <el-table-column label="创建时间" width="180">
            <template slot-scope="scope">
              <div style="font-weight: 500">{{ formatTimestampToHour(scope.row.createTime) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="任务数量" width="120">
            <template slot-scope="scope">
              <el-tag v-if="scope.row.taskCount > 1" type="info" size="medium">
                {{ scope.row.taskCount }} 个任务
              </el-tag>
              <el-tag v-else type="success" size="medium">单个任务</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="完成状态" width="120">
            <template slot-scope="scope">
              <el-tag v-if="scope.row.status === 'Completed'" type="success" size="small">已完成</el-tag>
              <el-tag v-else type="warning" size="small">进行中</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="工作目录">
            <template slot-scope="scope">{{ scope.row.path }}</template>
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
            <el-table-column prop="reference" label="类型" />
            <el-table-column prop="value" label="指标值" />
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
        dateRange: null,
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
      // 记录选中的单个任务
      selectedTasks: [],
      // 按组记录子表格选中状态（跨展开/收起持久化）
      subSelections: {},
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
  computed: {
    groupedTableData() {
      const groups = {};
      
      this.tableData.forEach(task => {
        let createTime = task.create_time;
        
        if (!createTime) {
          const taskId = task.task_id || '';
          const timestampPart = taskId.substring(0, 13);
          if (/^\d{13}$/.test(timestampPart)) {
            createTime = parseInt(timestampPart);
          } else {
            createTime = Date.now();
          }
        }
        
        const groupKey = this.getGroupKey(createTime);
        
        if (!groupKey) {
          const uniqueKey = `single_${task.task_id}`;
          groups[uniqueKey] = {
            groupKey: uniqueKey,
            task_id: task.task_id,
            type: task.type,
            path: task.path,
            files: task.files,
            status: task.status,
            createTime: createTime,
            taskCount: 1,
            originalTasks: [task]
          };
          return;
        }
        
        if (!groups[groupKey]) {
          groups[groupKey] = {
            groupKey: groupKey,
            task_id: task.task_id,
            type: task.type,
            path: task.path,
            files: task.files,
            status: task.status,
            createTime: createTime,
            taskCount: 1,
            originalTasks: [task]
          };
        } else {
          groups[groupKey].taskCount++;
          groups[groupKey].originalTasks.push(task);
          if (task.status === 'Completed') {
            groups[groupKey].status = 'Completed';
          }
        }
      });
      
      return Object.values(groups).sort((a, b) => b.createTime - a.createTime);
    }
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
      
      if (this.formData.dateRange && this.formData.dateRange.length === 2) {
        req.startTime = this.formData.dateRange[0];
        req.endTime = this.formData.dateRange[1];
      }
      
      fetchList(req).then((response) => {
        this.tableData = response.tasks;
        this.page.total = response.total_count;
        this.listLoading = false;
        
        const allTaskIds = new Set(response.tasks.map(task => task.task_id));
        const remainingSelectedTasks = this.selectedTasks.filter(task => allTaskIds.has(task.task_id));
        
        const newSubSelections = {};
        Object.keys(this.subSelections).forEach(groupKey => {
          newSubSelections[groupKey] = (this.subSelections[groupKey] || []).filter(
            taskId => allTaskIds.has(taskId)
          );
        });
        
        this.selectedTasks = remainingSelectedTasks;
        this.subSelections = newSubSelections;
        
        this.$nextTick(() => {
          this.restoreSelectionState();
        });
      });
    },
    // 选择表格中的复选框触发的函数
    handleSelectionChange(val) {
      this.multipleSelection = val;
    },
    // 恢复选中状态
    restoreSelectionState() {
      this.syncAllCheckboxStates();
    },
    // 同步已展开的子表格选中状态
    syncExpandedSubTables() {
      this.syncAllCheckboxStates();
    },
    // 获取子表格引用
    getSubTableRef(groupKey) {
      const refName = 'subTable_' + groupKey;
      const refValue = this.$refs[refName];
      if (refValue) {
        return Array.isArray(refValue) ? refValue[0] : refValue;
      }
      return null;
    },
    // 统一同步所有复选框状态（主表格 + 已展开的子表格）
    syncAllCheckboxStates() {
      const mainTable = this.$refs.multipleTable;
      if (!mainTable) return;

      this.groupedTableData.forEach(group => {
        const groupKey = group.groupKey;
        const subSelected = this.subSelections[groupKey] || [];
        const selectedCount = subSelected.length;
        const totalCount = group.originalTasks.length;

        const isCurrentlySelected = mainTable.selection.some(row => row.groupKey === groupKey);
        const shouldBeSelected = selectedCount === totalCount && totalCount > 0;
        const isIndeterminate = selectedCount > 0 && selectedCount < totalCount;

        if (shouldBeSelected && !isCurrentlySelected) {
          mainTable.toggleRowSelection(group, true);
        } else if (!shouldBeSelected && isCurrentlySelected) {
          mainTable.toggleRowSelection(group, false);
        }

        this.$nextTick(() => {
          this.setGroupIndeterminate(group, isIndeterminate);
        });

        const subTableRef = this.getSubTableRef(groupKey);
        if (subTableRef) {
          const selectedIds = new Set(subSelected);
          group.originalTasks.forEach(task => {
            const isTaskSelected = selectedIds.has(task.task_id);
            const isCurrentlyTaskSelected = subTableRef.selection.some(
              row => row.task_id === task.task_id
            );
            if (isTaskSelected !== isCurrentlyTaskSelected) {
              subTableRef.toggleRowSelection(task, isTaskSelected);
            }
          });
        }
      });

      this.multipleSelection = mainTable.selection;
    },
    // 子表格选择变化
    handleSubSelectionChange(val, group) {
      const groupKey = group.groupKey;
      this.subSelections[groupKey] = val.map(t => t.task_id);
      this.rebuildSelectedTasks();

      const selectedCount = val.length;
      const totalCount = group.originalTasks.length;
      const mainTable = this.$refs.multipleTable;

      if (selectedCount === totalCount && totalCount > 0) {
        if (!mainTable.selection.find(row => row.groupKey === groupKey)) {
          mainTable.toggleRowSelection(group, true);
        }
        this.setGroupIndeterminate(group, false);
      } else if (selectedCount > 0) {
        const isCurrentlyChecked = mainTable.selection.some(row => row.groupKey === groupKey);
        if (isCurrentlyChecked) {
          mainTable.toggleRowSelection(group, false);
        }
        this.$nextTick(() => {
          this.setGroupIndeterminate(group, true);
        });
      } else {
        mainTable.toggleRowSelection(group, false);
        this.setGroupIndeterminate(group, false);
      }

      this.multipleSelection = mainTable.selection;
    },
    // 从 subSelections 重建 selectedTasks
    rebuildSelectedTasks() {
      const taskMap = {};
      this.groupedTableData.forEach(group => {
        const selectedIds = new Set(this.subSelections[group.groupKey] || []);
        group.originalTasks.forEach(task => {
          if (selectedIds.has(task.task_id)) {
            taskMap[task.task_id] = task;
          }
        });
      });
      this.selectedTasks = Object.values(taskMap);
    },
    // 设置聚合行复选框的 indeterminate 状态
    setGroupIndeterminate(group, indeterminate) {
      this.$nextTick(() => {
        const mainTable = this.$refs.multipleTable;
        if (!mainTable) return;
        const tableBody = mainTable.$el.querySelector('.el-table__body-wrapper');
        if (!tableBody) return;
        const rows = tableBody.querySelectorAll('.el-table__row');
        for (const row of rows) {
          const rowKey = row.getAttribute('data-row-key');
          if (rowKey === String(group.groupKey) || rowKey === group.groupKey) {
            const checkbox = row.querySelector('.el-checkbox');
            if (checkbox) {
              const checkboxInput = checkbox.querySelector('input[type="checkbox"]');
              if (checkboxInput) {
                checkboxInput.indeterminate = indeterminate;
              }
            }
            break;
          }
        }
      });
    },
    // 展开/收起变化处理
    handleExpandChange(row, expandedRows) {
      this.$nextTick(() => {
        this.syncAllCheckboxStates();
      });
    },
    // 恢复单个子表格的选中状态
    restoreSubTableSelection(group) {
      const groupKey = group.groupKey;
      const selectedIds = new Set(this.subSelections[groupKey] || []);
      const subTableRef = this.getSubTableRef(groupKey);

      if (subTableRef) {
        group.originalTasks.forEach(task => {
          subTableRef.toggleRowSelection(task, selectedIds.has(task.task_id));
        });
      }
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
      this.formData = {
        nameOrCode: "",
        status: "",
        dateRange: null,
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
    getFileName(filePath) {
      if (!filePath) return '';
      const parts = filePath.split(/[/\\]/);
      return parts[parts.length - 1] || filePath;
    },
    getUniqueFileNames(files) {
      if (!files) return [];
      const fileArray = files.split(',');
      const uniqueNames = [...new Set(fileArray.map(file => this.getFileName(file)))];
      return uniqueNames;
    },
    getGroupKey(timestamp) {
      if (!timestamp) return null;
      const date = new Date(timestamp);
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hour = String(date.getHours()).padStart(2, '0');
      return `${year}-${month}-${day} ${hour}:00`;
    },
    formatTimestampToHour(timestamp) {
      if (!timestamp) return '-';
      const date = new Date(timestamp);
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hour = String(date.getHours()).padStart(2, '0');
      return `${year}-${month}-${day} ${hour}:00`;
    },
    getTaskCreateTime(taskId) {
      if (!taskId) return Date.now();
      const timestampPart = taskId.substring(0, 13);
      if (/^\d{13}$/.test(timestampPart)) {
        return parseInt(timestampPart);
      }
      return Date.now();
    },
    formatTimestamp(timestamp) {
      if (!timestamp) return '-';
      const date = new Date(timestamp);
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      const seconds = String(date.getSeconds()).padStart(2, '0');
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    },
    batchDelete() {
      if (this.selectedTasks.length === 0) {
        this.$message.warning('请先选择要删除的任务');
        return;
      }
      
      this.$confirm(`确定要删除选中的 ${this.selectedTasks.length} 个任务吗？`, '批量删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        const deletePromises = this.selectedTasks.map(task => 
          deleteJob(task.task_id)
        );
        
        Promise.all(deletePromises)
          .then(() => {
            this.$message.success('批量删除成功！');
            this.$refs.multipleTable.clearSelection();
            this.selectedTasks = [];
            this.subSelections = {};
            this.getList();
          })
          .catch((error) => {
            this.$message.error('部分任务删除失败');
            this.getList();
          });
      }).catch(() => {});
    },
    batchDownload() {
      if (this.selectedTasks.length === 0) {
        this.$message.warning('请先选择要下载的任务');
        return;
      }
      
      const completedTasks = this.selectedTasks.filter(
        task => task.status === 'Completed'
      );
      
      if (completedTasks.length === 0) {
        this.$message.warning('选中的任务中没有已完成的任务可下载');
        return;
      }
      
      this.$message.success(`开始下载 ${completedTasks.length} 个任务报告`);
      
      completedTasks.forEach((task, index) => {
        setTimeout(() => {
          const iframe = document.createElement('iframe');
          iframe.style.display = 'none';
          iframe.src = `/db/retrieve_report/${task.task_id}`;
          document.body.appendChild(iframe);
          setTimeout(() => {
            document.body.removeChild(iframe);
          }, 60000);
        }, index * 1000);
      });
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
::v-deep .el-table__expanded-cell {
  padding: 10px 20px;
  background-color: #f5f7fa;
}
::v-deep .el-table__expanded-cell:hover {
  background-color: #f5f7fa !important;
}
</style>
