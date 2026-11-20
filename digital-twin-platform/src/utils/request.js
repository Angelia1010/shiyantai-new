import axios from 'axios'
import { Message } from 'element-ui'
import { getToken, removeToken } from '@/utils/auth'

// 所有后端接口都以 /api/<服务名> 开头，由开发服务器或 Nginx 转发到对应服务
const service = axios.create({
  timeout: 120000
})

service.interceptors.request.use(config => {
  const token = getToken()
  if (token) {
    config.headers['X-Token'] = token
  }
  return config
})

let redirectingToLogin = false

/** 从后端错误响应里取出可读的提示（Flask 服务返回 error，FastAPI 服务返回 detail）。 */
export function errorMessage(error) {
  const data = error && error.response && error.response.data
  if (data && typeof data === 'object') {
    if (data.error) return data.error
    if (typeof data.detail === 'string') return data.detail
  }
  return (error && error.message) || '请求失败'
}

service.interceptors.response.use(
  response => response.data,
  error => {
    const status = error.response && error.response.status
    const config = error.config || {}
    if (status === 401 && config.loginRequest) {
      // 登录接口的 401 表示账号密码错误，不是登录过期
      Message.error(errorMessage(error))
    } else if (status === 401 && !redirectingToLogin) {
      redirectingToLogin = true
      removeToken()
      Message.error('登录已过期，请重新登录')
      const redirect = encodeURIComponent(window.location.hash.replace(/^#/, '') || '/')
      window.location.hash = `#/login?redirect=${redirect}`
      setTimeout(() => { redirectingToLogin = false }, 1000)
    } else if (status !== 401 && !config.silent) {
      Message.error({ message: errorMessage(error), duration: 5000 })
    }
    return Promise.reject(error)
  }
)

export default service
