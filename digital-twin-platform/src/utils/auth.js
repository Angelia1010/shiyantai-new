import Cookies from 'js-cookie'

const TokenKey = 'shiyantai_token'

export function getToken() {
  return Cookies.get(TokenKey)
}

export function setToken(token) {
  return Cookies.set(TokenKey, token, { sameSite: 'strict' })
}

export function removeToken() {
  return Cookies.remove(TokenKey)
}
