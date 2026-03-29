import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../api'

describe('api client', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('getStatus calls correct URL', async () => {
    global.fetch.mockResolvedValue({ ok: true, json: () => ({ state: 'online' }) })
    const data = await api.getStatus()
    expect(data.state).toBe('online')
    const calledUrl = global.fetch.mock.calls[0][0]
    expect(calledUrl.toString()).toContain('/api/status')
  })

  it('submitRender posts to /api/renders', async () => {
    global.fetch.mockResolvedValue({ ok: true, json: () => ({ id: 1, status: 'pending' }) })
    const data = await api.submitRender({ camera: 'garden', date_from: '2026-03-01', date_to: '2026-03-28' })
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/renders',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(data.id).toBe(1)
  })

  it('throws on non-ok response', async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 })
    await expect(api.getStatus()).rejects.toThrow('API error: 500')
  })
})
