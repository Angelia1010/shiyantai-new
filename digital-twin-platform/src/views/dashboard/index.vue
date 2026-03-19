<template>
  <div class="dashboard-grid">
    <div class="dashboard-title">标准试验台数字化校验系统</div>
    <!-- 第一行：SidebarLeft | 模型区 | Sidebar + SidebarBottom -->
    <div class="sidebar-left-cell">
      <div class="dashboard-card sidebar-left">
        <SidebarLeft :featureMap="featureMap" :dataType="dataType" @switchDataType="switchDataType" />
      </div>
    </div>
    <div class="model-area-cell">
      <div class="model-area-grid">
        <!-- 先显示3D模型 -->
        <div class="model-3d-row">
          <PumpModel ref="pumpModelRef" />
        </div>
        <!-- 再显示渐变条+PumpModel2D -->
        <div class="model-2d-row">
          <div class="pump2d-gradient-bar-wrap">
            <div class="mode-switch-bar">
              <button :class="['mode-btn', mode === 'temperature' ? 'active' : '']" @click="mode = 'temperature'">
                温度
              </button>
              <button :class="['mode-btn', mode === 'pressure' ? 'active' : '']" @click="mode = 'pressure'">
                压力
              </button>
            </div>
            <div class="gradient-bar">
              <div class="bar-label bar-label-top">
                {{ mode === "pressure" ? "35MPa" : "90°C" }}
              </div>
              <div class="bar-gradient" :style="{
                background:
                  mode === 'pressure'
                    ? pressureGradient
                    : temperatureGradient,
              }"></div>
              <div class="bar-label bar-label-bottom">
                {{ mode === "pressure" ? "2MPa" : "20°C" }}
              </div>
            </div>
          </div>
          <div class="pump2d-list">
            <div v-for="port in ['供油1-1', '供油1-2', '回油1-1', '回油1-2']" :key="port">
              <PumpModel2D :portName="port" :featureMap="featureMap" :viewDirection="'z'" :mode="mode" />
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="sidebar-cell">
      <div class="dashboard-card">
        <SidebarBottom :featureMap="sidebarBottomFeatureMap" />
      </div>
    </div>
    <!-- 悬浮AI助手 -->
    <AIChater />
  </div>
</template>

<script>
import SidebarLeft from "@/components/SidebarLeft";
import SidebarBottom from "@/components/SidebarBottom";
import Sidebar from "@/components/Sidebar";
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
import AIChater from "@/components/AI/AIChater.vue";
import { stopJob } from "@/api/article";
import { Message } from "element-ui";
import PumpModel from "./PumpModel.vue";
import PumpModel2D from "./PumpModel2D.vue";

export default {
  components: {
    Sidebar,
    SidebarBottom,
    SidebarLeft,
    AIChater,
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
      timerId: null, // 定时器ID
      fileNames: [],
      fileNameIndex: 0,

      isRunning: true, // Flag to control the run loop

      featureMap: {}, // 当前消费到的 featureMap（PumpModel/PumpModel2D 用）
      sidebarBottomFeatureMap: {}, // SidebarBottom 用，延迟更新
      queueThreshold: 60, // 队列阈值
      spectrumQueue: [], // 斜盘角度和转速队列
      featuresQueue: [], // 特征队列
      featuresConsumerTimer: null, // 定时器ID
      spectrum: {}, // 当前消费到的频谱数据
      groupSize: 50, // 每组数据大小
      spectrumIndex: 0,

      mode: "temperature",
      pumpState: { swashAngle: 0, rotateSpeed: 0 }, // 补充初始化，防止未定义报错
      dataType: "experiment", // 'experiment' or 'simulation'
    };
  },
  computed: {
    temperatureGradient() {
      // 蓝-青-绿-黄-橙-红
      return "linear-gradient(to bottom, #ff0000 0%, #ff8000 20%, #ffff00 40%, #00ff00 60%, #00ffff 80%, #0066ff 100%)";
    },
    pressureGradient() {
      // 蓝-青-绿-黄-橙-红
      return "linear-gradient(to bottom, #ff0000 0%, #ff8000 20%, #ffff00 40%, #00ff00 60%, #00ffff 80%, #0066ff 100%)";
    },
  },
  created() {
    window.addEventListener("message", this.iframeEventListener);
    window.hideLoading = () => {
      this.showLoading = false;
    };

    // Extract URL parameters
    const hash = window.location.hash.substring(1); // Remove the '#' character
    const urlParams = new URLSearchParams(hash.split("?")[1]); // Extract the query string after '?'
    this.type = urlParams.get("type") || null;
    this.path = urlParams.get("path") || null;
    this.fault = urlParams.get("fault") || null;
    this.selectedItems = urlParams.get("selectedItems")
      ? urlParams.get("selectedItems").split(",")
      : [];

    console.log("urlParams:", urlParams);
    console.log("type:", this.type);
    console.log("path:", this.path);
    console.log("fault:", this.fault);
    console.log("selectedItems:", this.selectedItems);
  },
  mounted() {
    this.run();
    // 新增：每秒消费 featuresQueue 和 swashAngleQueue
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
    this.isRunning = false; // Stop the run loop when the component is destroyed
    window.removeEventListener("message", this.iframeEventListener);
    // 清理定时器
    if (this.featuresConsumerTimer) {
      clearInterval(this.featuresConsumerTimer);
      this.featuresConsumerTimer = null;
    }
  },
  methods: {
    async sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    },

    async run() {
      // Check the flag to continue or stop the loop
      console.log("开始获取任务");
      if (!this.type || !this.path || !this.selectedItems) {
        console.log("参数不完整，停止任务");
        return;
      }
      //log type, path, selectedItems
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
                  // 新增：生成唯一 task_id
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

                // 再开始处理数据
                await this.updateData(filename, this.path);
              }
            }
            await this.sleep(5000); // Sleep for 5 seconds
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
      // 新增：featuresQueue长度判断，若大于等于阈值则直接返回

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
          await this.sleep(1000); // Sleep for 1 second
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
      // 临时模拟数据 - 当后端接口有问题时使用
      const useMockData = false; // 设置为 false 以使用真实接口

      if (useMockData) {
        // 模拟延迟
        await this.sleep(200);

        // 模拟分页数据，每页最多返回 500 条数据
        const totalPages = 5; // 模拟总共5页数据
        if (requestReq.page >= totalPages) {
          return false; // 没有更多数据
        }

        console.log(`[Mock] 返回第 ${requestReq.page} 页模拟数据`);

        // 生成模拟数据
        const mockResponse = this.generateMockData(requestReq);

        // 使用模拟数据继续后续处理逻辑
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

        // 处理模拟数据
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

      // 真实接口调用（当 useMockData 为 false 时）
      try {
        console.log("数据请求体：", requestReq);
        const response = await readExcelApi(requestReq);
        console
        // 适配新结构，选择实验或仿真数据
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
        // 接口失败时自动切换到模拟数据
        return this.loadDataNew({ ...requestReq, useMockData: true });
      }
    },

    switchDataType(type) {
      this.dataType = type;
      this.featuresQueue = [];
      this.featureMap = {};
      this.sidebarBottomFeatureMap = {};
      this.page = 0;
      // 重新拉取数据
      this.run();
    },

    // iframeEventListener(event) {
    //   if (event.data.type === "workbench") {
    //     console.log(event.data.modelData.name);
    //     let pumpData = ["Mesh_500001"];

    //     let name = event.data.modelData.name;
    //     // console.log("pump", name);
    //     // 泵的跳转
    //     if (pumpData.includes(name)) {
    //       this.$router.push({ path: "/model" });
    //     }
    //     if (event.data.modelData.name === "输入1_504") {
    //     }
    //   }
    // },
    /**
     * 生成模拟数据
     */
    generateMockData(requestReq) {
      const filename = requestReq.file_name[0] || "mock_file.xlsx";
      const page = requestReq.page || 0;

      // 生成每页500条数据
      const dataSize = requestReq.page_size || 500;

      // 模拟字段数据生成器
      const generateFieldData = (baseValue, variance = 0.1, trend = 0) => {
        const data = [];
        for (let i = 0; i < dataSize; i++) {
          // 添加随机波动和趋势
          const randomFactor = 1 + (Math.random() - 0.5) * variance;
          const trendFactor = 1 + (trend * i) / dataSize;
          const value = baseValue * randomFactor * trendFactor;
          data.push(Number(value.toFixed(3)));
        }
        return data;
      };

      // 生成时间序列数据，模拟真实传感器数据
      const timeOffset = page * dataSize;

      const mockData = {
        [filename]: {
          1: {
            // 实验数据
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
            // 仿真数据（稍微不同的数值范围）
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
.dashboard-title {
  grid-column: 1 / -1;
  text-align: center;
  font-size: 26px;
  font-weight: bold;
  color: #1976d2 !important;
  letter-spacing: 2px;
  margin: 18px 0 10px 0;
  /* text-shadow: 0 0 18px #00d8ff; */
}

.dashboard-grid {
  display: grid;
  grid-template-rows: auto 1fr;
  /* 第一行：标题 | 第二行：SidebarLeft | 模型区 | Sidebar + SidebarBottom */
  grid-template-columns: 400px 1fr auto;
  /* 三列：左侧边栏 | 模型区 | 右侧边栏 */
  grid-template-areas:
    ". title ."
    "sidebar-left model-area sidebar";
  width: 100%;
  height: 100%;
  background: #1d2530;
  position: relative;
  /* gap: 10px; */
  /* padding: 10px; */
}

.sidebar-left-cell {
  grid-column: 1 / -1;
  grid-area: sidebar-left;
  overflow: visible;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  background: none;
  box-shadow: none;
  padding: 0;
}

.sidebar-left {
  height: 100%;
}

.model-area-cell {
  grid-area: model-area;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  height: 100%;
  background: none;
  box-shadow: none;
  padding: 0;
}

.sidebar-cell {
  grid-area: sidebar;
  overflow: visible;
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
  justify-content: flex-start;
  background: none;
  box-shadow: none;
  /* padding: 10px; */
  min-width: 0 !important;
  /* 修正：允许收缩，防止溢出 */
  max-width: 100% !important;
}

.model-area-grid {
  display: grid;
  grid-template-rows: 1fr auto;
  /* 3D区填满剩余空间，2D区自适应高度 */
  width: 100%;
  height: 100%;
  align-items: center;
  justify-items: center;
  /* border: 2px solid #696eff !important; */
}

.model-2d-row {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 24px;
  margin-bottom: 16px;
}

.pump2d-list {
  display: flex;
  flex-direction: row;
  gap: 16px;
}

.model-3d-row {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  /* 填满grid剩余空间 */
  min-height: 0;
  /* 防止塌陷 */
}

/* 保留原有的渐变条和按钮样式 */
.pump2d-gradient-bar-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-right: 0;
  width: 24px;
}

.mode-switch-bar {
  display: flex;
  flex-direction: row;
  gap: 0;
  margin-bottom: 10px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.mode-btn {
  background: transparent;
  border: 1px solid #1976d2;
  border-radius: 0;
  padding: 4px 10px;
  font-size: 13px;
  color: #1976d2 !important;
  cursor: pointer;
  outline: none;
  transition: background 0.2s, color 0.2s, border 0.2s;
  margin: 0;
  flex-shrink: 0;
  min-width: 40px;
  max-width: 80px;
}

.mode-btn.active {
  background: #1976d2;
  color: #fff !important;
  border: 1px solid #1976d2;
}

.gradient-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 10px;
  height: 100px;
  position: relative;
  justify-content: center;
}

.bar-gradient {
  width: 100%;
  height: 80px;
  border-radius: 2px;
  margin: 0 0 0 0;
  border: 1px solid #1976d2;
}

.bar-label {
  font-size: 12px;
  color: #1976d2 !important;
  font-weight: bold;
  text-align: center;
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.bar-label-top {
  margin-bottom: 2px;
}

.bar-label-bottom {
  margin-top: 2px;
}

.dashboard-grid,
.sidebar-left-cell,
.model-area-cell,
.sidebar-cell {
  /* 允许内容溢出时显示滚动条，防止塌陷 */
  min-height: 0 !important;
  min-width: 0 !important;
  overflow: auto !important;
  /* border: 2px solid #ff69b4 !important; */
  padding: 10px;
}

/* 保证按钮、渐变条等局部样式不受影响 */
.mode-btn,
.gradient-bar,
.bar-label,
.bar-gradient {
  border: none !important;
  margin: 0 !important;
  padding: 0 !important;
}

/* Card style for all dashboard cards (sidebars, bottom bar, 2D model) */
.dashboard-card {
  background: #1d2530;
  border-radius: 14px;
  box-shadow: 4.5px 4.5px 6px rgba(0, 0, 0, 0.3);
  box-sizing: border-box;
  border: 1.5px solid #e0e4ea;
  margin: 0;
  padding: 10px;
  transition: box-shadow 0.2s, border-color 0.2s;
}

/* .dashboard-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.13);
  border-color: #00cc44;
} */
.sidebar-cell {
  min-width: 0 !important;
}

.dashboard-card>*,
.sidebar-content,
.chart-container,
.chart {
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
}
</style>
