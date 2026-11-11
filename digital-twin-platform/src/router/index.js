import Vue from 'vue'
import Router from 'vue-router'
import Layout from '@/layout'

Vue.use(Router)

/**
 * 路由配置。
 * hidden: true      不在侧边栏显示
 * meta.title/icon   侧边栏与面包屑中显示的名称和图标
 */
export const constantRoutes = [
  {
    path: '/login',
    component: () => import('@/views/login/index'),
    hidden: true
  },
  {
    path: '/404',
    component: () => import('@/views/404'),
    hidden: true
  },
  {
    path: '/',
    component: Layout,
    children: [{
      path: '',
      name: 'Dashboard',
      component: () => import('@/views/dashboard/index'),
      meta: { title: '工作台', icon: 'dashboard' }
    }]
  },
  {
    path: '/tasks',
    component: Layout,
    children: [{
      path: '',
      name: 'Tasks',
      component: () => import('@/views/tasks/index'),
      meta: { title: '任务列表', icon: 'table' }
    }]
  },
  {
    path: '/autoDiagnosis',
    component: Layout,
    children: [{
      path: '',
      name: 'AutoDiagnosis',
      component: () => import('@/views/autoDiagnosis/index'),
      meta: { title: '自动诊断', icon: 'el-icon-s-promotion' }
    }]
  },
  {
    path: '/assistant',
    component: Layout,
    children: [{
      path: '',
      name: 'Assistant',
      component: () => import('@/views/assistant/index'),
      meta: { title: '智能助手', icon: 'el-icon-chat-dot-round' }
    }]
  },
  // 404 必须放在最后
  { path: '*', redirect: '/404', hidden: true }
]

const createRouter = () => new Router({
  scrollBehavior: () => ({ y: 0 }),
  routes: constantRoutes
})

const router = createRouter()

// 退出登录时重置路由，参见 https://github.com/vuejs/vue-router/issues/1234#issuecomment-357941465
export function resetRouter() {
  router.matcher = createRouter().matcher
}

export default router
