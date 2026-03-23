<template>
  <el-card class="config-step-card" shadow="hover">
    <div slot="header" class="card-header">
      <span>配置参数</span>
    </div>
    
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="never" class="sub-card">
          <div slot="header">基本配置</div>
          <el-form label-width="120px">
            <el-form-item label="试验数据路径" required>
              <el-input 
                v-model="localConfig.dataPath" 
                placeholder="请输入试验数据文件夹路径"
                clearable
              >
                <template #prepend>
                  <i class="el-icon-folder"></i>
                </template>
              </el-input>
            </el-form-item>
            
            <el-form-item label="诊断模式">
              <el-radio-group v-model="localConfig.diagnosisMode">
                <el-radio-button label="realtime">实时监控</el-radio-button>
                <el-radio-button label="file">文件处理</el-radio-button>
              </el-radio-group>
              <div class="form-tip">
                <template v-if="localConfig.diagnosisMode === 'realtime'">
                  实时监控模式：持续监控文件夹，新文件出现时自动诊断
                </template>
                <template v-else>
                  文件处理模式：选择指定文件进行诊断，处理完成后停止
                </template>
              </div>
            </el-form-item>

            <el-form-item label="自动诊断">
              <el-switch v-model="localConfig.autoDiagnosis" />
              <span class="switch-label">{{ localConfig.autoDiagnosis ? '开启' : '关闭' }}</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never" class="sub-card">
          <div slot="header">
            <span>AMESim仿真配置</span>
            <el-switch 
              v-model="localConfig.enableSimulation" 
              style="float: right;"
              active-text="启用"
              inactive-text="禁用"
            />
          </div>
          
          <el-form label-width="120px" :disabled="!localConfig.enableSimulation">
            <el-form-item label="模型文件路径">
              <el-input 
                v-model="localConfig.ameModel" 
                placeholder="如: pump_model.ame"
                clearable
              >
                <template #prepend>
                  <i class="el-icon-document"></i>
                </template>
              </el-input>
            </el-form-item>

            <el-divider content-position="left">仿真变量配置</el-divider>
            
            <el-form-item 
              v-for="(item, index) in variableConfigs" 
              :key="index" 
              :label="'变量 ' + (index + 1)"
            >
              <el-row :gutter="10">
                <el-col :span="10">
                  <el-input 
                    v-model="item.name" 
                    placeholder="变量名"
                    size="small"
                  />
                </el-col>
                <el-col :span="10">
                  <el-input 
                    v-model="item.path" 
                    placeholder="变量路径"
                    size="small"
                  />
                </el-col>
                <el-col :span="4">
                  <el-button 
                    type="danger" 
                    size="small" 
                    icon="el-icon-delete"
                    :disabled="variableConfigs.length <= 1"
                    @click="$emit('remove-variable', index)"
                    circle
                  />
                </el-col>
              </el-row>
            </el-form-item>
            
            <el-form-item>
              <el-button 
                type="primary" 
                size="small" 
                icon="el-icon-plus"
                @click="$emit('add-variable')"
              >
                添加变量
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <div class="action-bar">
      <el-button type="primary" size="medium" @click="handleNext">
        下一步
        <i class="el-icon-arrow-right"></i>
      </el-button>
    </div>
  </el-card>
</template>

<script>
export default {
  name: 'ConfigStep',
  props: {
    config: {
      type: Object,
      required: true
    },
    variableConfigs: {
      type: Array,
      required: true
    }
  },
  computed: {
    localConfig: {
      get() {
        return this.config
      },
      set(val) {
        this.$emit('update:config', val)
      }
    }
  },
  methods: {
    handleNext() {
      this.$emit('next')
    }
  }
}
</script>

<style scoped>
.config-step-card {
  max-height: calc(100vh - 280px);
  overflow-y: auto;
}

.card-header {
  font-size: 16px;
  font-weight: bold;
}

.sub-card {
  margin-bottom: 0;
}

.sub-card >>> .el-card__header {
  padding: 12px 16px;
  background-color: #f5f7fa;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

.switch-label {
  margin-left: 10px;
  color: #606266;
}

.action-bar {
  margin-top: 20px;
  text-align: right;
  padding: 10px 0;
  border-top: 1px solid #ebeef5;
}
</style>
