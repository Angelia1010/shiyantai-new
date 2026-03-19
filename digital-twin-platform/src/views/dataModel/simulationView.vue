<template>
    <div style="height: 100vh; overflow-y: auto;">
        <!-- 新增：顶部图片 -->
       <img src="/model/AmesimModel.png" alt="Header" style="width: 100%; height: auto; display: block;" />
        <!-- 新增：AMESim 控制面板 -->
        <div style="padding: 16px; background-color: #f5f7fa; border-bottom: 1px solid #e8eaec; ">
            <el-row :gutter="12" align="middle">
                <el-col :span="8">
                    <el-input v-model="amesimFilePath" placeholder="请输入 AMESim 模型文件路径（如 test.ame）" clearable>
                        <template #prepend>模型路径</template>
                    </el-input>
                </el-col>
                <el-col :span="16">
                    <el-button-group>
                        <el-button type="primary" @click="handleOpenModel" :loading="loadingAction === 'open'">
                            打开模型
                        </el-button>
                        <el-button type="success" @click="handleRunSimulation" :loading="loadingAction === 'run'"
                            :disabled="!modelOpened">
                            运行仿真
                        </el-button>
                        <el-button @click="handleCloseModel" :loading="loadingAction === 'close'"
                            :disabled="!modelOpened">
                            关闭模型
                        </el-button>
                        <el-button @click="resetAll">重置</el-button>
                    </el-button-group>
                </el-col>
            </el-row>
            <div v-if="message" style="margin-top: 8px; color: #606266; font-size: 14px;">
                {{ message }}
            </div>
            <!-- 变量配置表单（仅当模型已打开时显示） -->
            <div v-if="modelOpened" style="padding: 16px; background-color: #f9fafb; border-bottom: 1px solid #e8eaec;">
                <el-divider content-position="left">仿真变量配置</el-divider>
                <el-form label-width="80px">
                    <el-form-item v-for="(item, index) in variableConfigs" :key="index" :label="'变量 ' + (index + 1)"
                        style="margin-bottom: 12px;">
                        <el-input v-model="item.name" placeholder="变量名（如 速度(m/s)）"
                            style="width: 200px; margin-right: 8px;" />
                        <el-input v-model="item.path" placeholder="变量路径（如 v@car01）"
                            style="width: 240px; margin-right: 8px;" />
                        <el-button type="danger" size="small" @click="removeVariable(index)"
                            :disabled="variableConfigs.length <= 1">
                            删除
                        </el-button>
                    </el-form-item>
                    <el-form-item>
                        <el-button type="primary" size="small" @click="addVariable">
                            + 添加变量
                        </el-button>
                    </el-form-item>
                </el-form>
            </div>
        </div>
        <div style="height: 100vh; overflow-y: auto;">
            <!-- 从后端获取数据 -->
            <div v-if="loading" style="padding: 20px; text-align: center;">加载中...</div>
            <div v-else style="padding: 20px;">
                <simulationDataChartView :raw-data="simulationData" :data-features="dataFeatures"
                    @playback-started="handlePlaybackStarted" @playback-stopped="handlePlaybackStopped"
                    style="height: calc(100vh - 120px);" />
            </div>
        </div>
    </div>
</template>

<script>
import simulationDataChartView from '@/views/dataModel/simulationChartView.vue';

// 引入 AMESim API
import {
    openModel,
    runSimulation,
    closeModel,
    getSimulationResults,
    initAmesimApi,
    closeAmesimApi
} from '@/api/amesimAPI';

export default {
    components: {
        simulationDataChartView
    },
    data() {
        return {
            amesimFilePath: '', // 用户输入的模型路径
            simulationData: [],
            dataFeatures: {
                rowCount: 0,
                columnCount: 0,
                fileSize: '',
                lastModified: '',
                columns: []
            },
            loading: false,
            loadingAction: null, // 'open' | 'run' | 'close'
            modelOpened: false,
            message: '',
            variableConfigs: [{ name: '', path: '' }], // 变量配置列表
        };
    },
    created() {
        // this.fetchData();
        // 初始化Amesim API
        this.initBackend();
    },
    beforeDestroy() {
        // 组件销毁时尝试关闭模型和 API（可选）
        if (this.modelOpened) {
            this.handleCloseModel();
        }
    },
    methods: {
        async fetchData() {
            try {
                this.loading = true;

                // 调用后端接口获取数据
                //const response = await fetchDataFromBackend();
                // 测试模拟数据
                const mockResponse = {
                    "data": [
                        {
                            "时间": 0,
                            "输入燃油泵转速": 1000,
                            "供油流量1-1": 5.2,
                            "供油流量1-2": 4.8,
                            "回油流量1-1": 3.5,
                            "回油流量1-2": 3.2
                        },
                        {
                            "时间": 1,
                            "输入燃油泵转速": 1020,
                            "供油流量1-1": 5.3,
                            "供油流量1-2": 4.9,
                            "回油流量1-1": 3.6,
                            "回油流量1-2": 3.3
                        },
                        {
                            "时间": 2,
                            "输入燃油泵转速": 1040,
                            "供油流量1-1": 5.4,
                            "供油流量1-2": 5.0,
                            "回油流量1-1": 3.7,
                            "回油流量1-2": 3.4
                        }
                    ],
                    "dataFeatures": {
                        "rowCount": 3,
                        "columnCount": 6,
                        "fileSize": "1.2 KB",
                        "lastModified": "2023-09-25 14:30:00",
                        "columns": [
                            { "name": "时间", "type": "number" },
                            { "name": "输入燃油泵转速", "type": "number" },
                            { "name": "供油流量1-1", "type": "number" },
                            { "name": "供油流量1-2", "type": "number" },
                            { "name": "回油流量1-1", "type": "number" },
                            { "name": "回油流量1-2", "type": "number" }
                        ]
                    }
                }

                // 假设后端返回格式如下：
                // {
                //   data: [ /* 数组，每个元素是对象 */ ],
                //   dataFeatures: { /* 数据特征 */ }
                // }

                // this.simulationData = response.data;
                // this.dataFeatures = response.dataFeatures;
                this.simulationData = mockResponse.data;
                this.dataFeatures = mockResponse.dataFeatures;
            } catch (error) {
                console.error('获取数据失败:', error);
                this.$message.error('数据加载失败');
            } finally {
                this.loading = false;
            }
        },
        async initBackend() {
            try {
                // 如果后端需要显式初始化（根据 client.py），可调用
                await initAmesimApi();
                console.log("初始化Amesim API 成功");
            } catch (err) {
                console.warn('AMESim API 初始化失败（可能不需要）:', err);
            }
        },

        async handleOpenModel() {
            if (!this.amesimFilePath.trim()) {
                this.$message.warning('请输入模型文件路径');
                return;
            }
            this.loadingAction = 'open';
            this.message = '正在打开模型...';
            try {
                const res = await openModel(this.amesimFilePath);
                console.log('打开模型响应:', res);
                this.modelOpened = true;
                this.message = `模型 ${this.amesimFilePath} 已成功加载`;
                this.$message.success('模型加载成功');
            } catch (error) {
                this.message = '模型打开失败';
                this.$message.error('模型打开失败：' + (error.response&&error.response.data&&error.response.data.message || error.message));
            } finally {
                this.loadingAction = null;
            }
        },

        async handleRunSimulation() {
            if (!this.modelOpened) return;
            this.loadingAction = 'run';
            this.message = '正在运行仿真...（可能需要几秒到几分钟）';
            this.loading = true;

            try {
                // 1. 运行仿真
                await runSimulation();

                // 2. 获取结果
                // 构建 variables 对象：{ "变量名": "路径", ... }
                const variables = {};
                let validCount = 0;
                for (const config of this.variableConfigs) {
                    if (config.name.trim() && config.path.trim()) {
                        variables[config.name.trim()] = config.path.trim();
                        validCount++;
                    }
                }
                if (validCount === 0) {
                    this.$message.warning('请至少配置一个有效的变量名和路径');
                    return;
                }

                // 获取仿真结果
                const result = await getSimulationResults(variables);

                // 3. 处理返回数据（假设 result.data 是数组，结构类似 mockResponse.data）
                if (result && Array.isArray(result.data)) {
                    this.simulationData = result.data;

                    // 构造 dataFeatures（可根据实际返回补充）
                    const columns = Object.keys(result.data[0] || {}).map(name => ({ name, type: 'number' }));
                    this.dataFeatures = {
                        rowCount: result.data.length,
                        columnCount: columns.length,
                        fileSize: 'N/A',
                        lastModified: new Date().toLocaleString(),
                        columns
                    };
                    this.message = `仿真完成，共 ${result.data.length} 条数据`;
                    this.$message.success('仿真完成');
                } else {
                    throw new Error('仿真结果格式异常');
                }
            } catch (error) {
                this.message = '仿真运行失败';
                this.$message.error('仿真失败：' + (error.response&&error.response.data&&error.response.data.message || error.message));
                this.simulationData = [];
                this.dataFeatures = { rowCount: 0, columnCount: 0, fileSize: '', lastModified: '', columns: [] };
            } finally {
                this.loading = false;
                this.loadingAction = null;
            }
        },

        async handleCloseModel() {
            this.loadingAction = 'close';
            this.message = '正在关闭模型...';
            try {
                await closeModel();
                this.modelOpened = false;
                this.message = '模型已关闭';
                this.$message.info('模型已关闭');
            } catch (error) {
                this.$message.error('关闭模型失败：' + (error.response&&error.response.data&&error.response.data.message || error.message));
            } finally {
                this.loadingAction = null;
            }
        },

        resetAll() {
            this.amesimFilePath = '';
            this.simulationData = [];
            this.dataFeatures = { rowCount: 0, columnCount: 0, fileSize: '', lastModified: '', columns: [] };
            this.modelOpened = false;
            this.message = '';
            this.variableConfigs = [{ name: '', path: '' }];
        },

        handlePlaybackStarted() {
            console.log('播放开始');
        },
        handlePlaybackStopped() {
            console.log('播放停止');
        },
        addVariable() {
            this.variableConfigs = [...this.variableConfigs, { name: '', path: '' }];
        },
        removeVariable(index) {
            this.variableConfigs = this.variableConfigs.filter((_, i) => i !== index);
        },
    }
};
</script>

<style scoped>
/* 可选：微调样式 */
.el-button-group .el-button {
    border-radius: 0 !important;
}

.el-button-group .el-button:first-child {
    border-top-left-radius: 4px !important;
    border-bottom-left-radius: 4px !important;
}

.el-button-group .el-button:last-child {
    border-top-right-radius: 4px !important;
    border-bottom-right-radius: 4px !important;
}
</style>