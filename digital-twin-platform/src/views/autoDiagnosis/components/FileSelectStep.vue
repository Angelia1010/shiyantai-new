<template>
  <el-card class="file-select-card" shadow="hover">
    <div slot="header" class="card-header">
      <span>选择文件</span>
      <el-button 
        type="text" 
        icon="el-icon-refresh" 
        @click="loadFiles"
        :loading="loading"
      >
        刷新
      </el-button>
    </div>

    <el-row :gutter="20">
      <el-col :span="24">
        <el-alert
          title="请选择需要进行诊断的文件"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 15px;"
        />
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="24">
        <div class="file-list-container">
          <div v-if="loading" class="loading-container">
            <i class="el-icon-loading"></i>
            <span>加载中...</span>
          </div>
          
          <div v-else-if="files.length === 0" class="empty-container">
            <i class="el-icon-folder-opened"></i>
            <p>该路径下没有可用的文件</p>
          </div>
          
          <el-checkbox-group v-else v-model="localSelectedFiles" class="file-checkbox-group">
            <el-checkbox 
              v-for="file in files" 
              :key="file" 
              :label="file"
              class="file-checkbox-item"
            >
              <div class="file-item">
                <i class="el-icon-document file-icon"></i>
                <span class="file-name">{{ file }}</span>
              </div>
            </el-checkbox>
          </el-checkbox-group>
        </div>
      </el-col>
    </el-row>

    <div class="selection-info">
      <el-tag type="info">已选择 {{ localSelectedFiles.length }} 个文件</el-tag>
    </div>

    <div class="action-bar">
      <el-button size="medium" @click="$emit('prev')">
        <i class="el-icon-arrow-left"></i>
        上一步
      </el-button>
      <el-button 
        type="primary" 
        size="medium" 
        @click="handleNext"
        :disabled="localSelectedFiles.length === 0"
      >
        开始诊断
        <i class="el-icon-arrow-right"></i>
      </el-button>
    </div>
  </el-card>
</template>

<script>
import { fileListAPI } from '@/api/home'

export default {
  name: 'FileSelectStep',
  props: {
    config: {
      type: Object,
      required: true
    },
    selectedFiles: {
      type: Array,
      default: () => []
    }
  },
  data() {
    return {
      files: [],
      loading: false
    }
  },
  computed: {
    localSelectedFiles: {
      get() {
        return this.selectedFiles
      },
      set(val) {
        this.$emit('update:selected-files', val)
      }
    }
  },
  mounted() {
    this.loadFiles()
  },
  methods: {
    async loadFiles() {
      if (!this.config.dataPath) {
        this.$message.warning('请先配置数据路径')
        return
      }
      
      this.loading = true
      try {
        const response = await fileListAPI(this.config.dataPath)
        this.files = response.files || []
      } catch (error) {
        this.$message.error('加载文件列表失败: ' + (error.message || error))
        this.files = []
      } finally {
        this.loading = false
      }
    },
    handleNext() {
      this.$emit('next')
    }
  }
}
</script>

<style scoped>
.file-select-card {
  max-height: calc(100vh - 280px);
  overflow-y: auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 16px;
  font-weight: bold;
}

.file-list-container {
  min-height: 300px;
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 10px;
}

.loading-container,
.empty-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #909399;
}

.loading-container i,
.empty-container i {
  font-size: 48px;
  margin-bottom: 10px;
}

.file-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.file-checkbox-item {
  margin: 0 !important;
  width: calc(25% - 10px);
  min-width: 200px;
}

.file-item {
  display: flex;
  align-items: center;
  padding: 10px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #fafafa;
  transition: all 0.3s;
}

.file-checkbox-item.is-checked .file-item {
  background: #ecf5ff;
  border-color: #409eff;
}

.file-icon {
  font-size: 24px;
  color: #409eff;
  margin-right: 10px;
}

.file-name {
  font-size: 13px;
  color: #606266;
  word-break: break-all;
}

.selection-info {
  margin-top: 15px;
  text-align: right;
}

.action-bar {
  margin-top: 20px;
  text-align: right;
  padding: 10px 0;
  border-top: 1px solid #ebeef5;
}

.action-bar .el-button {
  margin-left: 10px;
}
</style>
