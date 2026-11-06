<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { notifyError, toast } from '../store'
import Modal from '../components/Modal.vue'

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

const now = new Date()
const pad = (n) => String(n).padStart(2, '0')
function iso(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const viewYear = ref(now.getFullYear())
const viewMonth = ref(now.getMonth())           // 0–11
const selected = ref(null)                       // ISO дата выбранного дня
const events = ref([])
const status = ref({ connected: false, calendars: [], selected: null, error: null })
const loading = ref(true)

// --- формы ---
const settingsOpen = ref(false)
const settingsForm = ref({ username: '', password: '', calendar: '' })
const settingsBusy = ref(false)

const addOpen = ref(false)
const addForm = ref({ summary: '', all_day: false, date: iso(now), start: '09:00', end: '10:00', description: '' })
const addBusy = ref(false)

function gridDays(year, month) {
  const first = new Date(year, month, 1)
  const startWeekday = (first.getDay() + 6) % 7 // понедельник = 0
  const start = new Date(year, month, 1 - startWeekday)
  const cells = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    cells.push(d)
  }
  return cells
}

const days = computed(() => gridDays(viewYear.value, viewMonth.value))
const monthLabel = computed(() => `${MONTHS[viewMonth.value]} ${viewYear.value}`)
const todayISO = iso(now)

function eventDay(ev) {
  if (ev.all_day) return ev.start.slice(0, 10)
  return iso(new Date(ev.start))
}

const byDay = computed(() => {
  const map = {}
  for (const ev of events.value) {
    const key = eventDay(ev)
    ;(map[key] ||= []).push(ev)
  }
  for (const key of Object.keys(map)) map[key].sort((a, b) => (a.start < b.start ? -1 : 1))
  return map
})

const selectedEvents = computed(() => (selected.value ? byDay.value[selected.value] || [] : []))

// Задачи (todo) с датой — тоже показываем на календаре.
const todos = ref([])
const tasksByDay = computed(() => {
  const map = {}
  for (const t of todos.value) {
    if (t.due_date && !t.done) (map[t.due_date] ||= []).push(t)
  }
  return map
})
const selectedTasks = computed(() => (selected.value ? tasksByDay.value[selected.value] || [] : []))

// Точки под днём: янтарные — события, зелёные — задачи; свыше MAX_DOTS — «+N».
const MAX_DOTS = 4
function dayDots(dayISO) {
  const evCount = (byDay.value[dayISO] || []).length
  const taskCount = (tasksByDay.value[dayISO] || []).length
  const dots = []
  for (let i = 0; i < evCount && dots.length < MAX_DOTS; i++) dots.push('event')
  for (let i = 0; i < taskCount && dots.length < MAX_DOTS; i++) dots.push('task')
  return { dots, extra: evCount + taskCount - dots.length }
}

function timeLabel(ev) {
  if (ev.all_day) return 'весь день'
  const d = new Date(ev.start)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function dayOfWeekLabel(isoDate) {
  const [y, m, d] = isoDate.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return WEEKDAYS[date.getDay()]
}

function isToday(d) { return iso(d) === todayISO }
function inCurrentMonth(d) { return d.getMonth() === viewMonth.value }

async function loadStatus() {
  try {
    status.value = await api.calendarStatus()
  } catch (error) {
    notifyError(error)
  }
}

async function loadEvents() {
  if (!status.value.connected) { events.value = []; return }
  const cells = days.value
  const start = iso(cells[0])
  const end = iso(cells[cells.length - 1])
  try {
    const data = await api.calendarEvents(start, end)
    events.value = data.events
  } catch (error) {
    notifyError(error)
  }
}

async function loadTodos() {
  try {
    const data = await api.todos()
    todos.value = data.todos
  } catch (error) {
    notifyError(error)
  }
}

onMounted(async () => {
  await loadStatus()
  if (status.value.connected) await loadEvents()
  await loadTodos()
  loading.value = false
})

async function refresh() {
  await loadStatus()
  await loadEvents()
  await loadTodos()
}

function prevMonth() {
  if (viewMonth.value === 0) { viewMonth.value = 11; viewYear.value-- }
  else viewMonth.value--
  selected.value = null
  loadEvents()
}
function nextMonth() {
  if (viewMonth.value === 11) { viewMonth.value = 0; viewYear.value++ }
  else viewMonth.value++
  selected.value = null
  loadEvents()
}
function goToday() {
  viewYear.value = now.getFullYear()
  viewMonth.value = now.getMonth()
  selected.value = todayISO
  loadEvents()
}

function pickDay(d) {
  selected.value = iso(d)
}

async function openSettings() {
  settingsOpen.value = true
  settingsForm.value = { username: '', password: '', calendar: '' }
  try {
    const s = await api.calendarSettings()
    await loadStatus()
    settingsForm.value.username = s.username || ''
    settingsForm.value.calendar = s.calendar || status.value.selected || ''
  } catch {
    /* статус подтянем отдельно */
  }
}

async function saveSettings() {
  settingsBusy.value = true
  try {
    const chosenCalendar = settingsForm.value.calendar || null
    const payload = { calendar: chosenCalendar }
    if (settingsForm.value.username.trim()) payload.username = settingsForm.value.username.trim()
    if (settingsForm.value.password.trim()) payload.password = settingsForm.value.password.trim()
    status.value = await api.saveCalendarSettings(payload)
    if (!status.value.connected) {
      if (status.value.error) toast(status.value.error, 'bad', 6000)
      return
    }
    if (!chosenCalendar) {
      // Подключились, но календарь ещё не выбран — не закрываем, показываем список.
      toast('Подключено! Выбери календарь с твоими событиями', 'good', 7000)
      return
    }
    toast('Календарь подключён', 'good')
    settingsOpen.value = false
    await loadEvents()
  } catch (error) {
    notifyError(error)
  } finally {
    settingsBusy.value = false
  }
}

async function disconnect() {
  if (!confirm('Отключить iCloud-календарь? События перестанут отображаться.')) return
  try {
    status.value = await api.disconnectCalendar()
    settingsOpen.value = false
    toast('iCloud отключён', 'good')
    await loadEvents()
  } catch (error) {
    notifyError(error)
  }
}

function openAdd() {
  addForm.value = { summary: '', all_day: false, date: selected.value || todayISO, start: '09:00', end: '10:00', description: '' }
  addOpen.value = true
}

async function saveEvent() {
  if (!addForm.value.summary.trim()) return toast('Напиши название события', 'warn')
  addBusy.value = true
  try {
    const f = addForm.value
    const payload = { summary: f.summary.trim(), all_day: f.all_day, description: f.description.trim() || null }
    if (f.all_day) {
      payload.start = f.date
      payload.end = f.date
    } else {
      payload.start = `${f.date}T${f.start}:00`
      payload.end = `${f.date}T${f.end}:00`
    }
    await api.addCalendarEvent(payload)
    toast('Событие создано', 'good')
    addOpen.value = false
    selected.value = f.date
    await loadEvents()
  } catch (error) {
    notifyError(error)
  } finally {
    addBusy.value = false
  }
}

async function removeEvent(ev) {
  if (!confirm(`Удалить «${ev.summary}» из календаря?`)) return
  try {
    await api.deleteCalendarEvent(ev.uid)
    toast('Событие удалено', 'good')
    await loadEvents()
  } catch (error) {
    notifyError(error)
  }
}

async function toggleTask(todo) {
  try {
    const data = await api.patchTodo(todo.id, { done: true })
    todos.value = data.todos
  } catch (error) {
    notifyError(error)
  }
}

const selectedDateLabel = computed(() => {
  if (!selected.value) return ''
  const [y, m, d] = selected.value.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return `${WEEKDAYS[date.getDay()]}, ${d} ${MONTHS[m - 1].toLowerCase()}`
})
</script>

<template>
  <div class="space-y-4">
    <!-- Подключение -->
    <section v-if="!status.connected && !loading" class="card p-5 text-center" v-reveal>
      <p class="text-[15px]">Календарь не подключён</p>
      <p class="mx-auto mt-1 max-w-sm text-[13px] text-[var(--color-muted)]">
        Подключи свой iCloud-календарь, чтобы видеть расписание с телефона.
      </p>
      <button class="btn btn-primary mt-4" @click="openSettings">Подключить iCloud</button>
    </section>

    <!-- Сетка месяца -->
    <section class="card overflow-hidden" v-reveal="60">
      <div class="flex items-center justify-between px-4 pt-4">
        <button class="grid h-8 w-8 place-items-center rounded-lg text-[var(--color-muted)] transition-colors hover:bg-black/[0.04] hover:text-[var(--color-ink)]" @click="prevMonth">
          <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6" /></svg>
        </button>
        <div class="text-center">
          <h1 class="text-[16px] font-medium">{{ monthLabel }}</h1>
          <button class="mt-0.5 text-[11.5px] text-[var(--color-accent)] transition-opacity hover:opacity-75" @click="goToday">сегодня</button>
        </div>
        <button class="grid h-8 w-8 place-items-center rounded-lg text-[var(--color-muted)] transition-colors hover:bg-black/[0.04] hover:text-[var(--color-ink)]" @click="nextMonth">
          <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6" /></svg>
        </button>
      </div>

      <div class="mt-3 grid grid-cols-7 border-b border-[var(--color-line)] text-center">
        <div v-for="wd in WEEKDAYS" :key="wd" class="py-2 text-[11px] uppercase tracking-wide text-[var(--color-muted)]">{{ wd }}</div>
      </div>

      <div class="grid grid-cols-7">
        <button
          v-for="(d, i) in days"
          :key="i"
          class="relative flex aspect-square flex-col items-center justify-center transition-colors"
          :class="inCurrentMonth(d) ? 'text-[var(--color-ink)]' : 'text-[var(--color-muted)]/40'"
          @click="pickDay(d)"
        >
          <span
            class="grid h-8 w-8 place-items-center rounded-full text-[13.5px] transition-all"
            :class="[
              isToday(d) ? 'border border-[var(--color-accent)] text-[var(--color-accent)]' : '',
              selected === iso(d) ? '!border-transparent bg-gradient-to-br from-[#ffb46b] to-[#ff8a5c] font-medium !text-[#2a1608]' : '',
            ]"
          >
            {{ d.getDate() }}
          </span>
          <span class="mt-1 flex h-1.5 items-center gap-0.5">
            <span
              v-for="(dot, j) in dayDots(iso(d)).dots"
              :key="j"
              class="h-1.5 w-1.5 rounded-full"
              :class="dot === 'event' ? 'bg-[var(--color-accent)]' : 'bg-[var(--color-good)]'"
            ></span>
            <span v-if="dayDots(iso(d)).extra > 0" class="text-[9px] leading-none text-[var(--color-muted)]">
              +{{ dayDots(iso(d)).extra }}
            </span>
          </span>
        </button>
      </div>
    </section>

    <!-- События выбранного дня -->
    <section class="space-y-2">
      <div class="flex items-center justify-between px-1">
        <h2 class="text-[13px] text-[var(--color-muted)]">{{ selectedDateLabel || 'Выбери день' }}</h2>
        <button
          v-if="status.connected && selected"
          class="text-[12.5px] font-medium text-[var(--color-accent)] transition-opacity hover:opacity-75"
          @click="openAdd"
        >
          + событие
        </button>
      </div>

      <!-- Задачи на день -->
      <div v-if="selected && selectedTasks.length" class="card divide-y divide-[var(--color-line)] overflow-hidden">
        <div v-for="t in selectedTasks" :key="t.id" class="flex items-center gap-3 px-4 py-3">
          <button
            class="grid h-5 w-5 shrink-0 place-items-center rounded-full border border-[var(--color-line-strong)] transition-colors hover:border-[var(--color-good)] hover:bg-[var(--color-good)]/15"
            title="Выполнено"
            @click="toggleTask(t)"
          >
            <svg viewBox="0 0 24 24" class="h-3 w-3 text-[var(--color-good)]" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 6" /></svg>
          </button>
          <div class="min-w-0 flex-1">
            <p class="text-[14px] leading-snug">{{ t.text }}</p>
            <p v-if="t.note" class="mt-0.5 text-[11.5px] text-[var(--color-muted)]">{{ t.note }}</p>
          </div>
          <span class="shrink-0 text-[11px] text-[var(--color-good)]">задача</span>
        </div>
      </div>

      <div v-if="selected && selectedEvents.length" class="card divide-y divide-[var(--color-line)] overflow-hidden">
        <div v-for="ev in selectedEvents" :key="ev.uid" class="flex items-start gap-3 px-4 py-3">
          <span class="w-12 shrink-0 pt-0.5 text-[12px] tabular text-[var(--color-accent)]">{{ timeLabel(ev) }}</span>
          <div class="min-w-0 flex-1">
            <p class="text-[14px] leading-snug">{{ ev.summary }}</p>
            <p v-if="ev.location" class="mt-0.5 text-[11.5px] text-[var(--color-muted)]">📍 {{ ev.location }}</p>
            <p v-if="ev.description" class="mt-0.5 text-[11.5px] text-[var(--color-muted)]">{{ ev.description }}</p>
          </div>
          <button class="shrink-0 text-[12px] text-[var(--color-muted)] transition-colors hover:text-[var(--color-bad)]" @click="removeEvent(ev)">удал.</button>
        </div>
      </div>

      <div v-else-if="selected && !selectedTasks.length && !selectedEvents.length" class="card p-6 text-center text-[13px] text-[var(--color-muted)]">
        На этот день ничего не записано
      </div>
    </section>

    <!-- Настройки подключения -->
    <Modal v-if="settingsOpen" :title="status.connected ? 'Календарь iCloud' : 'Подключить iCloud'" @close="settingsOpen = false">
      <form class="space-y-3" @submit.prevent="saveSettings">
        <label class="block">
          <span class="mb-1.5 block text-[12px] text-[var(--color-muted)]">Apple ID (email)</span>
          <input v-model="settingsForm.username" class="field" type="email" autocomplete="username" placeholder="you@icloud.com" />
        </label>
        <label class="block">
          <span class="mb-1.5 block text-[12px] text-[var(--color-muted)]">Пароль приложения</span>
          <input v-model="settingsForm.password" class="field" type="password" autocomplete="off" placeholder="xxxx-xxxx-xxxx-xxxx" />
          <span class="mt-1 block text-[11px] text-[var(--color-muted)]">
            Создай в appleid.apple.com → «Пароли приложений». Оставь пустым, чтобы не менять.
          </span>
        </label>
        <label v-if="status.calendars.length" class="block">
          <span class="mb-1.5 block text-[12px] text-[var(--color-muted)]">Календарь</span>
          <select v-model="settingsForm.calendar" class="field">
            <option value="" disabled>Выбери календарь…</option>
            <option v-for="cal in status.calendars" :key="cal.url" :value="cal.name">{{ cal.name }}</option>
          </select>
          <span class="mt-1 block text-[11px] text-[var(--color-muted)]">
            Выбери тот, где лежат твои события (обычно «Домашний» или «Calendar», не «Напоминания»).
          </span>
        </label>
        <div class="flex gap-2 pt-1">
          <button type="button" class="btn btn-ghost flex-1" @click="settingsOpen = false">Отмена</button>
          <button class="btn btn-primary flex-1" :disabled="settingsBusy">{{ settingsBusy ? 'Проверяю…' : 'Сохранить' }}</button>
        </div>

        <div v-if="status.connected" class="border-t border-[var(--color-line)] pt-3">
          <button type="button" class="btn btn-ghost w-full text-[var(--color-bad)] transition-colors hover:border-[var(--color-bad)]" @click="disconnect">
            Выйти из iCloud
          </button>
        </div>
      </form>
    </Modal>

    <!-- Новое событие -->
    <Modal v-if="addOpen" title="Новое событие" @close="addOpen = false">
      <form class="space-y-3" @submit.prevent="saveEvent">
        <input v-model="addForm.summary" class="field" placeholder="Название" />
        <label class="flex items-center gap-2 text-[13px]">
          <input v-model="addForm.all_day" type="checkbox" class="h-4 w-4 accent-[var(--color-accent)]" />
          На весь день
        </label>
        <input v-model="addForm.date" type="date" class="field tabular" />
        <div v-if="!addForm.all_day" class="grid grid-cols-2 gap-2">
          <label class="block">
            <span class="mb-1 block text-[11.5px] text-[var(--color-muted)]">Начало</span>
            <input v-model="addForm.start" type="time" class="field tabular" />
          </label>
          <label class="block">
            <span class="mb-1 block text-[11.5px] text-[var(--color-muted)]">Конец</span>
            <input v-model="addForm.end" type="time" class="field tabular" />
          </label>
        </div>
        <input v-model="addForm.description" class="field" placeholder="Описание (необязательно)" />
        <div class="flex gap-2 pt-1">
          <button type="button" class="btn btn-ghost flex-1" @click="addOpen = false">Отмена</button>
          <button class="btn btn-primary flex-1" :disabled="addBusy">{{ addBusy ? 'Создаю…' : 'Создать' }}</button>
        </div>
      </form>
    </Modal>
  </div>
</template>
