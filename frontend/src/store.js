import { reactive } from 'vue'
import { api } from './api'

export const state = reactive({
  authed: false,
  username: '',
  userId: null,
  overview: null,
  settings: null,
  categories: [],
  loading: false,
  toasts: [],
})

let toastId = 0

export function toast(text, kind = 'info', ttl = 4500) {
  const id = ++toastId
  state.toasts.push({ id, text, kind })
  setTimeout(() => {
    const index = state.toasts.findIndex((t) => t.id === id)
    if (index !== -1) state.toasts.splice(index, 1)
  }, ttl)
}

export const notifyError = (error) => {
  if (error?.auth) return
  toast(error?.message || 'Что-то пошло не так', 'bad')
}

export async function loadOverview() {
  state.overview = await api.overview()
  state.categories = state.overview.categories
  return state.overview
}

export async function loadSettings() {
  state.settings = await api.settings()
  return state.settings
}

export async function bootstrap() {
  state.loading = true
  try {
    const me = await api.me()
    state.authed = !!me.authenticated
    state.username = me.username || ''
    state.userId = me.user_id
    if (state.authed) await Promise.all([loadOverview(), loadSettings()])
  } catch (error) {
    state.authed = false
  } finally {
    state.loading = false
  }
}

// После любой операции, меняющей деньги, обновляем обзор — шапка всегда актуальна.
export async function applyMutation(result) {
  if (result?.plan) {
    state.overview = { ...(state.overview || {}), plan: result.plan }
  }
  if (result?.warnings?.length) {
    result.warnings.forEach((line) => toast(stripEmoji(line), 'warn', 6000))
  }
  return result
}

export const stripEmoji = (text) => String(text).replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, '').trim()

export const monthName = (iso) => {
  const months = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
  const date = new Date(iso + 'T00:00:00')
  return `${months[date.getMonth()]} ${date.getFullYear()}`
}

export const shortDate = (iso) => {
  if (!iso) return ''
  const date = new Date(iso + 'T00:00:00')
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })
}

export const todayISO = () => {
  const now = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}
