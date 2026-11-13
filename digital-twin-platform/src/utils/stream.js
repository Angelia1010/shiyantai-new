import { getToken } from '@/utils/auth'

/**
 * 以 POST 调用返回 NDJSON（每行一个 JSON）的流式接口，逐个事件回调 onEvent。
 * 可传入 AbortSignal 取消请求；Promise 在流结束时 resolve。
 */
export async function postNdjson(url, body, onEvent, signal) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Token': getToken() || '' },
    body: JSON.stringify(body),
    signal
  })
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const data = await response.json()
      message = data.detail || data.error || message
    } catch (e) { /* 非 JSON 响应 */ }
    throw new Error(message)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  const emitLines = () => {
    let index
    while ((index = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, index).trim()
      buffer = buffer.slice(index + 1)
      if (line) onEvent(JSON.parse(line))
    }
  }
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    emitLines()
  }
  buffer += decoder.decode()
  buffer += '\n'
  emitLines()
}
