import Vue from 'vue'
import Router from 'vue-router'

Vue.use(Router)

/* Layout */
import Layout from '@/layout'
import AIChaterNew from '@/components/AI/AIChaterNew.vue'

/**
 * Note: sub-menu only appear when route children.length >= 1
 * Detail see: https://panjiachen.github.io/vue-element-admin-site/guide/essentials/router-and-nav.html
 *
 * hidden: true                   if set true, item will not show in the sidebar(default is false)
 * alwaysShow: true               if set true, will always show the root menu
 *                                if not set alwaysShow, when item has more than one children route,
 *                                it will becomes nested mode, otherwise not show the root menu
 * redirect: noRedirect           if set noRedirect will no redirect in the breadcrumb
 * name:'router-name'             the name is used by <keep-alive> (must set!!!)
 * meta : {
    roles: ['admin','editor']    control the page roles (you can set multiple roles)
    title: 'title'               the name show in sidebar and breadcrumb (recommend set)
    icon: 'svg-name'/'el-icon-x' the icon show in the sidebar
    breadcrumb: false            if set false, the item will hidden in breadcrumb(default is true)
    activeMenu: '/example/list'  if set path, the sidebar will highlight the path you set
  }
 */

/**
 * constantRoutes
 * a base page that does not have permission requirements
 * all roles can be accessed
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
    path: '/workbench',
    component: () => import('@/views/workbench'),
    hidden: true
  },

  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    meta: { title: '首页', icon: 'dashboard' },
    children: [{
      path: '/',
      name: 'Home',
      component: () => import('@/views/dashboard/index'),
      meta: { title: '工作台', icon: 'dashboard' }
    },
      // {
      //   path: 'model',
      //   name: 'Model',
      //   component: () => import('@/views/dashboard/model'),
      //   meta: { title: '泵模型', icon: 'nested' }
      // }
    ]
  },

  {
    path: '/example',
    component: Layout,
    redirect: '/example/table',
    name: 'Example',
    meta: { title: '任务管理', icon: 'el-icon-s-help' },
    children: [
      // {
      //   path: 'setting',
      //   name: 'Setting',
      //   component: () => import('@/views/setting/index'),
      //   meta: { title: '试验台数据同步', icon: 'el-icon-setting' }
      // },
      {
        path: 'table',
        name: 'Table',
        component: () => import('@/views/table/index'),
        meta: { title: '任务列表', icon: 'table' }
      },
      {
        path: 'tree',
        name: 'Tree',
        component: () => import('@/views/tree/index'),
        meta: { title: '任务创建', icon: 'form' }
      }
    ]
  },
  {
    path: '/dataModel',
    component: Layout,
    redirect: '/dataModel/index',
    name: 'DataModel',
    meta: { title: '仿真管理', icon: 'el-icon-data-analysis' },
    children: [
      {
        path: 'index',
        name: 'DataModelList',
        component: () => import('@/views/dataModel/index'),
        meta: { title: '仿真列表', icon: 'el-icon-s-grid' }
      },
      // {
      //   path: 'create',
      //   name: 'DataModelCreate',
      //   component: () => import('@/views/dataModel/create'),
      //   meta: { title: '创建仿真', icon: 'el-icon-plus' },
      // }
      {
        path: 'simulationView',
        name: 'simulationView',
        component: () => import('@/views/dataModel/simulationView'),
        meta: { title: '仿真界面', icon: 'el-icon-stopwatch' },
      }
    ]
  },
  {
    path: '/aichat',
    component: Layout,
    children: [
      {
        path: 'index',
        name: 'Form',
        component: AIChaterNew,
        meta: { title: 'AI Chat', icon: 'el-icon-chat-dot-round' }
      }
    ]
  },
  {
    path: '/form',
    component: Layout,
    children: [
      {
        path: 'index',
        name: 'Form',
        component: () => import('@/views/form/index'),
        meta: { title: '权限设置', icon: 'tree' }
      }
    ]
  },
  {
    path: '/autoDiagnosis',
    component: Layout,
    redirect: '/autoDiagnosis/index',
    name: 'AutoDiagnosis',
    meta: { title: '自动诊断', icon: 'el-icon-s-promotion' },
    children: [
      {
        path: 'index',
        name: 'AutoDiagnosisIndex',
        component: () => import('@/views/autoDiagnosis/index'),
        meta: { title: '自动诊断流程', icon: 'el-icon-s-promotion' }
      }
    ]
  },

  // 404 page must be placed at the end !!!
  { path: '*', redirect: '/404', hidden: true }
]

const createRouter = () => new Router({
  scrollBehavior: () => ({ y: 0 }),
  routes: constantRoutes
})

const router = createRouter()

// Detail see: https://github.com/vuejs/vue-router/issues/1234#issuecomment-357941465
export function resetRouter() {
  const newRouter = createRouter()
  router.matcher = newRouter.matcher // reset router
}

export default router
