<template>
  <div class="task-create">
    <el-overlay v-if="isSubmitting" class="full-screen-loading">
      <div class="loading-content">
        <i class="el-icon-loading loading-icon"></i>
        <p class="loading-text">任务创建中，请耐心等候...</p>
      </div>
    </el-overlay>
    <el-form :model="taskForm" ref="taskForm" label-width="100px" class="task-form">
      <!-- 任务基本信息部分 -->
      <p class="section-title">创建任务</p>
      <el-row :gutter="20">
        <!-- 任务名称 -->
        <el-col>
          <el-form-item label="任务名称" :rules="[
            { required: true, message: '请输入任务名称', trigger: 'blur' },
          ]">
            <el-input v-model="taskForm.name" placeholder="请输入任务名称"></el-input>
          </el-form-item>
        </el-col>
      </el-row>

      <!-- 故障诊断 -->
      <el-form-item label="故障诊断" :rules="[
        { required: true, message: '请选择故障诊断', trigger: 'change' },
      ]">
        <el-radio-group v-model="taskForm.fault">
          <el-radio label="1">是</el-radio>
          <el-radio label="0">否</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- 数据配置 -->
      <el-form-item label="数据配置" :rules="[
        { required: true, message: '请输入数据配置地址', trigger: 'blur' },
      ]">
        <el-input v-model="taskForm.path" placeholder="请输入数据配置地址" @input="handlePathChange"></el-input>
      </el-form-item>

      <!-- 任务内容部分 -->
      <el-form-item label="任务方式" :rules="[
        { required: true, message: '请选择任务内容', trigger: 'change' },
      ]">
        <el-radio-group v-model="taskForm.type">
          <el-radio label="0">默认</el-radio>
          <el-radio label="1">可选</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- 数据选择列表 -->
      <el-form-item v-if="taskForm.type == '1'" label="选择数据"
        :rules="[{ required: true, message: '请选择数据', trigger: 'change' }]">
        <el-checkbox-group v-model="taskForm.selectedItems">
          <div class="product-list">
            <el-checkbox v-for="item in products" :key="item" :label="item" class="product-item">
              <div class="item">
                <i class="el-icon-document product-image" style="font-size: 100px; color: #409eff"></i>
                <span class="product-name">{{ item }}</span>
              </div>
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </el-form-item>

      <!-- 提交按钮 -->
      <el-form-item>
        <el-button type="primary" :loading="isSubmitting" @click="handleSubmit">
          创建任务
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script>
import { readExcelApi, fileListAPI, storeReport, createTask } from "@/api/home";

export default {
  data() {
    return {
      taskForm: {
        name: "", // 任务名称
        endDate: "", // 结束时间
        content: "", // 任务内容
        frequency: "", // 采集频次
        selectedItems: [], // Changed from selectedItem to selectedItems for multi-select
        type: "1", //0默认，1可选
        path: "",
        fault: "1",
      },
      products: [],
      isSubmitting: false, // 控制loading状态
    };
  },
  created() {
    // this.getAllFiles();
  },
  methods: {
    handlePathChange(path) {
      fileListAPI(path).then(
        (response) => {
          console.log(response);
          this.products = response.files || [];
        },
        (error) => {
          console.log(error);
          this.products = [];
        }
      );
    },
    async handleSubmit() {
      this.isSubmitting = true; // 开启loading
      try {
        const { name, selectedItems, type, path, fault } = this.taskForm || {};

        if (path === "") {
          this.$message.error("请输入数据配置地址！");
          this.isSubmitting = false; // 关闭loading
          return;
        }

        if (type === "1" && !selectedItems.length) {
          this.$message.error("请选择数据！");
          this.isSubmitting = false; // 关闭loading
          return;
        }

        const data = {
          task_id: name,
          file_name: selectedItems.join(","), // Join selectedItems with commas
          path: path,
          type: type,
          fault: fault,
        };
        if (fault === "1" && type === "1") {
          try {
            const res = await createTask(data); // Create the task using the API
            console.log("res:", res);
          } catch (error) {
            if (fault === "1") {
              this.$message.error("任务创建失败！");
            }
            console.log(error);
            return;
          }
        }

        // console.log("res:", res);
        // if (res && res.type && res.type === "error") {
        //   this.$message.error(res.error);
        //   return;
        // }
        this.$message.success("任务创建成功！");

        // Open a new browser window with the specified parameters
        const url = `/#/?type=${encodeURIComponent(
          type
        )}&path=${encodeURIComponent(path)}&selectedItems=${encodeURIComponent(
          selectedItems.join(",")
        )}&fault=${encodeURIComponent(fault)}`;
        window.open(url, "_blank");

        if (fault === "1" && type === "1") {
          storeReport(data);
        }

        setTimeout(() => {
          this.$router.push(`/example/table`);
        }, 1000);
      } catch (error) {
        console.log(error);
        this.$message.error("任务创建失败！");
      } finally {
        this.isSubmitting = false; // 关闭loading
      }
    },
    handleRadioChange(value) {
      console.log("当前选中的单选按钮的值：", value);
      // 在这里处理选择事件
    },
  },
  watch: {},
};
</script>

<style scoped>
.task-create {
  height: 100%;
  /* Ensure the container takes full height */
  overflow-y: auto;
  /* Enable vertical scrolling if content overflows */
}

.task-form {
  padding: 20px;
  min-height: 100%;
  /* Ensure the form stretches to fill available space */
}

.task-form {
  padding: 20px;
}

.task-form .el-form-item {
  margin-bottom: 20px;
}

/* 标题样式 */
.section-title {
  font-size: 18px;
  margin-bottom: 15px;
  color: #333;
}

/* 数据列表样式 */
.product-list {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
}

.product-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: #f9f9f9;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 8px;
  /* Reduced padding */
  text-align: center;
  width: 150px;
  /* Reduced width */
  /* height: 220px; */
  box-sizing: border-box;
  transition: transform 0.3s, box-shadow 0.3s;
}

.product-item:hover {
  transform: scale(1.05);
  box-shadow: 0 5px 10px rgba(0, 0, 0, 0.2);
}

.product-image {
  width: 100px;
  /* Reduced width */
  height: 100px;
  /* Reduced height */
  object-fit: cover;
  /* 确保图片填满框且不变形 */
  margin-bottom: 8px;
  /* Reduced margin */
  border-radius: 4px;
}

.product-name {
  font-size: 12px;
  /* Reduced font size */
  color: #333;
  overflow: hidden;
  /* text-overflow: ellipsis; */
  white-space: normal;
  /* max-height: 40px; */
  max-width: 80px;
  /* Reduced max width */
}

.item {
  display: flex;
  flex-direction: column;
  margin-top: 15px;
  align-items: center;
}

.el-input {
  width: 220px;
}

.path-btn {
  margin-left: 10px;
}

/* 全屏遮罩样式 */
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
  /* 蓝色 */
}

.loading-text {
  margin-top: 10px;
  font-size: 18px;
  color: #409eff;
  /* 蓝色 */
}
</style>
