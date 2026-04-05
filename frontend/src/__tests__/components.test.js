import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import NavBar from '../components/NavBar.vue'
import ImageCompare from '../components/ImageCompare.vue'
import WeatherBadge from '../components/WeatherBadge.vue'
import WeatherDetail from '../components/WeatherDetail.vue'

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
