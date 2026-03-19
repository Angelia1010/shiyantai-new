<template>
  <div class="sidebar">
    <div style="display: flex; align-items: center; gap: 20px">
      <div>
        <p class="title">频谱图</p>
      </div>
      <el-select v-model="filter" single :placeholder="placeholder" size="mini" collapse-tags ref="selectRef">
        <el-option v-for="item in options" :key="item.value" :label="item.label" :value="item.value">
        </el-option>
      </el-select>
    </div>
    <div class="spectrumContainer">
      <div v-for="item in options" :key="item.value" v-show="filter.includes(item.value)">
        <div :ref="`lineChart${item.value}`" style="height: 250px; width: 300px" class="chart"></div>
      </div>
    </div>
  </div>
</template>

<script>
import * as echarts from "echarts";
import { options } from "runjs";

export default {
  props: {
    spectrum: {
      type: Object, // spectrumMap
      required: true, // 确保父组件一定传递了该 prop
    },
  },
  data() {
    return {
      options: [
        { value: "供油压力PT2/MPa", label: "供油压力PT2/MPa" },
        { value: "控制口压力PT3/MPa", label: "控制口压力PT3/MPa" },
        { value: "排油口压力PT4/MPa", label: "排油口压力PT4/MPa" },
        { value: "出油口压力PT5/MPa", label: "出油口压力PT5/MPa" },
        { value: "振动X/m/s2", label: "振动X/m/s2" },
        { value: "振动Y/m/s2", label: "振动Y/m/s2" },
        { value: "振动Z/m/s2", label: "振动Z/m/s2" },
        { value: "排油流量FM1/L/h", label: "排油流量FM1/L/h" },
        { value: "回油流量FM2/L/h", label: "回油流量FM2/L/h" },
        { value: "供油温度RTD2/℃", label: "供油温度RTD2/℃" },
        { value: "排油口温度RTD4/℃", label: "排油口温度RTD4/℃" },
        { value: "出油口温度RTD5/℃", label: "出油口温度RTD5/℃" },
        { value: "控制口温度RTD3/℃", label: "控制口温度RTD3/℃" },
        { value: "转速/RPM", label: "转速/RPM" },
        { value: "转矩/N.M", label: "转矩/N.M" },
        { value: "排油质量流量/Kg/h", label: "排油质量流量/Kg/h" },
        { value: "回油质量流量/Kg/h", label: "回油质量流量/Kg/h" },
      ],
      placeholder: "过滤器",
      filter: ["供油压力PT2/MPa"], // 默认只展示第一个图
      chartList: [],
    };
  },
  mounted() {
    this.$nextTick(() => {
      this.options.forEach((item) => {
        const refKey = `lineChart${item.value}`;
        const refArr = this.$refs[refKey];
        if (!refArr || !refArr[0]) return;
        const dom = refArr[0];
        // 只初始化可见的（filter中有的）
        if (this.filter.includes(item.value)) {
          const chart = echarts.init(dom);
          this.chartList.push(chart);
        } else {
          this.chartList.push(null);
        }
      });
      this.filter = [this.options[0].value];
      this.drawChart();
    });
  },
  watch: {
    spectrum: {
      handler() {
        this.drawChart();
      },
      deep: true,
    },
    filter() {
      this.drawChart();
    },
  },
  methods: {
    drawChart() {
      console.log("动态图表spectrum：", this.spectrum)
      if (!this.spectrum) return;
      this.options.forEach((item, index) => {
        if (!this.filter.includes(item.value)) return;
        let chart = this.chartList[index];
        // 动态初始化未初始化的chart
        if (!chart) {
          const refKey = `lineChart${item.value}`;
          const refArr = this.$refs[refKey];
          if (refArr && refArr[0]) {
            chart = echarts.init(refArr[0]);
            this.chartList[index] = chart;
          } else {
            return;
          }
        }
        const spectrumObj = this.spectrum[item.value];
        if (!spectrumObj) return;
        const option = {
          // title: {
          //   text: `${item.value}频谱图`,
          //   left: "center",
          //   textStyle: {
          //     fontSize: 18,
          //     color: "#222",
          //     fontWeight: "bold",
          //   },
          // },
          legend: {
            show: false,
            textStyle: { color: "#222", fontSize: 13 },
          },
          tooltip: {
            trigger: "axis",
            axisPointer: { type: "shadow" },
            backgroundColor: "#fff",
            borderColor: "#1976d2",
            borderWidth: 1,
            textStyle: { color: "#222", fontSize: 14 },
            extraCssText:
              "box-shadow:0 2px 8px rgba(0,0,0,0.08);padding:8px 12px;",
          },
          grid: { left: 60, bottom: "10%", top: 10 },

          xAxis: {
            type: "value",
            axisLabel: {
              color: "#222",
              fontSize: 14,
              formatter: "{value} Hz",
            },
            axisLine: { lineStyle: { color: "#ddd" } },
          },
          yAxis: {
            type: "value",
            axisLabel: { color: "#222", fontSize: 14 },
            axisLine: { lineStyle: { color: "#ddd" } },
            splitLine: { lineStyle: { color: "#eee" } },
          },
          series: [
            {
              name: item.value,
              data: spectrumObj.freqs.map((freq, i) => [
                freq,
                spectrumObj.spectrum[i] != null
                  ? spectrumObj.spectrum[i].toFixed(4)
                  : null,
              ]),
              type: "line",
              showSymbol: false, // 不显示点
              itemStyle: { color: "rgb(54, 162, 235)" },
              areaStyle: undefined,
            },
          ],
        };
        chart.setOption(option);
      });
    },
    handleSelectChange() {
      const input =
        this.$refs.selectRef &&
        this.$refs.selectRef.$el &&
        this.$refs.selectRef.$el.querySelector(".el-input__inner");

      if (input) {
        // 手动设置 placeholder
        input.setAttribute("placeholder", this.placeholder);
      }
    },
  },
};
</script>

<style scoped>
.sidebar {
  box-sizing: border-box;
  /* border: 1px solid #00cc44 !important;  */
  padding: 0 !important;
  color: #222;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: auto;
  align-items: center;
}

/* Custom scrollbar styles for sidebar-content */
.sidebar-content::-webkit-scrollbar {
  width: 8px !important;
}

.sidebar-content::-webkit-scrollbar-thumb {
  background-color: rgba(255,
      255,
      255,
      0.3) !important;
  /* Semi-transparent thumb */
  border-radius: 4px;
  /* Rounded edges for better visibility */
}

.sidebar-content::-webkit-scrollbar-track {
  background-color: rgba(255,
      255,
      255,
      0.1) !important;
  /* Semi-transparent track */
}

@keyframes fadeIn {
  0% {
    opacity: 0;
    transform: translateX(100%);
  }

  100% {
    opacity: 1;
    transform: translateX(0);
  }
}

.sidebar-header {
  position: relative;
  display: flex;
  align-items: center;
}

/* 其余内容和滚动条样式保留 */

h3 {
  background: url(./titleioc.png) left center no-repeat;
  text-indent: 27px;
  line-height: 30px;
}

.close-btn {
  background: transparent;
  color: white;
  border: none;
  font-size: 30px;
  cursor: pointer;
  transition: color 0.3s ease;
  position: absolute;
  right: 0;
  top: 10px;
}

.close-btn:hover {
  color: #ff0;
}

/* .card {
  border-radius: 15px;
  padding: 20px;
  margin-bottom: 20px;
  transition: transform 0.3s ease;
} */

.card {
  display: flex;
  flex-direction: column;
  align-items: center;
  /* background: rgba(255, 255, 255, 0.2); */
  border-radius: 15px;
  padding: 20px;
  margin-bottom: 20px;
  /* box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3); */
  transition: transform 0.3s ease;
  /* border: 0.01rem solid #217093; */
  width: 400px;
  float: none;
  /* Remove float to avoid layout issues */
  margin-right: 0;
  /* Reset margin to ensure proper centering */
  flex: 0 0 auto;
  /* Ensure the card respects flexbox alignment */
}

.card:hover {
  cursor: pointer;
}

.card p {
  margin: 10px 0;
}

.card strong {
  color: #00ff9d;
}

.chart {
  margin-top: 20px;
}

.title {
  color: #fff;
  font-weight: 600;
  text-align: center;
  font-size: 18px;
}

.images {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.image-container {
  width: 120px;
  height: 120px;
  overflow: hidden;
  border-radius: 10px;
  box-shadow: 0 0 15px rgba(0, 0, 0, 0.2);
  transition: transform 0.3s ease;
}

.image-container:hover {
  transform: scale(1.1);
}

.sidebar-enter-active,
.sidebar-leave-active {
  transition: transform 0.5s ease-in-out;
}

.sidebar-enter,
.sidebar-leave-to {
  transform: translateX(100%);
}

.card:last-child {
  margin-bottom: 70px;
}

.el-dropdown-link {
  cursor: pointer;
  color: #217093;
  margin-left: 10px;
  font-weight: 500;
}

.el-icon-arrow-down {
  font-size: 12px;
}

.el-popper.dropdownMenu {
  background-color: #217093;
  border: 1px solid #217093;

  .el-dropdown-menu__item {
    color: #fff !important;
  }

  .popper__arrow::after {
    border-bottom-color: #217093 !important;
    border-top-color: #217093 !important;
  }

  .el-dropdown-menu__item:not(.is-disabled):hover {
    background: #217093 !important;
  }
}

::v-deep input {
  background: transparent;
}

::v-deep .el-select__tags {
  display: none;
}

.spectrumContainer {
  display: flex;
  flex-direction: column;
  align-items: center;
  /* Center charts horizontally */
  justify-content: center;
  /* Center charts vertically */
  width: 100%;
  /* Ensure it spans the full width of the parent */
  max-width: 100%;
  /* Ensure it does not exceed the parent's width */
  box-sizing: border-box;
  /* Include padding and border in width calculation */
}

.sidebar {
  color: #222 !important;
}

.title,
.card .title {
  color: #1976d2 !important;
}
</style>
