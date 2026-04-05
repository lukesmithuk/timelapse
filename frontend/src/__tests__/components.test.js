import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import NavBar from '../components/NavBar.vue'
import ImageCompare from '../components/ImageCompare.vue'
import WeatherBadge from '../components/WeatherBadge.vue'
import WeatherDetail from '../components/WeatherDetail.vue'
import VideoCard from '../components/VideoCard.vue'

vi.mock('../api', () => ({
  api: {
    getWeather: vi.fn().mockResolvedValue({ summary: null, intervals: [] }),
    getWeatherForCapture: vi.fn().mockResolvedValue(null),
  },
}))

describe('NavBar', () => {
  const stubs = { 'router-link': { template: '<a><slot /></a>', props: ['to'] } }

  it('renders navigation links including Compare', () => {
    const wrapper = mount(NavBar, {
      global: { stubs },
    })
    expect(wrapper.text()).toContain('Dashboard')
    expect(wrapper.text()).toContain('Gallery')
    expect(wrapper.text()).toContain('Compare')
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
    expect(wrapper.text()).toContain('Compare')
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

describe('ImageCompare', () => {
  it('renders both images', () => {
    const wrapper = mount(ImageCompare, {
      props: {
        imageA: '/img/a.jpg',
        imageB: '/img/b.jpg',
      },
    })
    const imgs = wrapper.findAll('img')
    expect(imgs.length).toBe(2)
    expect(imgs[0].attributes('src')).toBe('/img/b.jpg')
    expect(imgs[1].attributes('src')).toBe('/img/a.jpg')
  })

  it('defaults slider to 50%', () => {
    const wrapper = mount(ImageCompare, {
      props: {
        imageA: '/img/a.jpg',
        imageB: '/img/b.jpg',
      },
    })
    const overlay = wrapper.find('.image-compare__overlay')
    expect(overlay.attributes('style')).toContain('50%')
  })

  it('renders labels when provided', () => {
    const wrapper = mount(ImageCompare, {
      props: {
        imageA: '/img/a.jpg',
        imageB: '/img/b.jpg',
        labelA: 'June 2026',
        labelB: 'September 2026',
      },
    })
    expect(wrapper.text()).toContain('June 2026')
    expect(wrapper.text()).toContain('September 2026')
  })
})

describe('WeatherBadge', () => {
  it('renders conditions and temperature', () => {
    const wrapper = mount(WeatherBadge, {
      props: { conditions: 'Clear sky', temperature: 18.2 },
    })
    expect(wrapper.text()).toContain('18')
    expect(wrapper.text()).toContain('°C')
  })

  it('shows sun icon for clear sky', () => {
    const wrapper = mount(WeatherBadge, {
      props: { conditions: 'Clear sky', temperature: 20 },
    })
    expect(wrapper.text()).toContain('☀')
  })

  it('shows rain icon for rain conditions', () => {
    const wrapper = mount(WeatherBadge, {
      props: { conditions: 'Light rain', temperature: 12 },
    })
    expect(wrapper.text()).toContain('🌧')
  })
})

describe('WeatherDetail', () => {
  it('renders all weather fields', () => {
    const wrapper = mount(WeatherDetail, {
      props: {
        weather: {
          temperature: 15.3,
          conditions: 'Partly cloudy',
          humidity: 65,
          wind_speed: 12.1,
          precipitation: 0.0,
          cloud_cover: 45,
        },
      },
    })
    expect(wrapper.text()).toContain('15')
    expect(wrapper.text()).toContain('Partly cloudy')
    expect(wrapper.text()).toContain('65')
  })

  it('handles missing values gracefully', () => {
    const wrapper = mount(WeatherDetail, {
      props: {
        weather: {
          temperature: null,
          conditions: null,
          humidity: null,
          wind_speed: null,
          precipitation: null,
          cloud_cover: null,
        },
      },
    })
    // Should render without errors
    expect(wrapper.exists()).toBe(true)
  })
})

describe('VideoCard weather badge', () => {
  it('fetches weather for daily videos', async () => {
    const { api } = await import('../api')
    api.getWeather.mockResolvedValue({
      summary: { conditions: 'Clear sky', temp_high: 20, temp_low: 10, humidity: 50, wind_speed: 10, precipitation: 0, cloud_cover: 20 },
      intervals: [],
    })

    const wrapper = mount(VideoCard, {
      props: {
        job: { id: 1, camera: 'garden', job_type: 'daily', status: 'done', date_from: '2026-04-05', date_to: '2026-04-05', video_url: '/api/videos/test.mp4', created_at: '2026-04-05T20:00:00' },
      },
    })

    // Wait for onMounted async
    await new Promise(r => setTimeout(r, 10))
    await wrapper.vm.$nextTick()

    expect(api.getWeather).toHaveBeenCalledWith({ date: '2026-04-05' })
  })

  it('does not fetch weather for custom videos', async () => {
    const { api } = await import('../api')
    api.getWeather.mockClear()

    mount(VideoCard, {
      props: {
        job: { id: 2, camera: 'garden', job_type: 'custom', status: 'done', date_from: '2026-04-01', date_to: '2026-04-05', video_url: '/api/videos/test.mp4', created_at: '2026-04-05T20:00:00' },
      },
    })

    await new Promise(r => setTimeout(r, 10))
    expect(api.getWeather).not.toHaveBeenCalled()
  })
})
