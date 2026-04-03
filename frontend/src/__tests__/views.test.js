import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import Render from '../views/Render.vue'

// Mock the api module
vi.mock('../api', () => ({
  api: {
    getCameras: vi.fn().mockResolvedValue({ cameras: { garden: { device: 0 } } }),
    getRenders: vi.fn().mockResolvedValue({ jobs: [] }),
    submitRender: vi.fn().mockResolvedValue({ id: 1, status: 'pending' }),
  },
}))

// Mock vue-router
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
}))

describe('Render view', () => {
  const stubs = {
    RenderForm: { template: '<div class="mock-form">Form</div>' },
    JobQueue: { template: '<div class="mock-queue">Queue</div>' },
  }

  it('shows restricted message for viewers', () => {
    const wrapper = mount(Render, {
      props: { access: 'viewer' },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('only available on the local network')
    expect(wrapper.find('.mock-form').exists()).toBe(false)
    expect(wrapper.find('.mock-queue').exists()).toBe(false)
  })

  it('shows form and queue for local access', () => {
    const wrapper = mount(Render, {
      props: { access: 'local' },
      global: { stubs },
    })
    expect(wrapper.text()).not.toContain('only available on the local network')
    expect(wrapper.find('.mock-form').exists()).toBe(true)
    expect(wrapper.find('.mock-queue').exists()).toBe(true)
  })

  it('shows form and queue for admin access', () => {
    const wrapper = mount(Render, {
      props: { access: 'admin' },
      global: { stubs },
    })
    expect(wrapper.find('.mock-form').exists()).toBe(true)
    expect(wrapper.find('.mock-queue').exists()).toBe(true)
  })
})
