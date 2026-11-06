<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { notifyError, toast } from '../store'
import Modal from '../components/Modal.vue'

const habits = ref([])
const log = ref([])          // [{habit_id, date}] — строки «выполнено»
const loading = ref(true)

const editing = ref(null)    // привычка или null
const isNew = ref(false)
const form = ref({ name: '', emoji: '' })
const saving = ref(false)

const WEEKDAYS_HEADER = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

// Готовые стикеры по категориям — выбираются тапом вместо ручного ввода эмодзи.
const EMOJI_GROUPS = [
  { label: 'Здоровье', emojis: ['💧', '🥗', '💊', '😴', '🚶', '🍎'] },
  { label: 'Спорт', emojis: ['💪', '🏃', '🧘', '🚴', '🏊', '⚽'] },
  { label: 'Учёба и работа', emojis: ['📚', '📝', '💻', '🎓', '🧠', '💼'] },
  { label: 'Дом и хобби', emojis: ['🎨', '🎸', '🌱', '🧹', '✍️', '🙏', '☀️'] },
]

const pad = (n) => String(n).padStart(2, '0')
function iso(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }

// Текущий месяц + листание по месяцам. При новом месяце страница сама покажет
// актуальный (viewMonth берётся от текущей даты при загрузке).
const now = new Date()
const viewYear = ref(now.getFullYear())
const viewMonth = ref(now.getMonth())   // 0–11

const monthLabel = computed(() => `${MONTHS[viewMonth.value]} ${viewYear.value}`)

// Ячейки месяца: null — пустые места перед первым числом (сетка с понедельника).
const monthCells = computed(() => {
  const first = new Date(viewYear.value, viewMonth.value, 1)
  const startWeekday = (first.getDay() + 6) % 7
  const daysInMonth = new Date(viewYear.value, viewMonth.value + 1, 0).getDate()
  const cells = []
  for (let i = 0; i < startWeekday; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(viewYear.value, viewMonth.value, d))
  return cells
})

function prevMonth() {
  if (viewMonth.value === 0) { viewMonth.value = 11; viewYear.value-- }
  else viewMonth.value--
}
function nextMonth() {
  if (viewMonth.value === 11) { viewMonth.value = 0; viewYear.value++ }
  else viewMonth.value++
}
function goToday() {
  const n = new Date()
  viewYear.value = n.getFullYear()
  viewMonth.value = n.getMonth()
}

const doneSet = computed(() => new Set(log.value.map((l) => `${l.habit_id}:${l.date}`)))
const todayISO = iso(new Date())

const isDone = (hid, d) => doneSet.value.has(`${hid}:${iso(d)}`)

function streak(hid) {
  let n = 0
  const d = new Date()
  if (!isDone(hid, d)) d.setDate(d.getDate() - 1)
  while (isDone(hid, d)) { n++; d.setDate(d.getDate() - 1) }
  return n
}

function cellClass(hid, d) {
  const dayISO = iso(d)
  if (isDone(hid, d)) return 'bg-gradient-to-br from-[#ffb46b] to-[#ff8a5c] font-medium text-[#2a1608]'
  if (dayISO > todayISO) return 'border border-[var(--color-line)] text-[var(--color-muted)]/40'
  if (dayISO === todayISO) return 'border border-[var(--color-accent)] text-[var(--color-accent)]'
  return 'border border-[var(--color-line-strong)] text-[var(--color-ink)]'
}

async function load() {
  const endD = new Date()
  const startD = new Date(); startD.setDate(startD.getDate() - 730)
  try {
    const data = await api.habits(iso(startD), iso(endD))
    habits.value = data.habits
    log.value = data.log
  } catch (error) {
    notifyError(error)
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function toggle(hid, d) {
  const date = iso(d)
  if (date > todayISO) return
  const done = !isDone(hid, d)
  // оптимистично обновляем список
  if (done) log.value.push({ habit_id: hid, date })
  else log.value = log.value.filter((l) => !(l.habit_id === hid && l.date === date))
  try {
    await api.markHabit(hid, { date, done })
  } catch (error) {
    notifyError(error)
    await load() // откат к серверному состоянию
  }
}

function openNew() { isNew.value = true; editing.value = null; form.value = { name: '', emoji: '' } }
function openEdit(h) { isNew.value = false; editing.value = h; form.value = { name: h.name, emoji: h.emoji || '' } }
function close() { editing.value = null; isNew.value = false }

async function save() {
  if (!form.value.name.trim()) return toast('Напиши название привычки', 'warn')
  saving.value = true
  try {
    if (isNew.value) {
      await api.addHabit({ name: form.value.name.trim(), emoji: form.value.emoji.trim() || null })
    } else {
      await api.patchHabit(editing.value.id, { name: form.value.name.trim(), emoji: form.value.emoji.trim() })
    }
    toast(isNew.value ? 'Привычка добавлена' : 'Сохранено', 'good')
    close()
    await load()
  } catch (error) {
    notifyError(error)
  } finally {
    saving.value = false
  }
}

async function remove(h) {
  if (!confirm(`Удалить привычку «${h.name}» и всю её историю?`)) return
  try {
    await api.deleteHabit(h.id)
    await load()
  } catch (error) {
    notifyError(error)
  }
}
</script>

<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between">
      <h1 class="px-1 text-[15px] font-medium">Привычки</h1>
      <button class="btn btn-primary text-[13px]" @click="openNew">+ Привычка</button>
    </div>

    <div v-if="loading" class="card p-8 text-center text-[13px] text-[var(--color-muted)]">Загружаю…</div>

    <section v-else class="card p-4" v-reveal>
      <div class="flex items-center justify-between">
        <button class="grid h-8 w-8 place-items-center rounded-lg text-[var(--color-muted)] transition-colors hover:bg-black/[0.04] hover:text-[var(--color-ink)]" @click="prevMonth">
          <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6" /></svg>
        </button>
        <div class="text-center">
          <p class="text-[15px] font-medium">{{ monthLabel }}</p>
          <button class="mt-0.5 text-[11px] text-[var(--color-accent)] transition-opacity hover:opacity-75" @click="goToday">сегодня</button>
        </div>
        <button class="grid h-8 w-8 place-items-center rounded-lg text-[var(--color-muted)] transition-colors hover:bg-black/[0.04] hover:text-[var(--color-ink)]" @click="nextMonth">
          <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6" /></svg>
        </button>
      </div>

      <div class="mt-3 grid grid-cols-7 text-center">
        <span v-for="wd in WEEKDAYS_HEADER" :key="wd" class="py-1 text-[10px] uppercase tracking-wide text-[var(--color-muted)]">{{ wd }}</span>
      </div>

      <p v-if="!habits.length" class="py-10 text-center text-[13px] text-[var(--color-muted)]">Привычек пока нет — добавь первую</p>

      <div v-else class="mt-1 divide-y divide-[var(--color-line)]">
        <div v-for="h in habits" :key="h.id" class="py-3">
          <div class="flex items-center gap-2.5">
            <span class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[var(--color-accent)]/10 text-[16px]">{{ h.emoji || '✓' }}</span>
            <div class="min-w-0 flex-1">
              <p class="truncate text-[13.5px] font-medium">{{ h.name }}</p>
              <p class="text-[11px] text-[var(--color-muted)]">
                <span v-if="streak(h.id)" class="font-medium text-[var(--color-accent)]">🔥 {{ streak(h.id) }} дн. подряд</span>
                <span v-else>пока без серии</span>
              </p>
            </div>
            <button class="shrink-0 text-[12px] text-[var(--color-muted)] transition-colors hover:text-[var(--color-ink)]" @click="openEdit(h)">изм.</button>
          </div>

          <div class="mt-2 grid grid-cols-7 gap-y-1">
            <template v-for="(d, i) in monthCells" :key="i">
              <div v-if="!d" class="h-8"></div>
              <button
                v-else
                class="mx-auto grid h-8 w-8 place-items-center rounded-full text-[11.5px] transition-all"
                :class="cellClass(h.id, d)"
                @click="toggle(h.id, d)"
              >
                {{ d.getDate() }}
              </button>
            </template>
          </div>
        </div>
      </div>
    </section>

    <Modal v-if="isNew || editing" :title="isNew ? 'Новая привычка' : 'Изменить привычку'" @close="close">
      <form class="space-y-3" @submit.prevent="save">
        <div class="flex items-center gap-2">
          <span class="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[var(--color-accent)]/10 text-[20px]">{{ form.emoji || '·' }}</span>
          <input v-model="form.name" class="field min-w-0 flex-1" placeholder="Название привычки" />
        </div>

        <div class="space-y-2.5">
          <div v-for="group in EMOJI_GROUPS" :key="group.label" class="space-y-1">
            <p class="text-[10.5px] text-[var(--color-muted)]">{{ group.label }}</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="e in group.emojis"
                :key="e"
                type="button"
                class="grid h-9 w-9 place-items-center rounded-lg text-[18px] transition-all"
                :class="form.emoji === e
                  ? 'bg-[var(--color-accent)]/15 ring-1 ring-[var(--color-accent)]'
                  : 'bg-black/[0.03] hover:bg-black/[0.06]'"
                @click="form.emoji = e"
              >{{ e }}</button>
            </div>
          </div>
          <button
            v-if="form.emoji"
            type="button"
            class="text-[11.5px] text-[var(--color-muted)] transition-colors hover:text-[var(--color-bad)]"
            @click="form.emoji = ''"
          >
            Убрать стикер
          </button>
        </div>
        <div class="flex gap-2 pt-1">
          <button v-if="!isNew" type="button" class="btn btn-ghost flex-1 text-[var(--color-bad)]" @click="remove(editing)">Удалить</button>
          <button v-else type="button" class="btn btn-ghost flex-1" @click="close">Отмена</button>
          <button class="btn btn-primary flex-1" :disabled="saving">{{ saving ? 'Сохраняю…' : (isNew ? 'Добавить' : 'Сохранить') }}</button>
        </div>
      </form>
    </Modal>
  </div>
</template>
