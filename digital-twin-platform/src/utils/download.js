import request from '@/utils/request'

/** 带登录令牌下载文件（普通 <a href> 无法携带请求头）。 */
export async function downloadWithAuth(url, fileName) {
  const blob = await request({ url, method: 'get', responseType: 'blob' })
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}
