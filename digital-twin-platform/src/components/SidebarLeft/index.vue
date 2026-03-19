<template>
  <div class="sidebar2">

    <div class="sidebar-content">
      <!-- 统计信息卡片 -->

      <div class="card">
        <div style="
            display: flex;
            align-items: center;
            justify-content: space-between;
          ">
          <p class="title">统计信息</p>
          <!-- 数据类型切换按钮 -->
          <div style="display: flex; gap: 8px">
            <button :class="['mode-btn', dataType === 'experiment' ? 'active' : '']"
              @click="$emit('switchDataType', 'experiment')">
              实验数据
            </button>
            <button :class="['mode-btn', dataType === 'simulation' ? 'active' : '']"
              @click="$emit('switchDataType', 'simulation')">
              仿真数据
            </button>
          </div>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>指标/量</th>
              <th>最大值</th>
              <th>最小值</th>
              <th>均值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in featuresList" :key="item.title">
              <td>{{ item.title }}</td>
              <td>{{ item["max"].toFixed(2) }}</td>
              <td>{{ item["min"].toFixed(2) }}</td>
              <td>{{ item["mean"].toFixed(2) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  props: {
    featureMap: {
      type: Object,
      default: () => ({}),
    },
    dataType: {
      type: String,
      default: "experiment",
    },
  },
  data() {
    return {
      featuresList: [],
      options: [],
      placeholder: "过滤器",
      filter: [],
      optionsInitialized: false, // 新增：标记是否已初始化 options/filter
    };
  },
  watch: {
    featureMap: {
      handler(newVal) {
        console.log("左栏-数据：", newVal)
        // 只在未初始化时提取 options 和 filter
        if (!this.optionsInitialized && newVal && Object.keys(newVal).length) {
          this.options = Object.keys(newVal).map((key) => ({
            value: key,
            label: key,
          }));
          this.filter = this.options.map((item) => item.value);
          this.optionsInitialized = true;
        }
        // 生成 featuresList
        this.featuresList = this.options.map((item) => {
          const v = newVal[item.value];
          if (v && typeof v === "object" && v.max !== undefined) {
            return { title: item.value, max: v.max, min: v.min, mean: v.avg };
          } else if (typeof v === "number") {
            return { title: item.value, max: v, min: v, mean: v };
          } else {
            return { title: item.value, max: "-", min: "-", mean: "-" };
          }
        });
      },
      immediate: true,
      deep: true,
    },
  },
};
</script>

<style scoped>
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

.sidebar2 {
  display: flex;
  flex-direction: column;
  height: 100%;
  /* 关键：占满可用高度 */
  box-sizing: border-box;
  /* 移除你原有的 margin/padding !important，避免冲突 */
}

/* 滚动条样式 - 透明背景 */
.sidebar2::-webkit-scrollbar {
  width: 8px;
  background: transparent;
}

.sidebar2::-webkit-scrollbar-thumb {
  background: rgba(33, 112, 147, 0.3);
  border-radius: 4px;
}

.sidebar2 {
  scrollbar-color: rgba(33, 112, 147, 0.3) transparent;
  scrollbar-width: thin;
}

/* 滚动条背景透明 */
.sidebar2::-webkit-scrollbar {
  width: 8px;
  background: transparent;
}

.sidebar2::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.18);
  border-radius: 4px;
}

.sidebar-content::-webkit-scrollbar {
  width: 8px;
  background: transparent;
}

.sidebar-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.18);
  border-radius: 4px;
}

/* 兼容 Firefox */
.sidebar2,
.sidebar-content {
  scrollbar-color: rgba(255, 255, 255, 0.18) transparent;
  scrollbar-width: thin;
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
  /* justify-content: center; */
  align-items: center;
  /* padding-left: 7px; */
}

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

.card {
  /* background: rgba(255, 255, 255, 0.2); */
  border-radius: 15px;
  padding: 10px;
  margin-bottom: 20px;
  /* box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3); */
  transition: transform 0.3s ease;
  /* border: 0.01rem solid #217093; */
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
  line-height: 18px;
}

.title,
.card .title {
  color: #1976d2 !important;
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

.images .image {
  width: 100%;
  height: 100%;
  object-fit: cover;
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

.sidebar-content {
  flex: 1;
  overflow-y: auto;
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

.table {
  width: 100%;
  font-size: 15px;
}

th {
  color: #409eff;
}

.table {
  width: 100%;
  table-layout: auto;
  /* 根据内容自动分配宽度 */
  border-collapse: collapse;
  font-size: 14px;
}

.table th,
.table td {
  padding: 10px 8px;
  /* 增加上下左右内边距，解决拥挤 */
  text-align: center;
  white-space: nowrap;
  /* 默认不换行 */
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 第一列（指标名称）允许换行，防止过长 */
.table td:first-child,
.table th:first-child {
  white-space: normal;
  min-width: 100px;
  /* 最小宽度保障 */
  text-align: left;
}

/* 数值列保持紧凑但有最小宽度 */
.table td:not(:first-child),
.table th:not(:first-child) {
  min-width: 60px;
}

.table tr {
  line-height: 1.4;
  /* 改为相对值，更灵活 */
}

/* 可选：悬停效果 */
.table tr:hover {
  background-color: rgba(25, 118, 210, 0.05);
}

.table tr td:nth-child(1) {
  color: #1976d2 !important;
}

.table tr td:nth-child(2) {
  color: #e67c00 !important;
}

.table tr td:nth-child(3) {
  color: #53bf18 !important;
}

.table tr td:nth-child(4) {
  color: #12b0e9 !important;
}

.table tr td,
.table tr th {
  color: #1976d2 !important;
  background: transparent !important;
}

::v-deep input {
  background: transparent;
}

::v-deep .el-select__tags {
  display: none;
}

::v-deep .el-select {
  width: 170px;
}
</style>
