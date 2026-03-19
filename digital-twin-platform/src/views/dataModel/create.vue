<template>
  <div class="data-model-create">
    <!-- 全屏加载遮罩 -->
    <el-overlay v-if="isSubmitting" class="full-screen-loading">
      <div class="loading-content">
        <i class="el-icon-loading loading-icon"></i>
        <p class="loading-text">仿真创建中，请耐心等候...</p>
      </div>
    </el-overlay>

    <el-form :model="modelForm" :rules="formRules" ref="modelForm" label-width="120px" class="model-form">
      <!-- 页面标题 -->
      <div class="page-header">
        <h2>创建仿真</h2>
        <el-button @click="goBack">返回列表</el-button>
      </div>

      <!-- 基本信息部分 -->
      <el-card class="form-section">
        <div slot="header" class="section-title">
          <span>仿真信息</span>
        </div>

        <!-- 仿真名称 -->
        <el-form-item label="仿真名称" prop="modelName">
          <el-input v-model="modelForm.modelName" placeholder="请输入仿真名称" maxlength="100" show-word-limit />
        </el-form-item>

        <!-- 数据类型 -->
        <el-form-item label="数据类型" prop="dataType">
          <el-select v-model="modelForm.dataType" placeholder="请选择数据类型" style="width: 100%">
            <el-option v-for="item in dataTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>

        <!-- Excel文件 -->
        <el-form-item label="Excel文件" prop="filePath">
          <el-input v-model="modelForm.filePath" placeholder="请选择Excel文件" readonly>
            <el-button slot="append" @click="selectFile" :loading="fileValidating">
              选择文件
            </el-button>
          </el-input>
        </el-form-item>

        <!-- 文件验证信息 -->
        <div v-if="fileInfo" class="file-info">
          <el-alert :title="fileInfo.message" :type="fileInfo.type" :closable="false" show-icon />
        </div>

        <!-- 文件预览 -->
        <div v-if="previewData && previewData.length > 0" class="file-preview">
          <h4>文件预览（前5行）</h4>
          <el-table :data="previewData.slice(0, 5)" border size="small" max-height="300">
            <el-table-column v-for="(column, index) in previewColumns" :key="index" :prop="column" :label="column"
              :width="120" show-overflow-tooltip />
          </el-table>
        </div>
      </el-card>

      <!-- 提交按钮 -->
      <div class="form-actions">
        <el-button @click="goBack">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="isSubmitting">
          创建仿真
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<script>
import { createDataModel, previewExcelData } from "@/api/dataModel";
import * as XLSX from 'xlsx';
export default {
  name: "DataModelCreate",
  data() {
    return {
      modelForm: {
        modelName: "",
        dataType: "",
        filePath: "",
      },
      selectedFile: null, // 选中的文件对象
      formRules: {
        modelName: [
          { required: true, message: "请输入仿真名称", trigger: "blur" },
          {
            min: 2,
            max: 100,
            message: "长度在 2 到 100 个字符",
            trigger: "blur",
          },
        ],
        dataType: [
          { required: true, message: "请选择数据类型", trigger: "change" },
        ],
        filePath: [
          { required: true, message: "请选择Excel文件", trigger: "change" },
        ],
      },
      dataTypeOptions: [
        { label: "仿真数据", value: "simulation" },
        { label: "涡轮流量计数据", value: "turbine_flowmeter" },
      ],
      isSubmitting: false,
      fileValidating: false,
      fileInfo: null,
      previewData: [],
      previewColumns: [],
    };
  },
  methods: {
    // 返回列表页
    goBack() {
      this.$router.push("/dataModel");
    },

    // 选择文件
    selectFile() {
      // 创建隐藏的文件输入元素
      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = ".xlsx,.xls";
      fileInput.style.display = "none";

      fileInput.onchange = (event) => {
        const file = event.target.files[0];
        if (file) {
          // 检查文件类型
          const allowedTypes = [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
          ];
          const fileExtension = file.name.toLowerCase().split(".").pop();

          if (
            !allowedTypes.includes(file.type) &&
            !["xlsx", "xls"].includes(fileExtension)
          ) {
            this.$message.error("请选择Excel文件（.xlsx或.xls格式）");
            return;
          }

          // 这里需要将文件上传到服务器或者获取文件路径
          // 由于浏览器安全限制，我们无法直接获取文件的完整路径
          // 所以这里显示文件名，并将文件对象保存起来用于后续上传
          this.selectedFile = file;
          this.modelForm.filePath = file.name;

          // 自动验证文件
          this.validateSelectedFile(file);
        }
      };

      // 触发文件选择对话框
      document.body.appendChild(fileInput);
      fileInput.click();
      document.body.removeChild(fileInput);
    },

    // 验证选中的文件
    async validateSelectedFile(file) {
      if (!file) {
        this.fileInfo = null;
        this.previewData = [];
        this.previewColumns = [];
        return;
      }

      this.fileValidating = true;
      this.fileInfo = {
        type: "info",
        message: "正在验证文件...",
      };

      try {
        // 创建FormData来上传文件进行预览
        const formData = new FormData();
        formData.append("file", file);

        // 调用预览API
        const response = await this.uploadFileForPreview(formData);

        if (response.success) {
          this.fileInfo = {
            type: "success",
            message: `文件验证成功，共 ${response.total_rows || 0} 行数据`,
          };
          this.previewData = response.preview_data || [];
          this.previewColumns = response.columns || [];
        } else {
          this.fileInfo = {
            type: "error",
            message: response.message || "文件验证失败",
          };
          this.previewData = [];
          this.previewColumns = [];
        }
      } catch (error) {
        this.fileInfo = {
          type: "error",
          message: "文件验证失败，请重试",
        };
        this.previewData = [];
        this.previewColumns = [];
      } finally {
        this.fileValidating = false;
      }
    },

    // 上传文件进行预览
    async uploadFileForPreview(formData) {
      // 这里应该调用实际的API来预览文件
      // 暂时返回模拟数据
      return new Promise((resolve) => {
        setTimeout(() => {
          resolve({
            success: true,
            total_rows: 100,
            preview_data: [
              { 列1: "数据1", 列2: "数据2", 列3: "数据3" },
              { 列1: "数据4", 列2: "数据5", 列3: "数据6" },
            ],
            columns: ["列1", "列2", "列3"],
          });
        }, 1000);
      });
    },

    // 提交表单
    handleSubmit() {
      this.$refs.modelForm.validate(async (valid) => {
        if (!valid) {
          return false;
        }

        // 检查是否选择了文件
        if (!this.selectedFile) {
          this.$message.error("请选择Excel文件");
          return;
        }

        this.isSubmitting = true;

        try {
          // 模拟API调用，返回假数据
          console.log("提交仿真数据:", {
            modelName: this.modelForm.modelName,
            dataType: this.modelForm.dataType,
            fileName: this.selectedFile.name,
            fileSize: this.selectedFile.size,
          });

          // 模拟网络延迟
          await new Promise((resolve) => setTimeout(resolve, 2000));

          // 返回假的成功响应
          const mockResponse = {
            success: true,
            data: {
              id: Date.now(),
              modelName: this.modelForm.modelName,
              dataType: this.modelForm.dataType,
              filePath: `mock_path/${this.selectedFile.name}`,
              status: "pending",
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            },
          };

          console.log("模拟API响应:", mockResponse);

          this.$message.success("仿真创建成功！");

          // 延迟跳转到列表页
          setTimeout(() => {
            this.goBack();
          }, 1500);
        } catch (error) {
          console.error("创建失败:", error);
          this.$message.error(error.message || "创建仿真失败，请重试");
        } finally {
          this.isSubmitting = false;
        }
      });
    },
  },
};
</script>

<style scoped lang="scss">
.data-model-create {
  height: 100%;
  overflow-y: auto;
  background: #f5f5f5;
}

.model-form {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;

  h2 {
    margin: 0;
    color: #333;
  }
}

.form-section {
  margin-bottom: 20px;

  .section-title {
    font-weight: bold;
    color: #333;
  }
}

.field-tip {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.file-info {
  margin-top: 8px;
}

.file-preview {
  margin-top: 20px;

  h4 {
    margin-bottom: 10px;
    color: #333;
  }
}

.form-actions {
  text-align: center;
  margin-top: 30px;

  .el-button {
    width: 120px;
    margin: 0 10px;
  }
}

/* 全屏加载遮罩样式 */
.full-screen-loading {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
}

.loading-content {
  text-align: center;
}

.loading-icon {
  font-size: 50px;
  color: #409eff;
}

.loading-text {
  margin-top: 10px;
  font-size: 18px;
  color: #409eff;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .model-form {
    padding: 10px;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}
</style>
