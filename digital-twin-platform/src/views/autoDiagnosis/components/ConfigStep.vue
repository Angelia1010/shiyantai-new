<template>
  <el-card class="config-step-card" shadow="hover">
    <div slot="header" class="card-header">
      <span>配置参数</span>
    </div>
    
    <el-card shadow="never" class="sub-card">
      <div slot="header">基本配置</div>
      <el-form label-width="120px">
        <el-row :gutter="20">
          <el-col :span="12">
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
          </el-col>
          <el-col :span="6">
            <el-form-item label="诊断模式">
              <el-radio-group v-model="localConfig.diagnosisMode" size="small">
                <el-radio-button label="realtime">实时监控</el-radio-button>
                <el-radio-button label="file">文件处理</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="自动诊断">
              <el-switch v-model="localConfig.autoDiagnosis" />
              <span class="switch-label">{{ localConfig.autoDiagnosis ? '开启' : '关闭' }}</span>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="介质密度">
              <el-input 
                v-model.number="localConfig.mediumDensity" 
                placeholder="如: 820"
                type="number"
                clearable
              >
                <template #prepend>
                  <i class="el-icon-data-line"></i>
                </template>
                <template #append>
                  kg/m³
                </template>
              </el-input>
            </el-form-item>
          </el-col>
        </el-row>
        <div class="form-tip">
          <template v-if="localConfig.diagnosisMode === 'realtime'">
            <i class="el-icon-info"></i> 实时监控模式：持续监控文件夹，新文件出现时自动诊断
          </template>
          <template v-else>
            <i class="el-icon-info"></i> 文件处理模式：选择指定文件进行诊断，处理完成后停止
          </template>
        </div>
      </el-form>
    </el-card>

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
        <el-row :gutter="20">
          <el-col :span="12">
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
          </el-col>
          <el-col :span="12">
            <el-form-item label="电传转速">
              <el-select 
                v-model="localConfig.electricalSpeed" 
                placeholder="请选择电传转速"
                style="width: 100%;"
              >
                <el-option 
                  v-for="item in electricalSpeedOptions" 
                  :key="item.value" 
                  :label="item.label" 
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <div class="form-tip">
          <i class="el-icon-info"></i> 选择电传转速后，将自动配置对应的三个流量控制参数
        </div>

        <el-divider content-position="left">
          <i class="el-icon-setting"></i> 仿真结果文件配置
        </el-divider>
        
        <div class="variable-grid" v-if="variableConfigs.length > 0">
          <div 
            v-for="(item, index) in variableConfigs" 
            :key="index"
            class="variable-item"
          >
            <div class="variable-header">
              <span class="variable-index">
                <i class="el-icon-coin"></i> 变量 {{ index + 1 }}
              </span>
              <el-button 
                type="text" 
                icon="el-icon-delete"
                :disabled="variableConfigs.length <= 1"
                @click="$emit('remove-variable', index)"
                class="delete-btn"
              />
            </div>
            <el-input 
              v-model="item.name" 
              placeholder="变量名称"
              size="small"
              class="variable-input"
            />
            <el-input 
              v-model="item.fileName" 
              placeholder="数据文件名（如 xxx.data）"
              size="small"
              class="variable-input"
            />
          </div>
        </div>
        
        <el-button 
          type="primary" 
          size="small" 
          icon="el-icon-plus"
          @click="$emit('add-variable')"
          class="add-variable-btn"
        >
          添加变量
        </el-button>
      </el-form>
    </el-card>

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
  data() {
    return {
      electricalSpeedOptions: [
        { value: 1295, label: '1295 rpm' },
        { value: 2999, label: '2999 rpm' },
        { value: 4975, label: '4975 rpm' },
        { value: 7958, label: '7958 rpm' },
        { value: 9990, label: '9990 rpm' }
      ]
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
  margin-bottom: 20px;
}

.sub-card:last-of-type {
  margin-bottom: 0;
}

.sub-card >>> .el-card__header {
  padding: 12px 16px;
  background-color: #f5f7fa;
  font-weight: 500;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
  padding: 8px 12px;
  background-color: #f4f4f5;
  border-radius: 4px;
  line-height: 1.6;
}

.form-tip i {
  margin-right: 4px;
}

.switch-label {
  margin-left: 10px;
  color: #606266;
}

.variable-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.variable-item {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  padding: 14px;
  background-color: #fafafa;
  transition: all 0.3s ease;
}

.variable-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.15);
  background-color: #fff;
}

.variable-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #e4e7ed;
}

.variable-index {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.variable-index i {
  margin-right: 4px;
  color: #409eff;
}

.delete-btn {
  padding: 0;
  color: #f56c6c;
  font-size: 16px;
}

.delete-btn:hover {
  color: #f78989;
}

.delete-btn.is-disabled {
  color: #c0c4cc;
}

.variable-input {
  margin-bottom: 8px;
}

.variable-input:last-child {
  margin-bottom: 0;
}

.add-variable-btn {
  margin-top: 8px;
}

.action-bar {
  margin-top: 20px;
  text-align: right;
  padding: 10px 0;
  border-top: 1px solid #ebeef5;
}

::v-deep .el-divider__text {
  background-color: #fff;
  color: #606266;
  font-weight: 500;
}

::v-deep .el-divider__text i {
  margin-right: 4px;
  color: #409eff;
}
</style>
