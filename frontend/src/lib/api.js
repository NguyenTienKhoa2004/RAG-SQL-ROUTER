const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE}/api${path}`, options)
  } catch {
    throw new ApiError('Không thể kết nối backend. Kiểm tra server rồi thử lại.', 0)
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new ApiError(typeof data.detail === 'string' ? data.detail : 'Yêu cầu không thành công. Vui lòng thử lại.', response.status)
  }
  return response.status === 204 ? null : response.json()
}

const post = (path, body) => request(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

export const api = {
  health: () => request('/health'),
  connect: (key) => post('/sessions', { api_key: key || null }),
  session: (id) => request(`/sessions/${id}`),
  chat: (id, message) => post(`/sessions/${id}/chat`, { message }),
  reset: (id) => post(`/sessions/${id}/reset`, {}),
  disconnect: (id) => request(`/sessions/${id}`, { method: 'DELETE' }),
  upload: (id, files) => {
    const body = new FormData()
    files.forEach((file) => body.append('files', file))
    return request(`/sessions/${id}/documents`, { method: 'POST', body })
  },
  database: ({ page = 1, search = '', table = 'orders' }, signal) => request(`/database?${new URLSearchParams({ page, search, table })}`, { signal }),
}
