<template>
  <el-card class="diagnosis-exec-card" shadow="hover">
    <div slot="header" class="card-header">
      <span>诊断执行</span>
      <el-tag :type="isRunning ? 'success' : 'info'" size="small">
        {{ isRunning ? '运行中' : '待机' }}
      </el-tag>
    </div>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card shadow="never" class="process-card">
          <div slot="header">执行进度</div>
          <el-steps 
            direction="vertical" 
            :active="currentProcessStep" 
            finish-status="success"
            :space="60"
          >
            <el-step title="数据监控" :description="getStepDesc(1)" />
            <el-step title="数据预处理" :description="getStepDesc(2)" />
            <el-step title="仿真模型对比" :description="getStepDesc(3)" />
            <el-step title="故障诊断" :description="getStepDesc(4)" />
            <el-step title="报告生成" :description="getStepDesc(5)" />
          </el-steps>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="never" class="status-card">
          <div slot="header">执行状态</div>
          
          <el-alert
            :title="statusMessage"
            :type="getAlertType"
            :closable="false"
            show-icon
            style="margin-bottom: 15px;"
          />

          <div class="control-buttons">
            <el-button 
              type="primary" 
              size="medium"
              icon="el-icon-video-play"
              @click="$emit('start')"
              :loading="isRunning"
              :disabled="isRunning"
            >
              启动诊断
            </el-button>
            <el-button 
              type="danger" 
              size="medium"
              icon="el-icon-video-pause"
              @click="$emit('stop')"
              :disabled="!isRunning"
            >
              停止
            </el-button>
          </div>
        </el-card>

        <el-card shadow="never" class="log-card">
          <div slot="header">
            <span>执行日志</span>
            <el-button 
              type="text" 
              size="small" 
              icon="el-icon-delete"
              style="float: right;"
              @click="clearLogs"
            >
              清空
            </el-button>
          </div>
          <div class="log-container" ref="logContainer">
            <div 
              v-for="(log, index) in logs" 
              :key="index" 
              :class="['log-item', log.level]"
            >
              <span class="log-time">[{{ log.time }}]</span>
              <span class="log-message">{{ log.message }}</span>
            </div>
            <div v-if="logs.length === 0" class="log-empty">
              暂无日志
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <div class="action-bar">
      <el-button size="medium" @click="$emit('prev')" :disabled="isRunning">
        <i class="el-icon-arrow-left"></i>
        上一步
      </el-button>
      <el-button 
        type="primary" 
        size="medium" 
        @click="handleNext"
        :disabled="isRunning || currentProcessStep < 5"
      >
        查看结果
        <i class="el-icon-arrow-right"></i>
      </el-button>
    </div>
  </el-card>
</template>

<script>
export default {
  name: 'DiagnosisExecStep',
  props: {
    isRunning: { type: Boolean, default: false },
    logs: { type: Array, default: () => [] },
    currentProcessStep: { type: Number, default: 0 },
    statusMessage: { type: String, default: '等待启动' }
  },
  computed: {
    getAlertType() {
      return !this.isRunning && this.currentProcessStep >= 5 ? 'success' : 'info'
    }
  },
  watch: {
    logs() {
      this.$nextTick(() => {
        const box = this.$refs.logContainer
        if (box) box.scrollTop = box.scrollHeight
      })
    }
  },
  methods: {
    getStepDesc(step) {
      if (this.currentProcessStep < step) return '等待执行'
      if (this.currentProcessStep === step) return '执行中...'
      return '已完成'
    },
    clearLogs() {
      this.$emit('clear-logs')
    },
    handleNext() {
      this.$emit('next')
    }
  }
}
</script>

<style scoped>
.diagnosis-exec-card {
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

.process-card,
.status-card,
.log-card {
  margin-bottom: 15px;
}

.process-card >>> .el-card__header,
.status-card >>> .el-card__header,
.log-card >>> .el-card__header {
  padding: 10px 15px;
  background-color: #f5f7fa;
}

.control-buttons {
  margin: 15px 0;
}

.log-container {
  height: 250px;
  overflow-y: auto;
  background-color: #1d2530;
  border-radius: 4px;
  padding: 10px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}

.log-item {
  padding: 3px 0;
  display: flex;
}

.log-time {
  color: #909399;
  margin-right: 10px;
  flex-shrink: 0;
}

.log-message {
  color: #fff;
}

.log-item.info .log-message { color: #909399; }
.log-item.success .log-message { color: #67c23a; }
.log-item.warn .log-message { color: #e6a23c; }
.log-item.error .log-message { color: #f56c6c; }

.log-empty {
  color: #909399;
  text-align: center;
  padding: 20px;
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
