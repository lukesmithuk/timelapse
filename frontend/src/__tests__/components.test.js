import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import NavBar from '../components/NavBar.vue'

describe('NavBar', () => {
  it('renders navigation links', () => {
    const wrapper = mount(NavBar, {
      global: { stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    expect(wrapper.text()).toContain('Dashboard')
    expect(wrapper.text()).toContain('Gallery')
    expect(wrapper.text()).toContain('Videos')
    expect(wrapper.text()).toContain('Render')
  })
})
