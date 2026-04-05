import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Render from '../views/Render.vue'
import Compare from '../views/Compare.vue'

// Mock the api module
vi.mock('../api', () => ({
  api: {
    getCameras: vi.fn().mockResolvedValue({ cameras: { garden: { device: 0 } } }),
    getRenders: vi.fn().mockResolvedValue({ jobs: [] }),
    submitRender: vi.fn().mockResolvedValue({ id: 1, status: 'pending' }),
    getCaptures: vi.fn().mockResolvedValue({ captures: [], total: 0 }),
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

describe('Compare view', () => {
  const stubs = {
    ImageCompare: { template: '<div class="mock-slider">Slider</div>' },
  }

  it('renders camera select and date inputs', () => {
    const wrapper = mount(Compare, {
      global: { stubs },
    })
    expect(wrapper.find('select').exists()).toBe(true)
    expect(wrapper.findAll('input[type="date"]').length).toBe(2)
    expect(wrapper.find('input[type="time"]').exists()).toBe(true)
  })

  it('shows Before and After labels', () => {
    const wrapper = mount(Compare, {
      global: { stubs },
    })
    expect(wrapper.text()).toContain('Before')
    expect(wrapper.text()).toContain('After')
  })

  it('does not show slider when no images selected', () => {
    const wrapper = mount(Compare, {
      global: { stubs },
    })
    expect(wrapper.find('.mock-slider').exists()).toBe(false)
  })
})
