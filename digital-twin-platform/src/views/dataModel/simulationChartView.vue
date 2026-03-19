<template>
    <div class="app-container">
        <!-- 数据预览区域 -->
        <el-card class="box-card" :body-style="{ padding: '20px' }">
            <h3>数据预览</h3>
            <div v-if="previewData.length > 0" style="max-height: 200px; overflow: auto;">
                <el-table :data="previewData" size="mini" border style="width: 100%">
                   <el-table-column v-for="col in orderedColumns" :key="col.name" :prop="col.name" :label="col.name"
                        width="120">
                    </el-table-column>
                </el-table>
            </div>
            <span v-else>暂无数据</span>
        </el-card>

        <!-- 播放控制区域 -->
        <div style="margin-top: 15px;">
            <el-button size="mini" @click="startPlayback" :disabled="isPlaying">
                {{ isPlaying ? '播放中...' : '开始播放' }}
            </el-button>
            <el-button size="mini" @click="stopPlayback" :disabled="!isPlaying"> 停止 </el-button>
            <el-button size="mini" @click="resetPlayback"> 重置 </el-button>
        </div>

        <!-- 图表区域 -->
        <div class="chart-animation-container" style="margin-top: 20px;">
            <el-row :gutter="20">
                <!-- 直接在 el-col 上使用 v-for 和 key -->
                <el-col v-for="(group, idx) in chartGroups" :key="group.name" :xs="24" :sm="12" :md="12" :lg="12" :xl="12"
                    style="margin-bottom: 20px;">
                    <h4>{{ group.name }}趋势</h4>
                    <el-card class="chart-card" shadow="never">
                        <div :ref="'trendChart' + idx" style="width: 100%; height: 300px;"></div>
                    </el-card>
                </el-col>
            </el-row>
        </div>
    </div>
</template>

<script>
import * as echarts from 'echarts';

export default {
    name: 'simulationDataChartView',
    props: {
        // 从后端获取的原始数据（必须是对象数组）
        rawData: {
            type: Array,
            required: true,
            validator: value => {
                return Array.isArray(value) && value.length > 0 &&
                    typeof value[0] === 'object' && value[0] !== null;
            }
        },
        // 数据特征（可选，用于显示数据统计信息）
        dataFeatures: {
            type: Object,
            default: () => ({
                rowCount: 0,
                columnCount: 0,
                fileSize: '',
                lastModified: '',
                columns: []
            })
        }
    },
    data() {
        return {
            // 用于展示的前5行数据
            previewData: [],
            // 播放相关
            currentRowIndex: 0,
            playbackInterval: null,
            isPlaying: false,
            // 图表相关
            trendCharts: [],
            xCount: 0,
            maxLen: 20,
            dataBuffer: null,
            // 移除 GROUPS，改为 computed 动态生成
            // 定义分组（与原始详情页一致）
            // GROUPS: [
            //     { name: "转速", keys: ["输入燃油泵转速"] },
            //     { name: "供油流量", keys: ["供油流量1-1", "供油流量1-2"] },
            //     { name: "回油流量", keys: ["回油流量1-1", "回油流量1-2"] }
            // ]
        };
    },
    created() {
        this.initData();
    },
    computed: {
        orderedColumns() {
            // 安全访问：防止 dataFeatures 或 columns 未定义
            const cols = this.dataFeatures&&this.dataFeatures.columns || [];
            
            // 查找 "时间(s)" 列
            const timeCol = cols.find(col => col.name === "时间(s)");
            const otherCols = cols.filter(col => col.name !== "时间(s)");

            // 如果找到了时间列，放前面；否则保持原顺序
            if (timeCol) {
                return [timeCol, ...otherCols];
            } else {
                return cols; // 没有时间列就原样返回
            }
        },
        // 动态生成图表分组：每个非时间变量作为一个独立图表
        chartGroups() {
            const cols = this.dataFeatures&&this.dataFeatures.columns || [];
            const timeColName = '时间(s)'; // 或从 orderedColumns 推断
            const variableCols = cols
                .filter(col => col.name !== timeColName)
                .map(col => ({
                    name: col.name,     // 图表标题
                    keys: [col.name]    // 该图表包含的变量（单变量）
                }));
            return variableCols;
        }
    },
    methods: {
        // 初始化数据
        initData() {
            // 设置预览数据（前5行）
            this.previewData = this.rawData.slice(0, 5);

            // 初始化图表
            this.initTrendCharts();
        },

        // 初始化所有趋势图
        initTrendCharts() {
            this.trendCharts = [];
            this.dataBuffer = this.chartGroups.map(group => group.keys.map(() => []));

            this.$nextTick(() => {
                this.chartGroups.forEach((group, idx) => {
                    const refValue = this.$refs[`trendChart${idx}`];
                    const chartDom = Array.isArray(refValue) ? refValue[0] : refValue;
                    if (!chartDom) return;

                    const chart = echarts.init(chartDom);
                    chart.setOption(this.getChartOption(group, []));
                    this.trendCharts.push(chart);
                });
            });
        },

        // 获取初始配置
        getChartOption(group, seriesData) {
            return {
                title: {
                    text: group.name + "趋势",
                    left: 'center',
                    textStyle: { fontSize: 14 }
                },
                tooltip: { trigger: 'axis' },
                legend: { data: group.keys, top: 30 },
                xAxis: { type: 'value' },
                yAxis: { type: 'value' },
                series: group.keys.map((key, i) => ({
                    name: key,
                    type: 'line',
                    smooth: true,
                    data: seriesData[i] || []
                }))
            };
        },

        // 接收新数据并更新图表
        updateTrendChart(featureMap, currentTime) {
            if (!featureMap || !this.trendCharts.length) return;
            if (currentTime == null || isNaN(currentTime)) return;

            // 不再使用 xCount，直接用 currentTime
            this.chartGroups.forEach((group, gIdx) => {
                const chart = this.trendCharts[gIdx];
                if (!chart) return;

                group.keys.forEach((key, sIdx) => {
                    const val = featureMap[key]&&featureMap[key].avg;
                    if (typeof val !== 'number') return;

                    const buffer = this.dataBuffer[gIdx][sIdx];
                    // 存储 [真实时间, 值]
                    buffer.push([parseFloat(currentTime.toFixed(3)), parseFloat(val.toFixed(3))]);
                    if (buffer.length > this.maxLen) buffer.shift();
                });

                // 更新 X 轴范围：取当前 buffer 的时间范围
                const allTimes = this.dataBuffer[gIdx].flat().filter(item => Array.isArray(item)).map(item => item[0]);
                const minTime = allTimes.length ? Math.min(...allTimes) : 0;
                const maxTime = allTimes.length ? Math.max(...allTimes) : 0;

                chart.setOption({
                    xAxis: {
                        type: 'value', // 确保是数值轴
                        min: minTime,
                        max: maxTime,
                        axisLabel: { formatter: '{value}' }
                    },
                    series: group.keys.map((key, sIdx) => ({
                        name: key,
                        data: this.dataBuffer[gIdx][sIdx] || [],
                        type: 'line',
                        smooth: true,
                        // 启用数据点标记
                        symbol: 'circle',        // 点的形状：'circle', 'rect', 'triangle' 等
                        symbolSize: 6,           // 点的大小
                        showSymbol: true         // 确保始终显示（即使数据点密集）
                    }))
                }, false, true);
            });
        },

        // 开始播放
        startPlayback() {
            if (this.rawData.length === 0) {
                this.$message.warning('没有数据可播放');
                return;
            }

            this.isPlaying = true;
            this.currentRowIndex = 0;

            // 清除之前的模拟定时器
            clearInterval(this.playbackInterval);
            this.playbackInterval = null;

            // 启动播放
            this.playbackInterval = setInterval(() => {
                if (this.currentRowIndex >= this.rawData.length) {
                    this.stopPlayback();
                    return;
                }

                const currentRow = this.rawData[this.currentRowIndex];
                const currentTime = currentRow['时间(s)']; 

                // 转换为 featureMap 格式
                const featureMap = {};
                this.chartGroups.forEach(group => {
                    group.keys.forEach(key => {
                        const value = currentRow[key];
                        if (typeof value === 'number') {
                            featureMap[key] = { avg: value };
                        }
                    });
                });

                // 更新图表
                this.updateTrendChart(featureMap, currentTime);
                this.currentRowIndex++;
            }, 1000); // 每 1000ms 播放一行
        },

        // 停止播放
        stopPlayback() {
            if (this.playbackInterval) {
                clearInterval(this.playbackInterval);
                this.playbackInterval = null;
            }
            this.isPlaying = false;
        },

        // 重置播放
        resetPlayback() {
            this.stopPlayback();
            this.currentRowIndex = 0;
            // 重置 x 轴计数器
            this.xCount = 0;
            // 清空数据缓冲
            this.dataBuffer = this.chartGroups.map(group => group.keys.map(() => []));

            // 重置图表
            this.disposeTrendCharts();
            this.initTrendCharts();
        },

        // 销毁图表
        disposeTrendCharts() {
            this.trendCharts.forEach(c => {
                if (c && typeof c.dispose === 'function') {
                    c.dispose();
                }
            });
            this.trendCharts = [];
        }
    },
    beforeDestroy() {
        this.disposeTrendCharts();
        this.stopPlayback();
    }
};
</script>

<style lang="scss" scoped>
.chart-animation-container {
    margin-top: 20px;
}

.chart-card {
    height: 100%;
}

.chart-container {
    .chart-placeholder {
        min-height: 300px;
        display: flex;
        align-items: center;
        justify-content: center;
        background-color: #f9f9f9;
        border-radius: 4px;
    }
}
</style>