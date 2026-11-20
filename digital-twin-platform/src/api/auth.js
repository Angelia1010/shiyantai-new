import request from '@/utils/request'

const BASE = '/api/task/auth'

export function login(username, password) {
  return request({ url: `${BASE}/login`, method: 'post', data: { username, password }, loginRequest: true })
}

export function getCurrentUser() {
  return request({ url: `${BASE}/me`, method: 'get' })
}
