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
              <el-autocomplete
                v-model="localConfig.dataPath"
                :fetch-suggestions="suggestDirs"
                placeholder="完整路径，如 D:/试验数据 或 //主机名/共享名（首次使用会自动登记）"
                clearable
                style="width: 100%"
              >
                <template #prepend>
                  <i class="el-icon-folder"></i>
                </template>
              </el-autocomplete>
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
            <el-form-item label="燃油密度(20℃)">
              <el-input 
                v-model.number="localConfig.mediumDensity" 
                placeholder="留空：按健康基准的油品"
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
          <el-col :span="8">
            <el-form-item label="分组大小">
              <el-input 
                v-model.number="localConfig.groupSize" 
                placeholder="数据分组行数"
                type="number"
                :min="1"
                clearable
              >
                <template #prepend>
                  <i class="el-icon-s-operation"></i>
                </template>
                <template #append>
                  行/组
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
        <span>仿真模型</span>
        <el-button type="text" style="float: right; padding: 0" @click="$router.push('/simulation')">管理仿真模型</el-button>
      </div>
      <div v-if="simStatus && simStatus.table" class="sim-info">
        诊断时自动按实测工况（{{ simStatus.table.inputs.map(i => i.name).join('、') }}）查仿真基准表，
        与模型预期值比较。当前模型：<b>{{ simStatus.table.model.label }}</b>，
        基准表建立于 {{ simStatus.table.created }}，标定用了 {{ simStatus.table.calibration.files }} 个正常数据文件。
      </div>
      <div v-else-if="simStatus" class="sim-info warn">
        还没有仿真基准表，诊断时不做模型对比。可在“仿真模型”页用正常数据建立。
      </div>
      <div v-else class="sim-info">正在读取仿真模型状态...</div>
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
import { getDataDirs } from '@/api/files'
import { getSimulationStatus } from '@/api/simulation'

export default {
  name: 'ConfigStep',
  props: {
    config: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      simStatus: null
    }
  },
  created() {
    getSimulationStatus().then(st => { this.simStatus = st }).catch(() => { this.simStatus = { table: null } })
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
    /** 输入框下拉：已登记 / 预置的数据目录 */
    async suggestDirs(query, callback) {
      try {
        const { preset, registered } = await getDataDirs()
        const keyword = (query || '').toLowerCase()
        callback([...registered, ...preset]
          .filter(dir => !keyword || dir.toLowerCase().includes(keyword))
          .map(value => ({ value })))
      } catch (e) {
        callback([])
      }
    },
    handleNext() {
      this.$emit('next')
    }
  }
}
</script>

<style scoped>
.sim-info {
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}
.sim-info.warn {
  color: #e6a23c;
}
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
