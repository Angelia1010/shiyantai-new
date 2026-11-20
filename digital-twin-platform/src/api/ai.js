import { postNdjson } from '@/utils/stream'

const BASE = '/api/ai'

/** 大模型分析数据文件。事件：start / window / summary / done / error */
export function analyzeFile({ path, fileName, sessionId }, onEvent, signal) {
  return postNdjson(`${BASE}/analyze`, { path, file_name: fileName, session_id: sessionId }, onEvent, signal)
}

/** 对话。事件：answer / done / error */
export function chat(question, sessionId, onEvent, signal) {
  return postNdjson(`${BASE}/chat`, { question, session_id: sessionId }, onEvent, signal)
}
