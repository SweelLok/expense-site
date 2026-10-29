// Тонкая обёртка над fetch: один origin, кука сессии, разбор ошибок FastAPI.
const base = '/api'

export const api = {
  onUnauthorized: null,

  async call(path, { method = 'GET', body, raw = false } = {}) {
    const res = await fetch(base + path, {
      method,
      credentials: 'same-origin',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
    if (res.status === 401) {
      this.onUnauthorized?.()
      const err = new Error('нужен вход')
      err.auth = true
      throw err
    }
    if (!res.ok) {
      let detail = `ошибка ${res.status}`
      try {
        const data = await res.json()
        if (typeof data.detail === 'string') detail = data.detail
        else if (Array.isArray(data.detail) && data.detail[0]?.msg) detail = data.detail[0].msg
      } catch { /* тело не JSON — оставляем код */ }
      const err = new Error(detail)
      err.status = res.status
      throw err
    }
    return raw ? res : res.json()
  },

  // auth
  me: () => api.call('/auth/me'),
  login: (username, password) => api.call('/auth/login', { method: 'POST', body: { username, password } }),
  logout: () => api.call('/auth/logout', { method: 'POST' }),
  changePassword: (current, next) => api.call('/auth/password', { method: 'POST', body: { current, new: next } }),

  // данные
  overview: () => api.call('/overview'),
  expenses: (query = {}) => api.call('/expenses?' + new URLSearchParams(query)),
  addExpense: (payload) => api.call('/expenses', { method: 'POST', body: payload }),
  patchExpense: (id, payload) => api.call(`/expenses/${id}`, { method: 'PATCH', body: payload }),
  deleteExpense: (id) => api.call(`/expenses/${id}`, { method: 'DELETE' }),

  incomes: (query = {}) => api.call('/incomes?' + new URLSearchParams(query)),
  addIncome: (payload) => api.call('/incomes', { method: 'POST', body: payload }),
  deleteIncome: (id) => api.call(`/incomes/${id}`, { method: 'DELETE' }),

  categories: () => api.call('/categories'),
  addCategory: (payload) => api.call('/categories', { method: 'POST', body: payload }),
  patchCategory: (id, payload) => api.call(`/categories/${id}`, { method: 'PATCH', body: payload }),
  deleteCategory: (id) => api.call(`/categories/${id}`, { method: 'DELETE' }),

  subscriptions: () => api.call('/subscriptions'),
  addSubscription: (payload) => api.call('/subscriptions', { method: 'POST', body: payload }),
  patchSubscription: (id, payload) => api.call(`/subscriptions/${id}`, { method: 'PATCH', body: payload }),
  deleteSubscription: (id) => api.call(`/subscriptions/${id}`, { method: 'DELETE' }),

  settings: () => api.call('/settings'),
  saveSettings: (payload) => api.call('/settings', { method: 'PUT', body: payload }),

  stats: (period) => api.call('/stats?period=' + period),
  monthly: (months = 12) => api.call('/monthly?months=' + months),
  reset: (confirm) => api.call('/reset', { method: 'POST', body: { confirm } }),
}

export const download = (path, filename) => {
  const a = document.createElement('a')
  a.href = base + path
  if (filename) a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export const eur = (value) =>
  new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0)) + ' €'

export const money = (value) => Number(value || 0)
