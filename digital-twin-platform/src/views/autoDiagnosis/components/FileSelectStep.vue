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
        <div class="search-container">
          <el-input
            v-model="searchKeyword"
            placeholder="请输入文件名称进行搜索"
            prefix-icon="el-icon-search"
            clearable
            @input="handleSearch"
          >
          </el-input>
        </div>
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
          
          <div v-else-if="filteredFiles.length === 0" class="empty-container">
            <i class="el-icon-search"></i>
            <p>未找到匹配的文件</p>
          </div>
          
          <el-radio-group v-else v-model="localSelectedFile" class="file-radio-group">
            <el-radio
              v-for="file in filteredFiles"
              :key="file"
              :label="file"
              class="file-radio-item"
            >
              <i class="el-icon-document file-icon"></i>
              <span class="file-name" v-html="highlightText(file)"></span>
            </el-radio>
          </el-radio-group>
        </div>
      </el-col>
    </el-row>

    <div class="selection-info">
      <el-tag type="info">已选择 {{ localSelectedFile ? 1 : 0 }} 个文件</el-tag>
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
        :disabled="!localSelectedFile"
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
      loading: false,
      searchKeyword: ''
    }
  },
  computed: {
    localSelectedFile: {
      get() {
        return this.selectedFiles && this.selectedFiles.length > 0 ? this.selectedFiles[0] : ''
      },
      set(val) {
        this.$emit('update:selected-files', val ? [val] : [])
      }
    },
    filteredFiles() {
      if (!this.searchKeyword.trim()) {
        return this.files
      }
      const keyword = this.searchKeyword.trim().toLowerCase()
      return this.files.filter(file => file.toLowerCase().includes(keyword))
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
    },
    handleSearch() {
      if (this.filteredFiles.length > 0 && !this.filteredFiles.includes(this.localSelectedFile)) {
        this.localSelectedFile = ''
      }
    },
    highlightText(text) {
      if (!this.searchKeyword.trim()) {
        return text
      }
      const keyword = this.searchKeyword.trim()
      const regex = new RegExp(`(${keyword})`, 'gi')
      return text.replace(regex, '<span class="highlight-text">$1</span>')
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

.search-container {
  margin-bottom: 15px;
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

.file-radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
}

.file-radio-item {
  display: flex;
  align-items: center;
  margin: 0 !important;
  padding: 12px 15px;
  width: calc(25% - 15px);
  min-width: 220px;
  border: 2px solid #dcdfe6;
  border-radius: 6px;
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
}

.file-radio-item:hover {
  border-color: #c0c4cc;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
}

.file-radio-item.is-checked {
  background: linear-gradient(135deg, #ecf5ff 0%, #f5f7fa 100%);
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
}

.file-radio-item >>> .el-radio__input {
  margin-right: 8px;
}

.file-radio-item >>> .el-radio__label {
  display: flex;
  align-items: center;
  padding: 0;
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

.highlight-text {
  color: #409eff;
  font-weight: bold;
  background-color: #e6f2ff;
  padding: 0 2px;
  border-radius: 2px;
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
