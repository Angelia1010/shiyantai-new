import { saveLogs } from '@/api/tasks'

/**
 * 把前端日志批量上报到任务服务，避免每条日志一个请求。
 * 每 10 秒或攒满 50 条上报一次；上报失败的日志直接丢弃（只是辅助排查）。
 */
export function createRemoteLogger(source, { interval = 10000, batchSize = 50 } = {}) {
  let buffer = []
  const flush = () => {
    if (!buffer.length) return
    const logs = buffer
    buffer = []
    saveLogs(source, logs).catch(() => {})
  }
  const timer = setInterval(flush, interval)
  return {
    log(level, message) {
      buffer.push({ level, message })
      if (buffer.length >= batchSize) flush()
    },
    close() {
      clearInterval(timer)
      flush()
    }
  }
}
