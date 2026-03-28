const BASE = '/api'

async function get(path, params = {}) {
  const url = new URL(BASE + path, window.location.origin)
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined) url.searchParams.set(k, v)
  })
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`API error: ${resp.status}`)
  return resp.json()
}

async function post(path, body) {
  const resp = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(`API error: ${resp.status}`)
  return resp.json()
}

export const api = {
  getStatus: () => get('/status'),
  getLatestCaptures: () => get('/captures/latest'),
  getCaptures: (params) => get('/captures', params),
  getCaptureDates: (params) => get('/captures/dates', params),
  getCapturesByTime: (params) => get('/captures/by-time', params),
  getCameras: () => get('/config/cameras'),
  getRenders: (params) => get('/renders', params),
  getRender: (id) => get(`/renders/${id}`),
  submitRender: (body) => post('/renders', body),
}
