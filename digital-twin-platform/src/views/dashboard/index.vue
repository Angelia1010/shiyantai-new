<template>
  <div class="dashboard-container">
    <div class="bg-grid"></div>
    <div class="bg-glow"></div>
    <div class="bg-particles">
      <div v-for="i in 20" :key="i" class="particle" :style="getParticleStyle(i)"></div>
    </div>
    
    <div class="dashboard-content">
      <div class="header-section">
        <div class="title-wrapper">
          <div class="title-decoration left">
            <div class="deco-line"></div>
            <div class="deco-dot"></div>
          </div>
          <h1 class="main-title">
            <span class="title-text">标准试验台数字化校验系统</span>
            <span class="title-glow"></span>
          </h1>
          <div class="title-decoration right">
            <div class="deco-dot"></div>
            <div class="deco-line"></div>
          </div>
        </div>
        <div class="status-bar">
          <div class="status-item">
            <span class="status-dot pulse"></span>
            <span>系统运行中</span>
          </div>
          <div class="status-divider"></div>
          <div class="status-item">
            <span class="status-label">数据类型:</span>
            <span class="status-value">{{ dataType === 'experiment' ? '实验数据' : '仿真数据' }}</span>
          </div>
          <template v-if="isRealtimeFromDiagnosis">
            <div class="status-divider"></div>
            <div class="status-item">
              <span class="status-label">诊断模式:</span>
              <span class="status-value highlight">实时监控</span>
            </div>
          </template>
        </div>
      </div>

      <div class="alert-banner" v-if="isRealtimeFromDiagnosis && latestAbnormalResult">
        <div class="alert-content">
          <div class="alert-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
          </div>
          <div class="alert-text">
            <span class="alert-title">检测到异常状态</span>
            <span class="alert-info">文件: {{ latestAbnormalResult.filename }} | 时间: {{ latestAbnormalResult.timestamp }}</span>
          </div>
        </div>
        <div class="alert-actions">
          <button class="alert-btn view" @click="viewDiagnosisResult(latestAbnormalResult)">查看详情</button>
          <button class="alert-btn close" @click="clearAbnormalWarning">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <div class="main-content" :class="{ 'with-sidebar': isRealtimeFromDiagnosis }">
        <div class="content-main">
          <div class="model-section">
            <div class="section-header">
              <div class="section-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                </svg>
              </div>
              <span class="section-title">三维模型视图</span>
              <div class="section-line"></div>
            </div>
            <div class="model-3d-container">
              <div class="corner-decoration tl"></div>
              <div class="corner-decoration tr"></div>
              <div class="corner-decoration bl"></div>
              <div class="corner-decoration br"></div>
              <div class="model-inner">
                <PumpModel ref="pumpModelRef" />
              </div>
              <div class="scan-line"></div>
            </div>
          </div>

          <div class="bottom-section">
            <div class="control-panel">
              <div class="panel-header">
                <span class="panel-title">显示模式</span>
              </div>
              <div class="mode-buttons">
                <button 
                  :class="['mode-btn', mode === 'temperature' ? 'active' : '']" 
                  @click="mode = 'temperature'"
                >
                  <span class="btn-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/>
                    </svg>
                  </span>
                  <span class="btn-text">温度</span>
                </button>
                <button 
                  :class="['mode-btn', mode === 'pressure' ? 'active' : '']" 
                  @click="mode = 'pressure'"
                >
                  <span class="btn-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="M12 6v6l4 2"/>
                    </svg>
                  </span>
                  <span class="btn-text">压力</span>
                </button>
              </div>
            </div>

            <div class="gradient-panel">
              <div class="gradient-bar-container">
                <div class="gradient-label top">
                  <span class="label-value">{{ mode === "pressure" ? "35" : "90" }}</span>
                  <span class="label-unit">{{ mode === "pressure" ? "MPa" : "°C" }}</span>
                </div>
                <div class="gradient-track">
                  <div 
                    class="gradient-fill" 
                    :style="{ background: mode === 'pressure' ? pressureGradient : temperatureGradient }"
                  ></div>
                  <div class="gradient-markers">
                    <div v-for="i in 5" :key="i" class="marker"></div>
                  </div>
                </div>
                <div class="gradient-label bottom">
                  <span class="label-value">{{ mode === "pressure" ? "2" : "20" }}</span>
                  <span class="label-unit">{{ mode === "pressure" ? "MPa" : "°C" }}</span>
                </div>
              </div>
            </div>

            <div class="pump2d-section">
              <div class="pump2d-grid">
                <div 
                  v-for="port in ['供油1-1', '供油1-2', '回油1-1', '回油1-2']" 
                  :key="port" 
                  class="pump2d-card"
                >
                  <div class="card-header">
                    <span class="card-title">{{ port }}</span>
                    <span class="card-status online"></span>
                  </div>
                  <PumpModel2D 
                    :portName="port" 
                    :featureMap="featureMap" 
                    :viewDirection="'z'" 
                    :mode="mode" 
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="diagnosis-sidebar" v-if="isRealtimeFromDiagnosis">
          <div class="sidebar-header">
            <div class="sidebar-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
                <path d="M9 14l2 2 4-4"/>
              </svg>
              <span>诊断记录</span>
            </div>
            <div class="sidebar-stats">
              <span class="stat-item">
                <span class="stat-label">总计</span>
                <span class="stat-value">{{ diagnosisResults.length }}</span>
              </span>
              <span class="stat-item abnormal">
                <span class="stat-label">异常</span>
                <span class="stat-value">{{ diagnosisResults.filter(r => r.status === '异常').length }}</span>
              </span>
            </div>
          </div>
          
          <div class="diagnosis-list">
            <div 
              v-for="(result, index) in diagnosisResults" 
              :key="result.taskId" 
              class="diagnosis-item"
              :class="{ abnormal: result.status === '异常' }"
            >
              <div class="item-header">
                <div class="item-status" :class="result.status === '正常' ? 'normal' : 'abnormal'">
                  <span class="status-icon">
                    <svg v-if="result.status === '正常'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                      <polyline points="22 4 12 14.01 9 11.01"/>
                    </svg>
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="10"/>
                      <line x1="12" y1="8" x2="12" y2="12"/>
                      <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                  </span>
                  <span class="status-text">{{ result.status }}</span>
                </div>
                <span class="item-time">{{ result.timestamp }}</span>
              </div>
              <div class="item-content">
                <div class="item-filename">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                  </svg>
                  <span>{{ result.filename }}</span>
                </div>
                <div class="item-fault" v-if="result.status === '异常' && result.diagnosis && result.diagnosis.fault_name">
                  <span class="fault-label">故障类型:</span>
                  <span class="fault-value">{{ result.diagnosis.fault_name }}</span>
                </div>
              </div>
              <div class="item-actions">
                <button class="action-btn view" @click="viewDiagnosisResult(result)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                  <span>查看</span>
                </button>
                <button class="action-btn download" @click="downloadDiagnosisReport(result.taskId)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  <span>下载</span>
                </button>
              </div>
            </div>
            
            <div class="empty-state" v-if="diagnosisResults.length === 0">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
              </svg>
              <span>暂无诊断记录</span>
              <span class="empty-hint">等待新文件诊断...</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="diagnosis-detail-modal" v-if="showDiagnosisDetail && selectedDiagnosisResult">
      <div class="modal-overlay" @click="showDiagnosisDetail = false"></div>
      <div class="modal-content">
        <div class="modal-header">
          <span class="modal-title">诊断结果详情</span>
          <button class="modal-close" @click="showDiagnosisDetail = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="detail-section">
            <div class="detail-row">
              <span class="detail-label">文件名称:</span>
              <span class="detail-value">{{ selectedDiagnosisResult.filename }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">诊断时间:</span>
              <span class="detail-value">{{ selectedDiagnosisResult.timestamp }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">诊断结果:</span>
              <span class="detail-value" :class="selectedDiagnosisResult.status === '正常' ? 'normal' : 'abnormal'">
                {{ selectedDiagnosisResult.status }}
              </span>
            </div>
            <div class="detail-row" v-if="selectedDiagnosisResult.diagnosis && selectedDiagnosisResult.diagnosis.fault_name">
              <span class="detail-label">故障类型:</span>
              <span class="detail-value abnormal">{{ selectedDiagnosisResult.diagnosis.fault_name }}</span>
            </div>
          </div>
          
          <div class="detail-section" v-if="selectedDiagnosisResult.indicators">
            <div class="section-title">关键指标</div>
            <div class="indicators-list">
              <div 
                class="indicator-card" 
                v-for="(indicator, index) in formatIndicators(selectedDiagnosisResult.indicators)" 
                :key="index"
                :class="{ 'abnormal': indicator.isAbnormal }"
              >
                <div class="indicator-header">
                  <div class="indicator-icon" :class="indicator.type">
                    <svg v-if="indicator.type === 'flow'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 2v20M2 12h20M4.93 4.93l14.14 14.14M19.07 4.93L4.93 19.07"/>
                    </svg>
                    <svg v-else-if="indicator.type === 'speed'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="M12 6v6l4 2"/>
                    </svg>
                    <svg v-else-if="indicator.type === 'pressure'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 2v20M2 12h20"/>
                    </svg>
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="3"/>
                      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                    </svg>
                  </div>
                  <div class="indicator-status" v-if="indicator.isAbnormal">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="10"/>
                      <line x1="12" y1="8" x2="12" y2="12"/>
                      <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                  </div>
                </div>
                <div class="indicator-body">
                  <div class="indicator-name">{{ indicator.name }}</div>
                  <div class="indicator-value">{{ indicator.value }}</div>
                </div>
                <div class="indicator-footer">
                  <span class="indicator-reference">{{ indicator.reference }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="detail-section" v-if="selectedDiagnosisResult.repairAdvice">
            <div class="section-title">维修建议</div>
            <div class="repair-advice">
              {{ selectedDiagnosisResult.repairAdvice }}
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="footer-btn download" @click="downloadDiagnosisReport(selectedDiagnosisResult.taskId)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            <span>下载报告</span>
          </button>
          <button class="footer-btn close" @click="showDiagnosisDetail = false">关闭</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script>
import {
  readExcelApi,
  fileListAPI,
  newFileListAPI,
  getGoingJob,
  getJobStatus,
  diagnose,
  storeReport,
  createTask,
} from "@/api/home";
import { stopJob, downloadFile, fetchReportPreview } from "@/api/article";
import { Message } from "element-ui";
import PumpModel from "./PumpModel.vue";
import PumpModel2D from "./PumpModel2D.vue";
import {
  getBroadcastChannel,
  closeBroadcastChannel
} from "@/utils/broadcastChannel";

export default {
  components: {
    PumpModel,
    PumpModel2D,
  },
  data() {
    return {
      form: {
        name: "",
        region: "",
        date1: "",
        date2: "",
        delivery: false,
        type: [],
        resource: "",
        desc: "",
      },
      isSidebarVisible: false,

      showLoading: true,

      page: 0,
      pageSize: 500,
      timerId: null,
      fileNames: [],
      fileNameIndex: 0,

      isRunning: true,

      featureMap: {},
      sidebarBottomFeatureMap: {},
      queueThreshold: 60,
      spectrumQueue: [],
      featuresQueue: [],
      featuresConsumerTimer: null,
      spectrum: {},
      groupSize: 50,
      spectrumIndex: 0,

      mode: "temperature",
      pumpState: { swashAngle: 0, rotateSpeed: 0 },
      dataType: "experiment",
      isRealtimeFromDiagnosis: false,
      diagnosisStatus: null,
      broadcastChannel: null,
      diagnosisResults: [],
      latestAbnormalResult: null,
      selectedDiagnosisResult: null,
      showDiagnosisDetail: false,
    };
  },
  computed: {
    temperatureGradient() {
      return "linear-gradient(to bottom, #ff0055 0%, #ff6b00 20%, #ffd000 40%, #00ff88 60%, #00d4ff 80%, #0066ff 100%)";
    },
    pressureGradient() {
      return "linear-gradient(to bottom, #ff0055 0%, #ff6b00 20%, #ffd000 40%, #00ff88 60%, #00d4ff 80%, #0066ff 100%)";
    },
  },
  created() {
    window.addEventListener("message", this.iframeEventListener);
    window.hideLoading = () => {
      this.showLoading = false;
    };

    const hash = window.location.hash.substring(1);
    const urlParams = new URLSearchParams(hash.split("?")[1]);
    this.type = urlParams.get("type") || null;
    this.path = urlParams.get("path") || null;
    this.fault = urlParams.get("fault") || null;
    this.selectedItems = urlParams.get("selectedItems")
      ? urlParams.get("selectedItems").split(",")
      : [];

    const mode = urlParams.get("mode");
    const source = urlParams.get("source");
    if (mode === "realtime" && source === "autoDiagnosis") {
      this.isRealtimeFromDiagnosis = true;
      this.initBroadcastChannelListener();
    }

    console.log("urlParams:", urlParams);
    console.log("type:", this.type);
    console.log("path:", this.path);
    console.log("fault:", this.fault);
    console.log("selectedItems:", this.selectedItems);
    console.log("isRealtimeFromDiagnosis:", this.isRealtimeFromDiagnosis);
  },
  mounted() {
    if (!this.isRealtimeFromDiagnosis) {
      this.run();
    }
    this.featuresConsumerTimer = setInterval(() => {
      if (this.featuresQueue && this.featuresQueue.length > 0) {
        const feature = this.featuresQueue.shift();
        this.featureMap = feature || {};
        console.log("Dashboard-featureMap:", this.featureMap)
        this.sidebarBottomFeatureMap = feature || {};
      }
    }, 1000);
  },
  destroyed() {
    console.log("destroyed");
    this.isRunning = false;
    window.removeEventListener("message", this.iframeEventListener);
    if (this.featuresConsumerTimer) {
      clearInterval(this.featuresConsumerTimer);
      this.featuresConsumerTimer = null;
    }
    if (this.broadcastChannel) {
      this.broadcastChannel.close();
      this.broadcastChannel = null;
    }
  },
  methods: {
    initBroadcastChannelListener() {
      this.broadcastChannel = getBroadcastChannel();
      this.broadcastChannel.onmessage = (event) => {
        const { type, payload } = event.data;
        console.log("Dashboard received broadcast message:", type, payload);

        switch (type) {
          case "FEATURE_MAP":
            this.featuresQueue.push(payload);
            console.log("Dashboard received featureMap:", payload);
            break;
          case "DIAGNOSIS_STATUS":
            this.diagnosisStatus = payload;
            console.log("Dashboard received status:", payload);
            break;
          case "DIAGNOSIS_RESULT":
            this.addDiagnosisResult(payload);
            console.log("Dashboard received diagnosis result:", payload);
            break;
          case "DIAGNOSIS_DATA":
            console.log("Dashboard received diagnosis data:", payload);
            break;
          default:
            console.log("Unknown message type:", type);
        }
      };
      console.log("Dashboard BroadcastChannel listener initialized");
    },

    addDiagnosisResult(result) {
      this.diagnosisResults.unshift(result);
      if (result.status === '异常') {
        this.latestAbnormalResult = result;
      }
    },

    viewDiagnosisResult(result) {
      this.selectedDiagnosisResult = result;
      this.showDiagnosisDetail = true;
    },

    downloadDiagnosisReport(taskId) {
      if (taskId) {
        downloadFile(taskId);
        Message.success('报告下载已开始');
      }
    },

    formatTimestamp(timestamp) {
      if (!timestamp) return '-';
      return timestamp;
    },

    clearAbnormalWarning() {
      this.latestAbnormalResult = null;
    },

    formatIndicators(indicators) {
      if (!indicators || !Array.isArray(indicators)) {
        return [];
      }
      return indicators.map(item => {
        const name = item.name || '';
        const value = item.value || '';
        const reference = item.reference || '';
        
        let type = 'default';
        if (name.includes('流量')) {
          type = 'flow';
        } else if (name.includes('转速')) {
          type = 'speed';
        } else if (name.includes('压力')) {
          type = 'pressure';
        }
        
        const isAbnormal = value.includes('⚠️') || value.includes('超限') || value.includes('异常');
        
        const cleanValue = value.replace(' ⚠️超限', '').replace(' ✓正常', '').replace(' ⚠️异常', '');
        
        return {
          name,
          value: cleanValue,
          reference,
          type,
          isAbnormal
        };
      });
    },

    getParticleStyle(index) {
      const size = Math.random() * 4 + 2;
      return {
        width: `${size}px`,
        height: `${size}px`,
        left: `${Math.random() * 100}%`,
        top: `${Math.random() * 100}%`,
        animationDelay: `${Math.random() * 20}s`,
        animationDuration: `${15 + Math.random() * 20}s`,
      };
    },

    async sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    },

    async run() {
      console.log("开始获取任务");
      if (!this.type || !this.path || !this.selectedItems) {
        console.log("参数不完整，停止任务");
        return;
      }
      console.log("type:", this.type);
      console.log("path:", this.path);
      console.log("selectedItems:", this.selectedItems);

      if (this.type === "0") {
        console.log("进入默认任务");
        while (this.isRunning) {
          try {
            console.log("开始获取新文件列表");
            const response = await newFileListAPI(this.path);
            this.fileNames = response.new_files || [];
            console.log("新文件列表:", this.fileNames);
            if (this.fileNames.length) {
              for (const filename of this.fileNames) {
                if (this.fault === "1") {
                  const now = Date.now();
                  const rand = Math.floor(Math.random() * 100000)
                    .toString()
                    .padStart(5, "0");
                  const task_id = `${now}${rand}`;
                  const data = {
                    task_id,
                    file_name: filename,
                    path: this.path,
                    type: this.type,
                    fault: "1",
                  };
                  try {
                    await createTask(data);
                    await storeReport(data);
                  } catch (e) {
                    console.log("createTask error:", e);
                    this.$message.error("诊断任务创建失败！");
                  }
                }

                await this.updateData(filename, this.path);
              }
            }
            await this.sleep(5000);
          } catch (e) {
            console.log("error:", e);
            break;
          }
        }
      } else {
        console.log("进入自定义任务");
        while (this.isRunning) {
          for (const fileName of this.selectedItems) {
            console.log("开始处理文件：", fileName);
            await this.updateData(fileName, this.path);
          }
        }
      }
      console.log("run loop stopped.");
    },

    async updateData(filename, path) {
      console.log("开始处理任务filename：", filename);

      this.page = 0;
      while (this.isRunning) {
        console.log("队列长度：", this.featuresQueue.length);
        if (
          this.featuresQueue &&
          this.featuresQueue.length >= this.queueThreshold
        ) {
          console.log(
            `featuresQueue 已有 ${this.featuresQueue.length} 条，跳过本次请求`
          );
          await this.sleep(1000);
          continue;
        }

        const data = {
          page: this.page,
          page_size: this.pageSize,
          file_names: [filename],
          sheet_names: ["1"],
          path: path,
        };
        const hasNextData = await this.loadDataNew(data);

        if (hasNextData) {
          this.page++;
        } else {
          console.log("完成处理文件：", filename);
          break;
        }
      }
      console.log("结束处理任务");
    },
    async loadDataNew(requestReq) {
      const useMockData = false;

      if (useMockData) {
        await this.sleep(200);

        const totalPages = 5;
        if (requestReq.page >= totalPages) {
          return false;
        }

        console.log(`[Mock] 返回第 ${requestReq.page} 页模拟数据`);

        const mockResponse = this.generateMockData(requestReq);

        const firstKey = Object.keys(mockResponse)[0];
        const res = mockResponse[firstKey];
        const dataRoot =
          this.dataType === "experiment" ? res["1"] : res["13-1"];

        if (!dataRoot) return false;

        const fields = [
          "燃油泵实际转速",
          "电传实际转速",
          "电传扭矩",
          "P1进口压力",
          "P17滑油压力",
          "P18回油工况模拟供油压力",
          "P2低压出口压力",
          "P3高压出口压力",
          "供油压力1-1",
          "供油压力1-2",
          "回油压力1-2",
          "回油压力1-1",
          "回油压力2-2",
          "回油压力2-1",
          "回油流量1-2",
          "回油流量2-2",
          "回油流量2-1",
          "回油流量1-1",
          "供油流量1-1",
          "供油流量1-2",
          "T20加热出口温度",
          "T3进口温度",
          "T4高压出口温度",
          "T5出口温度",
          "供油温度1-1",
          "供油温度1-2",
          "回油温度2-2",
          "回油温度2-1",
          "回油温度1-2",
          "回油温度1-1",
          "振动传感器1-1",
          "振动传感器2-1",
          "振动传感器3-1",
        ];

        const allFieldData = {};
        for (const field of fields) {
          const arr = dataRoot[field];
          if (arr && Array.isArray(arr)) {
            allFieldData[field] = arr;
          }
        }

        const maxLen = Math.max(
          ...Object.values(allFieldData).map((arr) => arr.length || 0),
          0
        );

        for (let i = 0; i < maxLen; i += this.groupSize) {
          const featureMap = {};
          for (const field of fields) {
            const arr = allFieldData[field] || [];
            const group = arr
              .slice(i, i + this.groupSize)
              .map((v) =>
                v === "nan" || v === null || v === undefined ? NaN : Number(v)
              )
              .filter((v) => typeof v === "number" && !isNaN(v));
            if (group.length > 0) {
              const max = Math.max(...group);
              const min = Math.min(...group);
              const avg = group.reduce((a, b) => a + b, 0) / group.length;
              featureMap[field] = { max, min, avg };
            }
          }
          if (Object.keys(featureMap).length > 0) {
            this.featuresQueue.push(featureMap);
          }
        }
        return true;
      }

      try {
        console.log("数据请求体：", requestReq);
        const response = await readExcelApi(requestReq);
        const firstKey = Object.keys(response)[0];
        const res = response[firstKey];
        console.log("res:", res);
        const dataRoot =
          this.dataType === "experiment" ? res["data"]["1"] : res["data"]["13-1"];

        if (!dataRoot) return false;

        const fields = [
          "燃油泵实际转速",
          "电传实际转速",
          "电传扭矩",
          "P1进口压力",
          "P17滑油压力",
          "P18回油工况模拟供油压力",
          "P2低压出口压力",
          "P3高压出口压力",
          "供油压力1-1",
          "供油压力1-2",
          "回油压力1-2",
          "回油压力1-1",
          "回油压力2-2",
          "回油压力2-1",
          "回油流量1-2",
          "回油流量2-2",
          "回油流量2-1",
          "回油流量1-1",
          "供油流量1-1",
          "供油流量1-2",
          "T20加热出口温度",
          "T3进口温度",
          "T4高压出口温度",
          "T5出口温度",
          "供油温度1-1",
          "供油温度1-2",
          "回油温度2-2",
          "回油温度2-1",
          "回油温度1-2",
          "回油温度1-1",
          "振动传感器1-1",
          "振动传感器2-1",
          "振动传感器3-1",
        ];

        const allFieldData = {};
        for (const field of fields) {
          const arr = dataRoot[field];
          if (arr && Array.isArray(arr)) {
            allFieldData[field] = arr;
          }
        }
        const maxLen = Math.max(
          ...Object.values(allFieldData).map((arr) => arr.length || 0),
          0
        );
        for (let i = 0; i < maxLen; i += this.groupSize) {
          const featureMap = {};
          for (const field of fields) {
            const arr = allFieldData[field] || [];
            const group = arr
              .slice(i, i + this.groupSize)
              .map((v) =>
                v === "nan" || v === null || v === undefined ? NaN : Number(v)
              )
              .filter((v) => typeof v === "number" && !isNaN(v));
            if (group.length > 0) {
              const max = Math.max(...group);
              const min = Math.min(...group);
              const avg = group.reduce((a, b) => a + b, 0) / group.length;
              featureMap[field] = { max, min, avg };
            }
          }
          if (Object.keys(featureMap).length > 0) {
            this.featuresQueue.push(featureMap);
          } else {
            return false;
          }
        }
        return true;
      } catch (error) {
        console.error("接口调用失败，使用模拟数据:", error);
        return this.loadDataNew({ ...requestReq, useMockData: true });
      }
    },

    switchDataType(type) {
      this.dataType = type;
      this.featuresQueue = [];
      this.featureMap = {};
      this.sidebarBottomFeatureMap = {};
      this.page = 0;
      this.run();
    },

    generateMockData(requestReq) {
      const filename = requestReq.file_name[0] || "mock_file.xlsx";
      const page = requestReq.page || 0;
      const dataSize = requestReq.page_size || 500;

      const generateFieldData = (baseValue, variance = 0.1, trend = 0) => {
        const data = [];
        for (let i = 0; i < dataSize; i++) {
          const randomFactor = 1 + (Math.random() - 0.5) * variance;
          const trendFactor = 1 + (trend * i) / dataSize;
          const value = baseValue * randomFactor * trendFactor;
          data.push(Number(value.toFixed(3)));
        }
        return data;
      };

      const timeOffset = page * dataSize;

      const mockData = {
        [filename]: {
          1: {
            燃油泵实际转速: generateFieldData(
              1500 + Math.sin(timeOffset / 100) * 200,
              0.05
            ),
            电传实际转速: generateFieldData(
              1480 + Math.sin(timeOffset / 100) * 180,
              0.04
            ),
            电传扭矩: generateFieldData(
              120 + Math.cos(timeOffset / 150) * 30,
              0.08
            ),
            P1进口压力: generateFieldData(
              2.5 + Math.sin(timeOffset / 200) * 0.5,
              0.06
            ),
            P17滑油压力: generateFieldData(
              1.8 + Math.cos(timeOffset / 180) * 0.3,
              0.05
            ),
            P18回油工况模拟供油压力: generateFieldData(
              3.2 + Math.sin(timeOffset / 160) * 0.6,
              0.07
            ),
            P2低压出口压力: generateFieldData(
              1.2 + Math.cos(timeOffset / 220) * 0.2,
              0.04
            ),
            P3高压出口压力: generateFieldData(
              25.5 + Math.sin(timeOffset / 140) * 5,
              0.1
            ),
            "供油压力1-1": generateFieldData(
              28.0 + Math.sin(timeOffset / 130) * 4,
              0.08
            ),
            "供油压力1-2": generateFieldData(
              27.8 + Math.cos(timeOffset / 135) * 4.2,
              0.08
            ),
            "回油压力1-1": generateFieldData(
              0.8 + Math.sin(timeOffset / 250) * 0.1,
              0.05
            ),
            "回油压力1-2": generateFieldData(
              0.9 + Math.cos(timeOffset / 240) * 0.12,
              0.05
            ),
            "回油压力2-1": generateFieldData(
              0.85 + Math.sin(timeOffset / 260) * 0.11,
              0.05
            ),
            "回油压力2-2": generateFieldData(
              0.88 + Math.cos(timeOffset / 255) * 0.1,
              0.05
            ),
            "回油流量1-1": generateFieldData(
              150 + Math.sin(timeOffset / 120) * 20,
              0.12
            ),
            "回油流量1-2": generateFieldData(
              148 + Math.cos(timeOffset / 125) * 22,
              0.12
            ),
            "回油流量2-1": generateFieldData(
              152 + Math.sin(timeOffset / 115) * 18,
              0.11
            ),
            "回油流量2-2": generateFieldData(
              149 + Math.cos(timeOffset / 118) * 21,
              0.12
            ),
            "供油流量1-1": generateFieldData(
              300 + Math.sin(timeOffset / 110) * 40,
              0.15
            ),
            "供油流量1-2": generateFieldData(
              298 + Math.cos(timeOffset / 112) * 42,
              0.15
            ),
            T20加热出口温度: generateFieldData(
              65 + Math.sin(timeOffset / 300) * 5,
              0.03
            ),
            T3进口温度: generateFieldData(
              45 + Math.sin(timeOffset / 280) * 3,
              0.04
            ),
            T4高压出口温度: generateFieldData(
              55 + Math.cos(timeOffset / 290) * 4,
              0.03
            ),
            T5出口温度: generateFieldData(
              50 + Math.sin(timeOffset / 270) * 3.5,
              0.04
            ),
            "供油温度1-1": generateFieldData(
              48 + Math.sin(timeOffset / 285) * 3.2,
              0.04
            ),
            "供油温度1-2": generateFieldData(
              47.5 + Math.cos(timeOffset / 275) * 3.3,
              0.04
            ),
            "回油温度1-1": generateFieldData(
              52 + Math.sin(timeOffset / 265) * 2.8,
              0.03
            ),
            "回油温度1-2": generateFieldData(
              51.8 + Math.cos(timeOffset / 268) * 2.9,
              0.03
            ),
            "回油温度2-1": generateFieldData(
              51.5 + Math.sin(timeOffset / 272) * 2.7,
              0.03
            ),
            "回油温度2-2": generateFieldData(
              52.2 + Math.cos(timeOffset / 278) * 2.8,
              0.03
            ),
            "振动传感器1-1": generateFieldData(
              0.5 + Math.sin(timeOffset / 50) * 0.3,
              0.25
            ),
            "振动传感器2-1": generateFieldData(
              0.6 + Math.cos(timeOffset / 55) * 0.35,
              0.25
            ),
            "振动传感器3-1": generateFieldData(
              0.55 + Math.sin(timeOffset / 52) * 0.32,
              0.25
            ),
          },
          "13-1": {
            燃油泵实际转速: generateFieldData(
              1520 + Math.sin(timeOffset / 105) * 190,
              0.04
            ),
            电传实际转速: generateFieldData(
              1500 + Math.sin(timeOffset / 105) * 170,
              0.035
            ),
            电传扭矩: generateFieldData(
              115 + Math.cos(timeOffset / 155) * 28,
              0.07
            ),
            P1进口压力: generateFieldData(
              2.6 + Math.sin(timeOffset / 205) * 0.45,
              0.055
            ),
            P17滑油压力: generateFieldData(
              1.85 + Math.cos(timeOffset / 185) * 0.28,
              0.045
            ),
            P18回油工况模拟供油压力: generateFieldData(
              3.3 + Math.sin(timeOffset / 165) * 0.55,
              0.065
            ),
            P2低压出口压力: generateFieldData(
              1.25 + Math.cos(timeOffset / 225) * 0.18,
              0.035
            ),
            P3高压出口压力: generateFieldData(
              26.0 + Math.sin(timeOffset / 145) * 4.8,
              0.09
            ),
            "供油压力1-1": generateFieldData(
              28.5 + Math.sin(timeOffset / 135) * 3.8,
              0.075
            ),
            "供油压力1-2": generateFieldData(
              28.3 + Math.cos(timeOffset / 140) * 4.0,
              0.075
            ),
            "回油压力1-1": generateFieldData(
              0.82 + Math.sin(timeOffset / 255) * 0.09,
              0.045
            ),
            "回油压力1-2": generateFieldData(
              0.92 + Math.cos(timeOffset / 245) * 0.11,
              0.045
            ),
            "回油压力2-1": generateFieldData(
              0.87 + Math.sin(timeOffset / 265) * 0.105,
              0.045
            ),
            "回油压力2-2": generateFieldData(
              0.9 + Math.cos(timeOffset / 260) * 0.095,
              0.045
            ),
            "回油流量1-1": generateFieldData(
              155 + Math.sin(timeOffset / 125) * 18,
              0.11
            ),
            "回油流量1-2": generateFieldData(
              153 + Math.cos(timeOffset / 130) * 20,
              0.11
            ),
            "回油流量2-1": generateFieldData(
              157 + Math.sin(timeOffset / 120) * 16,
              0.1
            ),
            "回油流量2-2": generateFieldData(
              154 + Math.cos(timeOffset / 123) * 19,
              0.11
            ),
            "供油流量1-1": generateFieldData(
              305 + Math.sin(timeOffset / 115) * 38,
              0.14
            ),
            "供油流量1-2": generateFieldData(
              303 + Math.cos(timeOffset / 117) * 40,
              0.14
            ),
            T20加热出口温度: generateFieldData(
              67 + Math.sin(timeOffset / 305) * 4.8,
              0.025
            ),
            T3进口温度: generateFieldData(
              47 + Math.sin(timeOffset / 285) * 2.8,
              0.035
            ),
            T4高压出口温度: generateFieldData(
              57 + Math.cos(timeOffset / 295) * 3.8,
              0.025
            ),
            T5出口温度: generateFieldData(
              52 + Math.sin(timeOffset / 275) * 3.3,
              0.035
            ),
            "供油温度1-1": generateFieldData(
              50 + Math.sin(timeOffset / 290) * 3.0,
              0.035
            ),
            "供油温度1-2": generateFieldData(
              49.5 + Math.cos(timeOffset / 280) * 3.1,
              0.035
            ),
            "回油温度1-1": generateFieldData(
              54 + Math.sin(timeOffset / 270) * 2.6,
              0.025
            ),
            "回油温度1-2": generateFieldData(
              53.8 + Math.cos(timeOffset / 273) * 2.7,
              0.025
            ),
            "回油温度2-1": generateFieldData(
              53.5 + Math.sin(timeOffset / 277) * 2.5,
              0.025
            ),
            "回油温度2-2": generateFieldData(
              54.2 + Math.cos(timeOffset / 283) * 2.6,
              0.025
            ),
            "振动传感器1-1": generateFieldData(
              0.45 + Math.sin(timeOffset / 52) * 0.28,
              0.22
            ),
            "振动传感器2-1": generateFieldData(
              0.55 + Math.cos(timeOffset / 57) * 0.32,
              0.22
            ),
            "振动传感器3-1": generateFieldData(
              0.5 + Math.sin(timeOffset / 54) * 0.3,
              0.22
            ),
          },
        },
      };

      console.log(`[Mock] 生成第 ${page} 页数据，包含 ${dataSize} 条记录`);
      return mockData;
    },
  },
};
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&display=swap');

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.dashboard-container {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, #0a0e17 0%, #1a1f2e 50%, #0d1321 100%);
  position: relative;
  overflow: hidden;
  font-family: 'Orbitron', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.bg-grid {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: 
    linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px);
  background-size: 50px 50px;
  pointer-events: none;
}

.bg-glow {
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle at 30% 30%, rgba(0, 150, 255, 0.08) 0%, transparent 50%),
              radial-gradient(circle at 70% 70%, rgba(0, 255, 200, 0.05) 0%, transparent 50%);
  pointer-events: none;
  animation: glowPulse 15s ease-in-out infinite;
}

@keyframes glowPulse {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50% { opacity: 0.8; transform: scale(1.1); }
}

.bg-particles {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
}

.particle {
  position: absolute;
  background: rgba(0, 212, 255, 0.6);
  border-radius: 50%;
  animation: particleFloat 20s linear infinite;
  box-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
}

@keyframes particleFloat {
  0% { transform: translateY(100vh) rotate(0deg); opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  100% { transform: translateY(-100vh) rotate(720deg); opacity: 0; }
}

.dashboard-content {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px 30px;
}

.header-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 20px;
}

.title-wrapper {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 15px;
}

.title-decoration {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-decoration.left .deco-line {
  width: 80px;
  height: 2px;
  background: linear-gradient(90deg, transparent, #00d4ff);
}

.title-decoration.right .deco-line {
  width: 80px;
  height: 2px;
  background: linear-gradient(90deg, #00d4ff, transparent);
}

.deco-dot {
  width: 8px;
  height: 8px;
  background: #00d4ff;
  border-radius: 50%;
  box-shadow: 0 0 10px #00d4ff, 0 0 20px #00d4ff;
  animation: dotPulse 2s ease-in-out infinite;
}

@keyframes dotPulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.3); opacity: 0.7; }
}

.main-title {
  position: relative;
  font-size: 32px;
  font-weight: 700;
  letter-spacing: 4px;
  color: #fff;
  text-shadow: 0 0 20px rgba(0, 212, 255, 0.5);
}

.title-text {
  background: linear-gradient(90deg, #00d4ff, #00ff88, #00d4ff);
  background-size: 200% 100%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: titleShine 3s linear infinite;
}

@keyframes titleShine {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.title-glow {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 100%;
  height: 100%;
  background: radial-gradient(ellipse, rgba(0, 212, 255, 0.2) 0%, transparent 70%);
  filter: blur(20px);
  pointer-events: none;
}

.status-bar {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 8px 25px;
  background: rgba(0, 212, 255, 0.05);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 20px;
  backdrop-filter: blur(10px);
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

.status-dot {
  width: 8px;
  height: 8px;
  background: #00ff88;
  border-radius: 50%;
  box-shadow: 0 0 10px #00ff88;
}

.status-dot.pulse {
  animation: statusPulse 1.5s ease-in-out infinite;
}

@keyframes statusPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.2); }
}

.status-divider {
  width: 1px;
  height: 15px;
  background: rgba(0, 212, 255, 0.3);
}

.status-label {
  color: rgba(255, 255, 255, 0.5);
}

.status-value {
  color: #00d4ff;
  font-weight: 500;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 0;
}

.model-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 15px;
}

.section-icon {
  width: 28px;
  height: 28px;
  color: #00d4ff;
}

.section-icon svg {
  width: 100%;
  height: 100%;
}

.section-title {
  font-size: 16px;
  font-weight: 500;
  color: #fff;
  letter-spacing: 2px;
}

.section-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, rgba(0, 212, 255, 0.5), transparent);
}

.model-3d-container {
  flex: 1;
  position: relative;
  background: linear-gradient(135deg, rgba(0, 30, 60, 0.6) 0%, rgba(0, 20, 40, 0.8) 100%);
  border: 1px solid rgba(0, 212, 255, 0.3);
  border-radius: 12px;
  overflow: hidden;
  min-height: 300px;
}

.corner-decoration {
  position: absolute;
  width: 30px;
  height: 30px;
  pointer-events: none;
}

.corner-decoration.tl {
  top: 0;
  left: 0;
  border-top: 2px solid #00d4ff;
  border-left: 2px solid #00d4ff;
  border-top-left-radius: 12px;
}

.corner-decoration.tr {
  top: 0;
  right: 0;
  border-top: 2px solid #00d4ff;
  border-right: 2px solid #00d4ff;
  border-top-right-radius: 12px;
}

.corner-decoration.bl {
  bottom: 0;
  left: 0;
  border-bottom: 2px solid #00d4ff;
  border-left: 2px solid #00d4ff;
  border-bottom-left-radius: 12px;
}

.corner-decoration.br {
  bottom: 0;
  right: 0;
  border-bottom: 2px solid #00d4ff;
  border-right: 2px solid #00d4ff;
  border-bottom-right-radius: 12px;
}

.model-inner {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.scan-line {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(0, 212, 255, 0.8), transparent);
  animation: scanLine 4s linear infinite;
  pointer-events: none;
}

@keyframes scanLine {
  0% { top: 0; opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  100% { top: 100%; opacity: 0; }
}

.bottom-section {
  display: flex;
  gap: 20px;
  align-items: stretch;
}

.control-panel {
  background: rgba(0, 30, 60, 0.5);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 12px;
  padding: 15px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 160px;
}

.panel-header {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
  letter-spacing: 1px;
  text-transform: uppercase;
}

.mode-buttons {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mode-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 15px;
  background: rgba(0, 212, 255, 0.05);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  transition: all 0.3s ease;
  font-family: inherit;
  font-size: 13px;
}

.mode-btn:hover {
  background: rgba(0, 212, 255, 0.1);
  border-color: rgba(0, 212, 255, 0.4);
  color: #fff;
}

.mode-btn.active {
  background: linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(0, 255, 136, 0.1));
  border-color: #00d4ff;
  color: #00d4ff;
  box-shadow: 0 0 15px rgba(0, 212, 255, 0.3), inset 0 0 15px rgba(0, 212, 255, 0.1);
}

.btn-icon {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-icon svg {
  width: 100%;
  height: 100%;
}

.gradient-panel {
  background: rgba(0, 30, 60, 0.5);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 12px;
  padding: 15px 20px;
  display: flex;
  align-items: center;
}

.gradient-bar-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.gradient-label {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.label-value {
  font-size: 16px;
  font-weight: 700;
  color: #fff;
}

.label-unit {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}

.gradient-track {
  position: relative;
  width: 16px;
  height: 120px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(0, 212, 255, 0.2);
}

.gradient-fill {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  border-radius: 7px;
}

.gradient-markers {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 5px 0;
  pointer-events: none;
}

.marker {
  width: 100%;
  height: 1px;
  background: rgba(255, 255, 255, 0.3);
}

.pump2d-section {
  flex: 1;
  background: rgba(0, 30, 60, 0.5);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 12px;
  padding: 15px;
}

.pump2d-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 15px;
  height: 100%;
}

.pump2d-card {
  background: rgba(0, 20, 40, 0.6);
  border: 1px solid rgba(0, 212, 255, 0.15);
  border-radius: 8px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
}

.pump2d-card:hover {
  border-color: rgba(0, 212, 255, 0.4);
  box-shadow: 0 0 20px rgba(0, 212, 255, 0.1);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(0, 212, 255, 0.1);
}

.card-title {
  font-size: 12px;
  color: #00d4ff;
  font-weight: 500;
  letter-spacing: 1px;
}

.card-status {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #00ff88;
  box-shadow: 0 0 8px #00ff88;
  animation: statusPulse 2s ease-in-out infinite;
}

.status-value.highlight {
  color: #00ff88;
  text-shadow: 0 0 10px rgba(0, 255, 136, 0.5);
}

.alert-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: linear-gradient(90deg, rgba(255, 0, 85, 0.15), rgba(255, 107, 0, 0.1));
  border: 1px solid rgba(255, 0, 85, 0.4);
  border-radius: 10px;
  margin-bottom: 15px;
  animation: alertPulse 2s ease-in-out infinite;
}

@keyframes alertPulse {
  0%, 100% { box-shadow: 0 0 10px rgba(255, 0, 85, 0.2); }
  50% { box-shadow: 0 0 20px rgba(255, 0, 85, 0.4); }
}

.alert-content {
  display: flex;
  align-items: center;
  gap: 15px;
}

.alert-icon {
  width: 24px;
  height: 24px;
  color: #ff0055;
  animation: alertIconPulse 1s ease-in-out infinite;
}

@keyframes alertIconPulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

.alert-icon svg {
  width: 100%;
  height: 100%;
}

.alert-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.alert-title {
  font-size: 14px;
  font-weight: 600;
  color: #ff0055;
  letter-spacing: 1px;
}

.alert-info {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}

.alert-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.alert-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 15px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  font-family: inherit;
}

.alert-btn.view {
  background: rgba(255, 0, 85, 0.2);
  border: 1px solid rgba(255, 0, 85, 0.5);
  color: #ff0055;
}

.alert-btn.view:hover {
  background: rgba(255, 0, 85, 0.3);
  border-color: #ff0055;
}

.alert-btn.close {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.6);
  padding: 8px;
}

.alert-btn.close:hover {
  border-color: rgba(255, 255, 255, 0.4);
  color: #fff;
}

.alert-btn svg {
  width: 16px;
  height: 16px;
}

.main-content.with-sidebar {
  flex-direction: row;
  gap: 20px;
}

.content-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

.diagnosis-sidebar {
  width: 320px;
  background: linear-gradient(180deg, rgba(0, 30, 60, 0.6) 0%, rgba(0, 20, 40, 0.8) 100%);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 15px 20px;
  border-bottom: 1px solid rgba(0, 212, 255, 0.15);
  background: rgba(0, 212, 255, 0.05);
}

.sidebar-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #00d4ff;
  letter-spacing: 1px;
  margin-bottom: 12px;
}

.sidebar-title svg {
  width: 20px;
  height: 20px;
}

.sidebar-stats {
  display: flex;
  gap: 20px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
}

.stat-value {
  font-size: 16px;
  font-weight: 700;
  color: #00d4ff;
}

.stat-item.abnormal .stat-value {
  color: #ff0055;
}

.diagnosis-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.diagnosis-list::-webkit-scrollbar {
  width: 4px;
}

.diagnosis-list::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 2px;
}

.diagnosis-list::-webkit-scrollbar-thumb {
  background: rgba(0, 212, 255, 0.3);
  border-radius: 2px;
}

.diagnosis-list::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 212, 255, 0.5);
}

.diagnosis-item {
  background: rgba(0, 20, 40, 0.6);
  border: 1px solid rgba(0, 212, 255, 0.15);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
  transition: all 0.3s ease;
}

.diagnosis-item:hover {
  border-color: rgba(0, 212, 255, 0.3);
  background: rgba(0, 30, 60, 0.6);
}

.diagnosis-item.abnormal {
  border-color: rgba(255, 0, 85, 0.3);
  background: rgba(255, 0, 85, 0.05);
}

.diagnosis-item.abnormal:hover {
  border-color: rgba(255, 0, 85, 0.5);
  background: rgba(255, 0, 85, 0.1);
}

.item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.item-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

.item-status.normal {
  background: rgba(0, 255, 136, 0.1);
  color: #00ff88;
}

.item-status.abnormal {
  background: rgba(255, 0, 85, 0.15);
  color: #ff0055;
}

.status-icon {
  width: 14px;
  height: 14px;
}

.status-icon svg {
  width: 100%;
  height: 100%;
}

.item-time {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
}

.item-content {
  margin-bottom: 10px;
}

.item-filename {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
  margin-bottom: 6px;
}

.item-filename svg {
  width: 14px;
  height: 14px;
  color: #00d4ff;
}

.item-fault {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}

.fault-label {
  color: rgba(255, 255, 255, 0.4);
}

.fault-value {
  color: #ff0055;
  margin-left: 4px;
}

.item-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.3s ease;
  font-family: inherit;
}

.action-btn svg {
  width: 14px;
  height: 14px;
}

.action-btn.view {
  background: rgba(0, 212, 255, 0.1);
  border: 1px solid rgba(0, 212, 255, 0.3);
  color: #00d4ff;
}

.action-btn.view:hover {
  background: rgba(0, 212, 255, 0.2);
  border-color: #00d4ff;
}

.action-btn.download {
  background: rgba(0, 255, 136, 0.1);
  border: 1px solid rgba(0, 255, 136, 0.3);
  color: #00ff88;
}

.action-btn.download:hover {
  background: rgba(0, 255, 136, 0.2);
  border-color: #00ff88;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: rgba(255, 255, 255, 0.3);
}

.empty-state svg {
  width: 48px;
  height: 48px;
  margin-bottom: 15px;
  opacity: 0.5;
}

.empty-state span {
  font-size: 13px;
}

.empty-hint {
  font-size: 11px !important;
  color: rgba(255, 255, 255, 0.2);
  margin-top: 5px;
}

.diagnosis-detail-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(5px);
}

.modal-content {
  position: relative;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  background: linear-gradient(135deg, rgba(10, 20, 40, 0.98) 0%, rgba(5, 15, 30, 0.98) 100%);
  border: 1px solid rgba(0, 212, 255, 0.3);
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 0 50px rgba(0, 212, 255, 0.2);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 25px;
  border-bottom: 1px solid rgba(0, 212, 255, 0.15);
  background: rgba(0, 212, 255, 0.05);
}

.modal-title {
  font-size: 18px;
  font-weight: 600;
  color: #00d4ff;
  letter-spacing: 2px;
}

.modal-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  transition: all 0.3s ease;
}

.modal-close:hover {
  background: rgba(255, 0, 85, 0.1);
  border-color: rgba(255, 0, 85, 0.3);
  color: #ff0055;
}

.modal-close svg {
  width: 18px;
  height: 18px;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 25px;
}

.detail-section {
  margin-bottom: 25px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-section .section-title {
  font-size: 13px;
  font-weight: 600;
  color: #00d4ff;
  letter-spacing: 1px;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(0, 212, 255, 0.15);
}

.detail-row {
  display: flex;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-label {
  width: 100px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
}

.detail-value {
  flex: 1;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
}

.detail-value.normal {
  color: #00ff88;
}

.detail-value.abnormal {
  color: #ff0055;
}

.indicators-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.indicator-card {
  background: linear-gradient(135deg, rgba(0, 30, 60, 0.6) 0%, rgba(0, 20, 40, 0.8) 100%);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 12px;
  padding: 16px;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.indicator-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: linear-gradient(to bottom, #00d4ff, #00ff88);
  opacity: 0.6;
}

.indicator-card:hover {
  border-color: rgba(0, 212, 255, 0.4);
  transform: translateX(4px);
  box-shadow: 0 4px 20px rgba(0, 212, 255, 0.1);
}

.indicator-card.abnormal {
  border-color: rgba(255, 0, 85, 0.4);
  background: linear-gradient(135deg, rgba(255, 0, 85, 0.1) 0%, rgba(0, 20, 40, 0.8) 100%);
}

.indicator-card.abnormal::before {
  background: linear-gradient(to bottom, #ff0055, #ff6b00);
}

.indicator-card.abnormal:hover {
  border-color: rgba(255, 0, 85, 0.6);
  box-shadow: 0 4px 20px rgba(255, 0, 85, 0.15);
}

.indicator-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.indicator-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(0, 212, 255, 0.1);
  border: 1px solid rgba(0, 212, 255, 0.3);
  color: #00d4ff;
}

.indicator-icon.flow {
  background: rgba(0, 212, 255, 0.1);
  border-color: rgba(0, 212, 255, 0.3);
  color: #00d4ff;
}

.indicator-icon.speed {
  background: rgba(0, 255, 136, 0.1);
  border-color: rgba(0, 255, 136, 0.3);
  color: #00ff88;
}

.indicator-icon.pressure {
  background: rgba(255, 107, 0, 0.1);
  border-color: rgba(255, 107, 0, 0.3);
  color: #ff6b00;
}

.indicator-icon svg {
  width: 18px;
  height: 18px;
}

.indicator-status {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ff0055;
  animation: pulseWarning 1.5s ease-in-out infinite;
}

.indicator-status svg {
  width: 20px;
  height: 20px;
}

@keyframes pulseWarning {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(1.1); }
}

.indicator-body {
  margin-bottom: 10px;
}

.indicator-name {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.6);
  margin-bottom: 6px;
  line-height: 1.4;
}

.indicator-value {
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.5px;
}

.indicator-card.abnormal .indicator-value {
  color: #ff6b00;
}

.indicator-footer {
  display: flex;
  align-items: center;
  gap: 6px;
}

.indicator-reference {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
  padding: 4px 10px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.repair-advice {
  background: rgba(0, 20, 40, 0.5);
  border: 1px solid rgba(0, 212, 255, 0.1);
  border-radius: 8px;
  padding: 15px;
  font-size: 13px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.8);
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 25px;
  border-top: 1px solid rgba(0, 212, 255, 0.15);
  background: rgba(0, 0, 0, 0.2);
}

.footer-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.3s ease;
  font-family: inherit;
}

.footer-btn svg {
  width: 16px;
  height: 16px;
}

.footer-btn.download {
  background: linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(0, 255, 136, 0.1));
  border: 1px solid #00d4ff;
  color: #00d4ff;
}

.footer-btn.download:hover {
  background: linear-gradient(135deg, rgba(0, 212, 255, 0.3), rgba(0, 255, 136, 0.2));
  box-shadow: 0 0 20px rgba(0, 212, 255, 0.3);
}

.footer-btn.close {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.7);
}

.footer-btn.close:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}
</style>
