// amesimApi.js - 封装 AMESim 仿真服务的 API 调用
import request from '@/utils/request'

// 基础路径前缀（与 Nginx 配置中的 location /amesim/ 对应）
const BASE_URL = '/amesim/api'

/**
 * 健康检查
 */
export function healthCheck() {
    return request({
        url: `${BASE_URL}/health`,
        method: 'get'
    })
}

/**
 * 初始化 AMESim API
 */
export function initAmesimApi() {
    return request({
        url: `${BASE_URL}/init`,
        method: 'post'
    })
}

/**
 * 打开模型文件
 * @param {string} filePath - 模型文件路径（如 'test.ame'）
 */
export function openModel(filePath) {
    return request({
        url: `${BASE_URL}/model/open`,
        method: 'post',
        data: { filePath }
    })
}

/**
 * 关闭当前模型
 */
export function closeModel() {
    return request({
        url: `${BASE_URL}/model/close`,
        method: 'post'
    })
}

/**
 * 获取所有模型参数
 */
export function getModelParameters() {
    return request({
        url: `${BASE_URL}/model/parameters`,
        method: 'get'
    })
}

/**
 * 设置运行参数（如 stop_time_s）
 * @param {string} parameter - 参数名
 * @param {any} value - 参数值（字符串或数字）
 */
export function setRunParameter(parameter, value) {
    return request({
        url: `${BASE_URL}/model/parameters/run`,
        method: 'put',
        data: { parameter, value }
    })
}

/**
 * 设置全局参数
 * @param {string} parameter - 参数名
 * @param {any} value - 参数值
 */
export function setGlobalParameter(parameter, value) {
    return request({
        url: `${BASE_URL}/model/parameters/global`,
        method: 'put',
        data: { parameter, value }
    })
}

/**
 * 设置部件（组件）参数
 * @param {string} parameter - 参数名（通常含组件路径，如 'pump01.diameter'）
 * @param {any} value - 参数值
 */
export function setComponentParameter(parameter, value) {
    return request({
        url: `${BASE_URL}/model/parameters/component`,
        method: 'put',
        data: { parameter, value }
    })
}

/**
 * 运行仿真
 */
export function runSimulation() {
    return request({
        url: `${BASE_URL}/simulation/run`,
        method: 'post'
    })
}

/**
 * 获取单个变量的值（需提供完整变量路径）
 * @param {string} variablePath - 变量路径，如 'pin@pump01'
 */
export function getVariable(variablePath) {
    return request({
        url: `${BASE_URL}/simulation/variable`,
        method: 'get',
        params: { path: variablePath }
    })
}

/**
 * 获取仿真结果（多变量）
 * @param {Object} variables - 变量名到路径的映射，例如：
 *   { "速度(m/s)": "v@car01", "高度(m)": "h@tank01" }
 */
export function getSimulationResults(variables) {
  return request({
    url: `${BASE_URL}/simulation/results`,
    method: 'post',
    data: { variables }
  })
}

/**
 * 关闭 AMESim API（释放资源）
 */
export function closeAmesimApi() {
    return request({
        url: `${BASE_URL}/close`,
        method: 'post'
    })
}