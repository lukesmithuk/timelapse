import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import NavBar from '../components/NavBar.vue'

describe('NavBar', () => {
  const stubs = { 'router-link': { template: '<a><slot /></a>', props: ['to'] } }

  it('renders navigation links', () => {
    const wrapper = mount(NavBar, {
      global: { stubs },
    })
    expect(wrapper.text()).toContain('Dashboard')
    expect(wrapper.text()).toContain('Gallery')
    expect(wrapper.text()).toContain('Videos')
    expect(wrapper.text()).toContain('Render')
  })

  it('hides Render link when canRender is false', () => {
    const wrapper = mount(NavBar, {
      props: { canRender: false },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('Dashboard')
    expect(wrapper.text()).toContain('Gallery')
    expect(wrapper.text()).toContain('Videos')
    expect(wrapper.text()).not.toContain('Render')
  })

  it('shows Render link when canRender is true', () => {
    const wrapper = mount(NavBar, {
      props: { canRender: true },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('Render')
  })
})
