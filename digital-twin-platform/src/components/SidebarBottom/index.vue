<template>
  <div class="sidebar3">
    <div class="sidebar-content">
      <div style="
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 20px;
          margin-bottom: 10px;
        ">
        <div>
          <p class="title">趋势图</p>
        </div>
        <!-- <el-select
          v-model="filter"
          :placeholder="placeholder"
          size="mini"
          collapse-tags
          clearable
        >
          <el-option
            v-for="item in groupOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          >
          </el-option>
        </el-select> -->
      </div>
      <div class="chart-container">
        <div v-for="(group, idx) in showGroups" :key="group.name">
          <div :ref="'lineChart' + idx" :style="{
            height:
              (group.chartConfig && group.chartConfig.height) || '320px',
            width: (group.chartConfig && group.chartConfig.width) || '300px',
          }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import index from "dat.gui";
import * as echarts from "echarts";

const GROUPS = [
  {
    name: "压力",
    keys: ["P1进口压力", "P17滑油压力", "P2低压出口压力", "P3高压出口压力"],
    chartConfig: {
      width: "300px",
      height: "320px",
    },
  },
  {
    name: "温度",
    keys: ["供油温度1-1", "供油温度1-2", "回油温度1-1", "回油温度1-2"],
    chartConfig: {
      width: "300px",
      height: "320px",
    },
  },
  // {
  //   name: "流量",
  //   keys: ["排油流量FM1/L/h", "回油流量FM2/L/h"],
  //   chartConfig: {
  //     width: "300px",
  //     height: "280px"
  //   }
  // },
  // ...可扩展更多分组...
];

export default {
  props: {
    featureMap: Object,
  },
  data() {
    return {
      GROUPS,
      charts: [],
      xCount: 0,
      maxLen: 20,
      filter: null, // 默认显示全部分组
      placeholder: "选择数据类型",
    };
  },
  computed: {
    groupOptions() {
      return this.GROUPS.map((g) => ({ value: g.name, label: g.name }));
    },
    showGroups() {
      // 如果未选filter则显示全部
      if (!this.filter) return this.GROUPS;
      return this.GROUPS.filter((g) => g.name === this.filter);
    },
  },
  watch: {
    featureMap: {
      handler(newVal) {
        if (!newVal || typeof newVal !== "object") return;
        this.appendFeatureMap(newVal);
      },
      immediate: true,
      deep: false,
    },
    filter() {
      this.$nextTick(() => {
        this.resizeCharts();
      });
    },
  },
  mounted() {
    // 初始化所有图表
    this.charts = this.GROUPS.map((group, idx) => {
      const refArr = this.$refs["lineChart" + idx];
      const dom = Array.isArray(refArr) ? refArr[0] : refArr;
      const chart = echarts.init(dom);
      chart.setOption(this.getInitOption(group));
      return chart;
    });
  },
  beforeDestroy() {
    this.charts.forEach((c) => c && c.dispose());
  },
  methods: {
    getInitOption(group) {
      const colorList = [
        "#5470c6",
        "#91cc75",
        "#fac858",
        "#ee6666",
        "#73c0de",
        "#3ba272",
        "#fc8452",
        "#9a60b4",
        "#ea7ccc",
      ];
      return {
        // title: {
        //   text: group.name + "数据趋势",
        //   left: "center",
        //   textStyle: { fontSize: 18, color: "#222", fontWeight: "bold" },
        // },
        legend: {
          show: true,
          // top: 10,
          left: "center",
          orient: "horizontal",
          textStyle: { color: "#dbe9fd", fontSize: 13 },
          icon: "circle",
          itemGap: 16,
          width: "20px",
          formatter: function (name) {
            return name;
          },
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          backgroundColor: '#1d2530',
          borderColor: '#1976d2',
          borderWidth: 1,
          textStyle: { color: '#dbe9fd', fontSize: 14 },
          extraCssText: `
            position: fixed !important;
            z-index: 2147483647 !important;
            box-shadow: 0 2px 12px rgba(0,0,0,0.15);
            padding: 8px 12px;
            pointer-events: none; /* 防止遮挡鼠标 */
          `,
          // position: [500, 500],
          position: function (point, params, dom, rect, size) {
            // point 是鼠标在图表内的坐标（相对于图表容器）
            // 但我们用 fixed 定位，需要转为视口坐标

            // const chartContainer = dom.closest('.echarts'); // 找到 ECharts 容器
            // if (!chartContainer) return point;

            // const containerRect = chartContainer.getBoundingClientRect();
            let x = point[0] + 1350;
            let y = point[1] + 80;
            if (point[1] > 100) {
              y = y + 250;
            }


            // 防止超出视口右侧
            if (x + size.contentSize[0] > window.innerWidth) {
              x = window.innerWidth - size.contentSize[0] - 10;
            }
            // 防止超出视口底部
            if (y + size.contentSize[1] > window.innerHeight) {
              y = window.innerHeight - size.contentSize[1] - 10;
            }
            // 防止跑到顶部以上
            if (y < 0) y = 0;

            return [x, y];
          }
        },
        color: colorList,
        grid: { left: 60, bottom: "5%", top: 120 },
        xAxis: {
          type: "value",
          axisLabel: { show: false, color: "#dbe9fd" },
          axisLine: { show: false },
          splitLine: { show: false },
        },
        yAxis: {
          type: "value",
          axisLabel: {
            color: "#dbe9fd",
            fontSize: 14,
          },
          axisLine: { lineStyle: { color: "#ddd" } },
          splitLine: { lineStyle: { color: "#eee" } },
        },
        series: group.keys.map((k) => ({
          name: k,
          data: [],
          type: "line",
          smooth: true,
          symbol: "none",
        })),
      };
    },
    appendFeatureMap(featureMap) {
      this.xCount += 1;
      if (!this.dataBuffer) {
        this.dataBuffer = this.GROUPS.map((group) => group.keys.map(() => []));
      }
      this.GROUPS.forEach((group, gidx) => {
        const chart = this.charts[gidx];
        if (!chart) return;
        group.keys.forEach((key, sidx) => {
          const v = featureMap[key];
          if (v && typeof v.avg === "number") {
            if (!this.dataBuffer[gidx][sidx]) this.dataBuffer[gidx][sidx] = [];
            this.dataBuffer[gidx][sidx].push([
              this.xCount,
              Number(v.avg.toFixed(5)),
            ]);
            if (this.dataBuffer[gidx][sidx].length > this.maxLen)
              this.dataBuffer[gidx][sidx].shift();
          }
        });
        const series = group.keys.map((k, sidx) => ({
          name: k,
          data: (this.dataBuffer[gidx][sidx] || []).slice(),
          type: "line",
          smooth: true,
          symbol: "none",
        }));
        chart.setOption(
          {
            series,
            xAxis: {
              min: Math.max(1, this.xCount - this.maxLen + 1),
              max: this.xCount,
            },
            animation: false,
          },
          false,
          true
        );
      });
    },
    resizeCharts() {
      this.$nextTick(() => {
        this.charts.forEach((chart, idx) => {
          if (chart) chart.resize();
        });
      });
    },
  },
};
</script>

<style scoped>
.sidebar3 {
  box-sizing: border-box;
  /* border: 1px solid #00cc44 !important; */
  margin: 0 !important;
  padding: 0 !important;
  color: #dbe9fd;
  transition: box-shadow 0.2s;
  width: 100%;
  height: 100%;

  overflow: visible !important;
}

.sidebar3::-webkit-scrollbar {
  width: 8px;
  background: transparent;
}

.sidebar3::-webkit-scrollbar-thumb {
  background: rgba(33, 112, 147, 0.3);
  border-radius: 4px;
}

.sidebar3 {
  scrollbar-color: rgba(33, 112, 147, 0.3) transparent;
  scrollbar-width: thin;
}

.sidebar-content {
  overflow-x: auto;
  display: flex;
  flex-direction: column;
  overflow: visible !important;
}

.chart-container {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 30px;
}

.sidebar-bottom {
  color: #dbe9fd !important;
}

.title {
  color: #fff;
  font-weight: 600;
  text-align: center;
  font-size: 18px;
}

.title,
.card .title {
  color: #1976d2 !important;
}
</style>
<style>
.echarts-tooltip {
  z-index: 9999 !important;
}

/* 或更通用的选择器 */
.xAxisPointer,
.ec-tooltip {
  z-index: 9999 !important;
}
</style>