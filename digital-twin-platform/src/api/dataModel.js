import request from '@/utils/request'

// 获取数据模型列表
export function fetchDataModelList(query) {
    return request({
        url: '/db/dataModels',
        method: 'get',
        params: query
    })
}

// 创建数据模型
export function createDataModel(data) {
    return request({
        url: '/db/createDataModel',
        method: 'post',
        data
    })
}

// 更新数据模型
export function updateDataModel(id, data) {
    return request({
        url: `/db/updateDataModel/${id}`,
        method: 'put',
        data
    })
}

// 删除数据模型
export function deleteDataModel(id) {
    return request({
        url: `/db/deleteDataModel/${id}`,
        method: 'delete'
    })
}

// 获取数据模型详情
export function fetchDataModel(id) {
    return request({
        url: `/db/dataModel/${id}`,
        method: 'get'
    })
}

// 分析数据模型（生成分析结果）
export function analyzeDataModel(id) {
    return request({
        url: `/db/analyzeDataModel/${id}`,
        method: 'post'
    })
}

// 下载分析结果
export function downloadAnalysisResult(id) {
    window.location.href = `/db/downloadAnalysisResult/${id}`;
}

// 获取Excel文件预览数据（用于创建页面的文件验证）
export function previewExcelData(filePath) {
    return request({
        url: `/file/previewExcel`,
        method: 'get',
        params: { file_path: filePath }
    })
}