import { login, getCurrentUser } from '@/api/auth'
import { getToken, setToken, removeToken } from '@/utils/auth'
import { resetRouter } from '@/router'

const getDefaultState = () => ({
  token: getToken(),
  name: ''
})

const state = getDefaultState()

const mutations = {
  RESET_STATE: state => {
    Object.assign(state, getDefaultState())
  },
  SET_TOKEN: (state, token) => {
    state.token = token
  },
  SET_NAME: (state, name) => {
    state.name = name
  }
}

const actions = {
  async login({ commit }, { username, password }) {
    const { token, username: name } = await login(username.trim(), password)
    setToken(token)
    commit('SET_TOKEN', token)
    commit('SET_NAME', name)
  },

  async getInfo({ commit }) {
    const { username } = await getCurrentUser()
    commit('SET_NAME', username)
    return username
  },

  // 令牌是无状态的，退出登录只需在本地删除
  logout({ commit }) {
    removeToken()
    resetRouter()
    commit('RESET_STATE')
  },

  resetToken({ commit }) {
    removeToken()
    commit('RESET_STATE')
  }
}

export default {
  namespaced: true,
  state,
  mutations,
  actions
}
