import { mount, createLocalVue } from '@vue/test-utils'
import VueRouter from 'vue-router'
import ElementUI from 'element-ui'
import Breadcrumb from '@/components/Breadcrumb/index.vue'

const localVue = createLocalVue()
localVue.use(VueRouter)
localVue.use(ElementUI)

// 面包屑只显示带 meta.title 的路由层级（与 src/router 中的写法一致，不额外插入“首页”）
const routes = [
  {
    path: '/',
    name: 'home',
    children: [{
      path: 'dashboard',
      name: 'dashboard',
      meta: { title: '工作台' }
    }]
  },
  {
    path: '/menu',
    name: 'menu',
    children: [{
      path: 'menu1',
      name: 'menu1',
      meta: { title: 'menu1' },
      children: [{
        path: 'menu1-1',
        name: 'menu1-1',
        meta: { title: 'menu1-1' }
      },
      {
        path: 'menu1-2',
        name: 'menu1-2',
        redirect: 'noRedirect',
        meta: { title: 'menu1-2' },
        children: [{
          path: 'menu1-2-1',
          name: 'menu1-2-1',
          meta: { title: 'menu1-2-1' }
        },
        {
          path: 'menu1-2-2',
          name: 'menu1-2-2'
        }]
      }]
    }]
  }]

const router = new VueRouter({
  routes
})

describe('Breadcrumb.vue', () => {
  const wrapper = mount(Breadcrumb, {
    localVue,
    router
  })
  const items = () => wrapper.findAll('.el-breadcrumb__inner')

  it('single level route', () => {
    router.push('/dashboard')
    expect(items().length).toBe(1)
    expect(items().at(0).text()).toBe('工作台')
  })
  it('normal route', () => {
    router.push('/menu/menu1')
    expect(items().length).toBe(1)
  })
  it('nested route', () => {
    router.push('/menu/menu1/menu1-2/menu1-2-1')
    expect(items().length).toBe(3)
  })
  it('levels without meta.title are hidden', () => {
    router.push('/menu/menu1/menu1-2/menu1-2-2')
    expect(items().length).toBe(2)
  })
  it('parent levels are links', () => {
    router.push('/menu/menu1/menu1-2/menu1-2-1')
    expect(items().at(0).contains('a')).toBe(true)
  })
  it('noRedirect level is not a link', () => {
    router.push('/menu/menu1/menu1-2/menu1-2-1')
    expect(items().at(1).contains('a')).toBe(false)
  })
  it('last breadcrumb is not a link', () => {
    router.push('/menu/menu1/menu1-2/menu1-2-1')
    expect(items().at(2).contains('a')).toBe(false)
  })
})
