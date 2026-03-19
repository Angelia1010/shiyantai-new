<template>
  <div class="app-container">
    <el-card class="box-card" :body-style="{ padding: '20px' }">
      <!-- 查询区域 -->
      <el-form :inline="true" :model="formData" class="demo-form-inline">
        <el-form-item label="仿真名称">
          <el-input v-model="formData.modelName" placeholder="请输入仿真名称" />
        </el-form-item>
        <el-form-item label="数据类型">
          <el-select v-model="formData.dataType" placeholder="请选择数据类型">
            <el-option v-for="item in dataTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <!-- 查询按钮 -->
      <div class="query-btn">
        <el-button size="small" @click="resetQuery">重置</el-button>
        <el-button type="primary" size="small" @click="getList">查询</el-button>
      </div>
    </el-card>

    <el-card class="box-card" :body-style="{ padding: '20px' }">
      <!-- 新增按钮 -->
      <!-- <div class="btn-row">
        <el-button type="primary" size="small" @click="addDataModel">
          新增仿真
        </el-button>
      </div> -->

      <!-- 表格 -->
      <div class="table-container">
        <el-table ref="multipleTable" :data="tableData" tooltip-effect="dark" style="width: 100%"
          height="calc(100vh - 400px)" @selection-change="handleSelectionChange" border>
          <el-table-column type="selection" width="55" />
          <el-table-column prop="modelName" label="仿真名称" width="150" />
          <el-table-column prop="dataType" label="数据类型" min-width="400">
            <template slot-scope="scope">
              <el-tag :type="getDataTypeTagType(scope.row.dataType)">
                {{ getDataTypeLabel(scope.row.dataType) }}
              </el-tag>
            </template>
          </el-table-column>
          <!-- <el-table-column label="文件路径" min-width="200">
            <template slot-scope="scope">
              <el-tooltip :content="scope.row.filePath" placement="top">
                <span class="file-path">{{ scope.row.filePath }}</span>
              </el-tooltip>
            </template>
          </el-table-column> -->

          <el-table-column label="操作" width="200" fixed="right">
            <template slot-scope="{ row }">
              <el-button size="mini" @click="viewDetail(row)">详情</el-button>
              <el-button size="mini" type="danger" @click="deleteModel(row)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 分页 -->
      <el-pagination :current-page="page.currentPage" :page-sizes="[10, 20, 50, 100]" :page-size="page.pageSize"
        layout="total, sizes, prev, pager, next, jumper" :total="page.total" @size-change="handleSizeChange"
        @current-change="handleCurrentChange" />
    </el-card>

    <!-- 仿真详情弹窗 -->
    <el-dialog title="仿真详情" :visible.sync="detailDialogVisible" width="100%" class="full-height-dialog"
      :close-on-click-modal="false">
      <div v-if="selectedModel">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="仿真名称">{{
            selectedModel.modelName
          }}</el-descriptions-item>
          <el-descriptions-item label="数据类型">
            <el-tag :type="getDataTypeTagType(selectedModel.dataType)">
              {{ getDataTypeLabel(selectedModel.dataType) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="数据文件">
            <div class="file-upload-area">
              <el-button size="mini" @click="triggerFileInput">选择Excel文件</el-button>
              <span v-if="selectedModel.filePath" class="file-name">
                {{ selectedModel.filePath }}
              </span>
              <!-- 隐藏的 input -->
              <input ref="fileInput" type="file" accept=".xlsx,.xls" style="display: none" @change="handleFileSelect" />
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="数据预览">
            <div v-if="previewData.length > 0" style="max-height: 200px; overflow: auto;">
              <el-table :data="previewData" size="mini" border style="width: 100%">
                <el-table-column
                  v-for="(col, index) in (selectedModel.dataFeatures && selectedModel.dataFeatures.columns) || []"
                  :key="index" :prop="col.name" :label="col.name" width="120">
                </el-table-column>
              </el-table>
            </div>
            <span v-else>暂无数据</span>
          </el-descriptions-item>
        </el-descriptions>
        <div style="margin-top: 15px;">
          <el-button size="mini" @click="startPlayback" :disabled="isPlaying">
            {{ isPlaying ? '播放中...' : '开始播放' }}
          </el-button>
          <el-button size="mini" @click="stopPlayback" :disabled="!isPlaying">
            停止
          </el-button>
          <el-button size="mini" @click="resetPlayback">
            重置
          </el-button>
        </div>


        <div v-if="selectedModel.analysisResult" style="margin-top: 20px">
          <h4>分析结果</h4>
          <el-card>
            <pre>{{ selectedModel.analysisResult }}</pre>
          </el-card>
        </div>

        <div v-if="selectedModel.dataFeatures" style="margin-top: 20px">
          <h4>数据特征</h4>
          <el-card>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="数据行数">{{
                selectedModel.dataFeatures.rowCount || "-"
              }}</el-descriptions-item>
              <el-descriptions-item label="数据列数">{{
                selectedModel.dataFeatures.columnCount || "-"
              }}</el-descriptions-item>
              <el-descriptions-item label="数据大小">{{
                selectedModel.dataFeatures.fileSize || "-"
              }}</el-descriptions-item>
              <el-descriptions-item label="最后修改时间">{{
                selectedModel.dataFeatures.lastModified || "-"
              }}</el-descriptions-item>
            </el-descriptions>
            <div v-if="
              selectedModel.dataFeatures.columns &&
              selectedModel.dataFeatures.columns.length > 0
            " style="margin-top: 15px">
              <h5>列信息：</h5>
              <el-tag v-for="column in selectedModel.dataFeatures.columns" :key="column.name" style="margin: 5px"
                size="small">
                {{ column.name }} ({{ column.type }})
              </el-tag>
            </div>
          </el-card>
          <!-- 图表 + 动画 并排区域 -->
          <div v-if="selectedModel" class="chart-animation-container">
            <el-row :gutter="20">
              <!-- 左侧：图表 Card -->
              <el-col :xs="24" :sm="12" :md="12" :lg="12" :xl="12">
                <h4>仿真结果图表</h4>
                <el-card class="chart-card" shadow="never">

                  <div class="chart-container">
                    <div v-for="(group, idx) in GROUPS" :key="group.name" style="margin-bottom: 20px;">
                      <div :ref="'trendChart' + idx" style="width: 100%; height: 300px;"></div>
                    </div>
                  </div>

                </el-card>
              </el-col>

              <!-- 右侧：动画 Card -->
              <el-col :xs="24" :sm="12" :md="12" :lg="12" :xl="12">
                <h4>仿真结果动画</h4>
                <el-card class="animation-card" shadow="never">

                  <div class="animation-placeholder" ref="animationContainer">
                    <!-- 使用 HTML5 video 标签播放 MP4 视频 -->
                    <video controls width="100%" preload="metadata">
                      <source :src="videoPath" type="video/mp4">
                      您的浏览器不支持HTML5视频标签。
                    </video>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </div>
      </div>

      <div slot="footer" class="dialog-footer">
        <el-button @click="closeDetail">关 闭</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import {
  fetchDataModelList,
  deleteDataModel,
  fetchDataModel,
} from "@/api/dataModel";
import * as echarts from "echarts";
import * as XLSX from 'xlsx';
export default {
  name: "DataModelList",
  data() {
    return {
      // 查询区域数据
      formData: {
        modelName: "",
        dataType: "",
      },
      // 数据类型下拉框选项
      dataTypeOptions: [
        { label: "全部", value: "" },
        { label: "仿真数据", value: "simulation" },
        { label: "涡轮流量计数据", value: "turbine_flowmeter" },
      ],
      // 分页配置
      page: {
        total: 0,
        pageSize: 20,
        currentPage: 1,
      },
      // 多选数据
      multipleSelection: [],
      // 表格数据
      tableData: [],
      // 加载状态
      listLoading: false,
      // 详情弹窗
      detailDialogVisible: false,
      selectedModel: null,
      videoPath: "./videos/涡轮流量计仿真2.mp4",
      currentFeatureMap: null, // 当前用于绘图的实时数据
      // 仿真图表
      trendCharts: [],         // 存储 ECharts 实例
      xCount: 0,
      maxLen: 20,
      dataBuffer: null,
      // 定义分组（和你第二个文件一致）
      GROUPS: [
        {
          name: "转速",
          keys: ["输入燃油泵转速"]
        },
        {
          name: "供油流量",
          keys: ["供油流量1-1", "供油流量1-2"]
        },
        {
          name: "回油流量",
          keys: ["回油流量1-1", "回油流量1-2"]
        }
      ],
      previewData: [], // 用于显示前5行
      excelDataRows: [],     // 存储解析后的所有行（每行是对象）
      currentRowIndex: 0,    // 当前播放到第几行
      playbackInterval: null, // 播放定时器
      isPlaying: false       // 是否正在播放
    };

  },
  created() {
    this.getList();
  },
  methods: {
    // 初始化所有趋势图
    initTrendCharts() {
      this.trendCharts = [];
      this.dataBuffer = this.GROUPS.map(group => group.keys.map(() => []));

      this.$nextTick(() => {
        this.GROUPS.forEach((group, idx) => {
          const refValue = this.$refs[`trendChart${idx}`];
          const chartDom = Array.isArray(refValue) ? refValue[0] : refValue;
          if (!chartDom) return;

          const chart = echarts.init(chartDom);
          chart.setOption(this.getChartOption(group, []));
          this.trendCharts.push(chart);
        });
      });
    },

    // 获取初始配置
    getChartOption(group, seriesData) {
      return {
        title: { text: group.name + "趋势", left: 'center', textStyle: { fontSize: 14 } },
        tooltip: { trigger: 'axis' },
        legend: { data: group.keys, top: 30 },
        xAxis: { type: 'value' },
        yAxis: { type: 'value' },
        series: group.keys.map((key, i) => ({
          name: key,
          type: 'line',
          smooth: true,
          data: seriesData[i] || []
        }))
      };
    },

    // 接收新数据并更新图表
    updateTrendChart(featureMap, currentTime) {
      if (!featureMap || !this.trendCharts.length) return;
      if (currentTime == null || isNaN(currentTime)) return;
      this.xCount++;
      this.GROUPS.forEach((group, gIdx) => {
        const chart = this.trendCharts[gIdx];
        if (!chart) return;

        const seriesList = group.keys.map(key => {
          const val = featureMap && featureMap[key] ? featureMap[key].avg : undefined;
          if (typeof val !== 'number') return null;

          // 更新缓冲区
          const buffer = this.dataBuffer[gIdx][group.keys.indexOf(key)];
          buffer.push([this.xCount, parseFloat(val.toFixed(3))]);
          if (buffer.length > this.maxLen) buffer.shift();

          return buffer.slice();
        }).filter(Boolean);

        // 更新图表
        chart.setOption({
          xAxis: { min: Math.max(1, this.xCount - this.maxLen + 1), max: this.xCount },
          series: group.keys.map((key, sIdx) => ({
            name: key,
            data: this.dataBuffer[gIdx][sIdx] || []
          }))
        }, false, true);
      });
    },

    // 销毁图表
    disposeTrendCharts() {
      this.trendCharts.forEach(c => {
        if (c && typeof c.dispose === 'function') {
          c.dispose();
        }
      });
      this.trendCharts = [];
    },
    /////////////////////////////////////////////////////////////////
    // 获取列表数据
    getList() {
      this.listLoading = true;

      // 模拟API调用延迟
      setTimeout(() => {
        // 模拟数据
        const mockData = [
          /* {
            id: 1,
            modelName: "泵站仿真模型A",
            dataType: "simulation",
            filePath: "D:\\data\\pump_simulation_a.xlsx",
            status: "completed",
            createdAt: "2025-10-14T10:00:00Z",
            updatedAt: "2025-10-14T10:30:00Z",
            analysisResult: "分析完成：泵站运行正常，效率98.5%",
            dataFeatures: {
              rowCount: 1250,
              columnCount: 8,
              fileSize: "2.3 MB",
              lastModified: "2025-10-14 10:00:00",
              columns: [
                { name: "时间戳", type: "datetime" },
                { name: "流量", type: "float" },
                { name: "压力", type: "float" },
                { name: "转速", type: "int" },
                { name: "温度", type: "float" },
                { name: "效率", type: "float" },
                { name: "功率", type: "float" },
                { name: "状态", type: "string" },
              ],
            },
          }, */
          {
            id: 1,
            modelName: "涡轮流量计测试数据",
            dataType: "turbine_flowmeter",
            filePath: "",
            status: "completed",
            createdAt: "2025-10-14T10:00:00Z",
            updatedAt: "",
            analysisResult: null,
            dataFeatures: {
              rowCount: null,
              columnCount: null,
              fileSize: "",
              lastModified: "",
              columns: null,
            },
          },
          /* {
            id: 3,
            modelName: "泵站性能优化模型",
            dataType: "simulation",
            filePath: "D:\\data\\pump_optimization.xlsx",
            status: "pending",
            createdAt: "2025-10-14T08:30:00Z",
            updatedAt: "2025-10-14T08:30:00Z",
            analysisResult: null,
            dataFeatures: {
              rowCount: 950,
              columnCount: 10,
              fileSize: "3.1 MB",
              lastModified: "2025-10-14 08:30:00",
              columns: [
                { name: "时间戳", type: "datetime" },
                { name: "泵站ID", type: "string" },
                { name: "流量", type: "float" },
                { name: "扬程", type: "float" },
                { name: "功率", type: "float" },
                { name: "效率", type: "float" },
                { name: "转速", type: "int" },
                { name: "温度", type: "float" },
                { name: "压力", type: "float" },
                { name: "优化建议", type: "string" },
              ],
            },
          },
          {
            id: 4,
            modelName: "流量计校准数据",
            dataType: "turbine_flowmeter",
            filePath: "D:\\data\\flowmeter_calibration.xlsx",
            status: "completed",
            createdAt: "2025-10-13T16:00:00Z",
            updatedAt: "2025-10-13T16:45:00Z",
            analysisResult: "校准完成：精度误差小于0.5%",
            dataFeatures: {
              rowCount: 500,
              columnCount: 5,
              fileSize: "1.2 MB",
              lastModified: "2025-10-13 16:00:00",
              columns: [
                { name: "标准流量", type: "float" },
                { name: "测量流量", type: "float" },
                { name: "误差", type: "float" },
                { name: "温度", type: "float" },
                { name: "压力", type: "float" },
              ],
            },
          },
          {
            id: 5,
            modelName: "多泵站协同仿真",
            dataType: "simulation",
            filePath: "D:\\data\\multi_pump_simulation.xlsx",
            status: "failed",
            createdAt: "2025-10-13T14:00:00Z",
            updatedAt: "2025-10-13T14:20:00Z",
            analysisResult: "分析失败：数据格式不正确",
            dataFeatures: {
              rowCount: 1800,
              columnCount: 12,
              fileSize: "4.5 MB",
              lastModified: "2025-10-13 14:00:00",
              columns: [
                { name: "时间戳", type: "datetime" },
                { name: "泵站1_流量", type: "float" },
                { name: "泵站1_压力", type: "float" },
                { name: "泵站2_流量", type: "float" },
                { name: "泵站2_压力", type: "float" },
                { name: "泵站3_流量", type: "float" },
                { name: "泵站3_压力", type: "float" },
                { name: "总流量", type: "float" },
                { name: "总压力", type: "float" },
                { name: "系统效率", type: "float" },
                { name: "能耗", type: "float" },
                { name: "协同状态", type: "string" },
              ],
            },
          }, */
        ];

        // 简单的筛选逻辑
        let filteredData = mockData;
        if (this.formData.modelName) {
          filteredData = filteredData.filter((item) =>
            item.modelName.includes(this.formData.modelName)
          );
        }
        if (this.formData.dataType) {
          filteredData = filteredData.filter(
            (item) => item.dataType === this.formData.dataType
          );
        }

        // 分页逻辑
        const startIndex = (this.page.currentPage - 1) * this.page.pageSize;
        const endIndex = startIndex + this.page.pageSize;
        const pageData = filteredData.slice(startIndex, endIndex);

        this.tableData = pageData;
        this.page.total = filteredData.length;
        this.listLoading = false;
      }, 500); // 模拟500ms延迟
    },

    // 重置查询条件
    resetQuery() {
      this.formData = {
        modelName: "",
        dataType: "",
      };
      this.page.currentPage = 1;
      this.getList();
    },

    // 选择表格中的复选框
    handleSelectionChange(val) {
      this.multipleSelection = val;
    },

    // 改变每页显示条数
    handleSizeChange(pageSize) {
      this.page.pageSize = pageSize;
      this.page.currentPage = 1;
      this.getList();
    },

    // 改变当前页码
    handleCurrentChange(currentPage) {
      this.page.currentPage = currentPage;
      this.getList();
    },

    // 新增数据模型
    addDataModel() {
      this.$router.push("/dataModel/create");
    },
    // 查看详情
    async viewDetail(row) {
      setTimeout(() => {
        this.selectedModel = { ...row };
        this.detailDialogVisible = true;

        // 模拟实时数据流（实际应来自 WebSocket 或轮询 API）
        this.currentFeatureMap = {}; // 初始空数据

        // 启动模拟数据更新（仅演示用）
        //this.simulateRealTimeData();

        // 初始化图表
        this.$nextTick(() => {
          this.initTrendCharts();
        });
      }, 300);
    },

    // 删除模型
    deleteModel(row) {
      this.$confirm("确认要删除此仿真吗？删除后无法恢复。", "警告", {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      }).then(() => {
        // 模拟删除操作
        setTimeout(() => {
          this.$message.success("删除成功");
          this.getList(); // 重新获取列表
        }, 500);
      });
    },

    // 获取数据类型标签样式
    getDataTypeTagType(type) {
      const typeMap = {
        simulation: "primary",
        turbine_flowmeter: "success",
      };
      return typeMap[type] || "";
    },

    // 获取数据类型标签文本
    getDataTypeLabel(type) {
      const typeMap = {
        simulation: "仿真数据",
        turbine_flowmeter: "涡轮流量计数据",
      };
      return typeMap[type] || type;
    },
    // 模拟数据
    simulateRealTimeData() {
      clearInterval(this.simulateTimer);
      this.simulateTimer = setInterval(() => {
        const mockFeature = {
          "P1进口压力": { avg: 2.0 + Math.random() * 0.5 },
          "P17滑油压力": { avg: 1.8 + Math.random() * 0.3 },
          "P2低压出口压力": { avg: 2.5 + Math.random() * 0.4 },
          "P3高压出口压力": { avg: 3.0 + Math.random() * 0.6 },
          "供油温度1-1": { avg: 45 + Math.random() * 5 },
          "供油温度1-2": { avg: 46 + Math.random() * 4 },
          "回油温度1-1": { avg: 50 + Math.random() * 3 },
          "回油温度1-2": { avg: 51 + Math.random() * 2 }
        };
        this.updateTrendChart(mockFeature);
      }, 1000); // 每秒更新一次
    },
    // 在 detailDialogVisible 的 watch 或关闭按钮中调用
    beforeDestroy() {
      clearInterval(this.simulateTimer);
      this.disposeTrendCharts();
    },
    closeDetail() {
      clearInterval(this.simulateTimer);
      this.disposeTrendCharts();
      this.detailDialogVisible = false;
      this.stopPlayback(); // 停止播放

    },
    //Excel文件选择////////////////////////////////////////////////////
    // 触发文件选择
    triggerFileInput() {
      this.$refs.fileInput.click();
    },

    // 处理文件选择
    handleFileSelect(event) {
      const file = event.target.files[0];
      if (!file) return;

      const validTypes = [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel"
      ];
      const ext = file.name.toLowerCase().split('.').pop();
      if (!validTypes.includes(file.type) && !['xlsx', 'xls'].includes(ext)) {
        this.$message.error("请选择 .xlsx 或 .xls 格式的 Excel 文件");
        this.clearFileInput();
        return;
      }

      // 显示加载状态
      this.$message.info("正在解析 Excel 文件...");

      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = new Uint8Array(e.target.result);
          const workbook = XLSX.read(data, { type: 'array' });

          // 获取第一个 sheet
          const firstSheetName = workbook.SheetNames[0];
          const worksheet = workbook.Sheets[firstSheetName];

          // 转为二维数组（含 header）
          const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 });

          if (!jsonData || jsonData.length === 0) {
            throw new Error("Excel 文件为空");
          }

          // 第一行作为列名
          const headers = jsonData[0].map((h, i) => String(h || `列${i + 1}`));
          const rows = jsonData.slice(1); // 数据行

          // 构造 dataFeatures
          const dataFeatures = {
            rowCount: rows.length,
            columnCount: headers.length,
            fileSize: (file.size / 1024).toFixed(1) + " KB",
            lastModified: new Date(file.lastModified).toLocaleString(),
            columns: headers.map(name => ({ name, type: "auto" }))
          };

          // 提取前 5 行用于预览
          const allRows = [];
          for (let i = 0; i < rows.length; i++) {
            const rowObj = {};
            headers.forEach((col, idx) => {
              let rawValue = rows[i][idx];

              // 处理 null / undefined / 空
              if (rawValue == null || rawValue === '') {
                rowObj[col] = '';
                return;
              }

              // 如果已经是 number，直接处理
              if (typeof rawValue === 'number' && !isNaN(rawValue)) {
                rowObj[col] = Math.round(rawValue * 100) / 100;
                return;
              }

              // 尝试将字符串转为数字
              if (typeof rawValue === 'string') {
                // 去除首尾空格
                const trimmed = rawValue.trim();

                // 检查是否是有效的数字字符串（支持负数、小数）
                if (trimmed !== '' && !isNaN(trimmed) && !isNaN(parseFloat(trimmed))) {
                  const num = parseFloat(trimmed);
                  // 防止 " " 或 "   " 被误判为 0
                  if (trimmed !== '' && isFinite(num)) {
                    rowObj[col] = Math.round(num * 100) / 100;
                    return;
                  }
                }
              }

              // 其他情况（非数字字符串、日期、布尔值等）保持原样
              rowObj[col] = rawValue;
            });
            allRows.push(rowObj);
          }

          // 更新模型数据
          this.selectedModel.filePath = file.name;
          //this.selectedModel.analysisResult = `已加载 "${firstSheetName}" 表格，共 ${rows.length} 行`;
          this.selectedModel.dataFeatures = dataFeatures;

          // 存储数据（用于表格和图表展示）
          this.excelDataRows = allRows;
          console.log("Excel data:", allRows);

          this.previewData = allRows.slice(0, 5);

          // 刷新图表（如果你有基于列的图表逻辑）
          this.disposeTrendCharts();
          this.initTrendCharts();

          this.$message.success(`解析成功！共 ${headers.length} 列，${rows.length} 行`);
          this.$nextTick(() => {
            this.startPlayback(); // 自动开始
          });
        } catch (error) {
          console.error("解析失败:", error);
          this.$message.error("Excel 解析失败：" + (error.message || "请检查文件格式"));
        } finally {
          this.clearFileInput();
        }
      };

      reader.onerror = () => {
        this.$message.error("文件读取失败");
        this.clearFileInput();
      };

      reader.readAsArrayBuffer(file);
    },

    // 清空 input，避免重复选择同一文件无响应
    clearFileInput() {
      this.$refs.fileInput.value = '';
    },
    //图表播放控制//////////////////////////////////////////////////////
    // 开始播放 Excel 数据
    startPlayback() {
      if (this.excelDataRows.length === 0) {
        this.$message.warning("请先选择并解析 Excel 文件");
        return;
      }

      this.isPlaying = true;
      this.currentRowIndex = 0;

      // 清除之前的模拟定时器
      clearInterval(this.simulateTimer);
      this.simulateTimer = null;

      // 启动播放
      this.playbackInterval = setInterval(() => {
        if (this.currentRowIndex >= this.excelDataRows.length) {
          this.stopPlayback();
          return;
        }

        const currentRow = this.excelDataRows[this.currentRowIndex];
        const currentTime = currentRow['时间']; // 直接取
        // 转换为 featureMap 格式：{ "输入燃油泵转速": { avg: value }, ...}
        const featureMap = {};
        this.GROUPS.forEach(group => {
          group.keys.forEach(key => {
            const value = currentRow[key];
            if (typeof value === 'number') {
              featureMap[key] = { avg: value };
            }
            // 如果 key 不存在或非数字，featureMap[key] 不会设置，图表会跳过
          });
        });

        // 更新图表
        this.updateTrendChart(featureMap, currentTime);

        this.currentRowIndex++;
      }, 1000); // 每 1000ms 播放一行
    },

    stopPlayback() {
      if (this.playbackInterval) {
        clearInterval(this.playbackInterval);
        this.playbackInterval = null;
      }
      this.isPlaying = false;
    },

    resetPlayback() {
      this.stopPlayback();
      this.currentRowIndex = 0;
      // 可选：清空图表
      this.disposeTrendCharts();
      this.initTrendCharts();
      //重置 x 轴计数器
      this.xCount = 0;

      //清空数据缓冲
      //this.dataBuffer = null;
    }



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
      width: calc(100% / 2);
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

  // ::v-deep .el-table {
  //   th {
  //     background-color: #ecf5ff;
  //   }
  // }
}

.box-card+.box-card {
  margin-top: 20px;
}

::v-deep .el-pagination {
  float: right;
  margin: 15px 0 15px 0;
}

.btn-row {
  margin-bottom: 15px;
  display: flex;
  justify-content: flex-end;
}

.query-btn {
  display: flex;
  justify-content: flex-end;
}

.table-container {
  overflow-y: auto;
}

.file-path {
  display: inline-block;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}

//详情页图表及动画
.chart-animation-container {
  margin-top: 20px;
}

.card-header {
  font-weight: bold;
  color: #333;
}

.chart-card,
.animation-card {
  height: 100%;
}

.chart-placeholder,
.animation-placeholder {
  min-height: 300px;
  /* 根据需要调整高度 */
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f9f9f9;
  border-radius: 4px;
}

.placeholder-text {
  color: #999;
  font-size: 14px;
}

.file-upload-area {
  display: flex;
  align-items: center;
  gap: 10px;
}

.file-name {
  font-size: 13px;
  color: #606266;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

<style>
/* 注意：必须是全局样式 */
.full-height-dialog .el-dialog {
  height: 100vh !important;
  /* 全屏高度 */
  margin-top: 0 !important;
  /* 消除默认上边距 */
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0;
  left: 0;
}

/* 让内容区域可滚动（推荐） */
.full-height-dialog .el-dialog__body {
  flex: 1;
  overflow: auto;
  padding: 20px;
}
</style>