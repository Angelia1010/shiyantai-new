/**
 * 自动诊断页面 → 工作台（Dashboard）的跨标签页消息通道。
 *
 * 消息格式 { type, payload }：
 *   DIAGNOSIS_STATUS   payload: { status, message, fileName? }
 *   DIAGNOSIS_RESULT   payload: { taskId, fileName, result, timestamp, report }
 */
const CHANNEL_NAME = 'shiyantai_diagnosis'

export const MessageType = {
  DIAGNOSIS_STATUS: 'DIAGNOSIS_STATUS',
  DIAGNOSIS_RESULT: 'DIAGNOSIS_RESULT'
}

export function openChannel(onMessage) {
  const channel = new BroadcastChannel(CHANNEL_NAME)
  if (onMessage) {
    channel.onmessage = event => onMessage(event.data || {})
  }
  return {
    send(type, payload) {
      channel.postMessage({ type, payload })
    },
    close() {
      channel.close()
    }
  }
}
