/**
 * 定时器。页面切到后台后浏览器会大幅降低 setInterval 的频率，
 * 而 Web Worker 里的定时器不受影响，所以优先用 Worker 发心跳，Worker 不可用时退回 setInterval。
 */
const WORKER_SOURCE = `
let timer = null
self.onmessage = (e) => {
  clearInterval(timer)
  if (e.data && e.data.interval) {
    timer = setInterval(() => self.postMessage('tick'), e.data.interval)
  }
}
`

export function createTicker(intervalMs, onTick) {
  let worker = null
  let timer = null
  try {
    const url = URL.createObjectURL(new Blob([WORKER_SOURCE], { type: 'application/javascript' }))
    worker = new Worker(url)
    URL.revokeObjectURL(url)
    worker.onmessage = () => onTick()
    worker.postMessage({ interval: intervalMs })
  } catch (e) {
    worker = null
    timer = setInterval(onTick, intervalMs)
  }
  return {
    stop() {
      if (worker) {
        worker.terminate()
        worker = null
      }
      if (timer) {
        clearInterval(timer)
        timer = null
      }
    }
  }
}
