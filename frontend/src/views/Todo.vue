<script setup>
import { computed, ref, onMounted } from 'vue'
import { api } from '../api'
import { notifyError, toast, todayISO } from '../store'
import Modal from '../components/Modal.vue'

const todos = ref([])
const loading = ref(true)
const showDone = ref(false)

const newText = ref('')
const newDate = ref('')
const newNote = ref('')
const adding = ref(false)

const editing = ref(null)
const editForm = ref({ text: '', due_date: '', note: '' })
const saving = ref(false)

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']

function isoOffset(days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function dayLabel(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return `${WEEKDAYS[date.getDay()]}, ${d} ${MONTHS[date.getMonth()]}`
}

const active = computed(() => todos.value.filter((t) => !t.done))
const done = computed(() => todos.value.filter((t) => t.done))

const groups = computed(() => {
  const today = todayISO()
  const tomorrow = isoOffset(1)
  const overdue = []
  const todayG = []
  const tomorrowG = []
  const upcoming = []
  const nodate = []
  for (const t of active.value) {
    if (!t.due_date) nodate.push(t)
    else if (t.due_date < today) overdue.push(t)
    else if (t.due_date === today) todayG.push(t)
    else if (t.due_date === tomorrow) tomorrowG.push(t)
    else upcoming.push(t)
  }
  upcoming.sort((a, b) => a.due_date.localeCompare(b.due_date))
  const list = [
    { key: 'overdue', label: 'Просрочено', items: overdue, tone: 'bad' },
    { key: 'today', label: 'Сегодня', items: todayG },
    { key: 'tomorrow', label: 'Завтра', items: tomorrowG },
    { key: 'upcoming', label: 'Дальше', items: upcoming, dated: true },
    { key: 'nodate', label: 'Без даты', items: nodate },
  ]
  if (done.value.length) list.push({ key: 'done', label: `Выполнено · ${done.value.length}`, items: done.value, done: true })
  return list.filter((g) => g.items.length)
})

async function load() {
  try {
    const data = await api.todos()
    todos.value = data.todos
  } catch (error) {
    notifyError(error)
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function add() {
  const text = newText.value.trim()
  if (!text) return toast('Напиши задачу', 'warn')
  adding.value = true
  try {
    const data = await api.addTodo({ text, due_date: newDate.value || null, note: newNote.value.trim() || null })
    todos.value = data.todos
    newText.value = ''
    newDate.value = ''
    newNote.value = ''
  } catch (error) {
    notifyError(error)
  } finally {
    adding.value = false
  }
}

async function toggle(todo) {
  try {
    const data = await api.patchTodo(todo.id, { done: !todo.done })
    todos.value = data.todos
  } catch (error) {
    notifyError(error)
  }
}

function startEdit(todo) {
  editing.value = todo
  editForm.value = { text: todo.text, due_date: todo.due_date || '', note: todo.note || '' }
}

async function saveEdit() {
  if (!editForm.value.text.trim()) return
  saving.value = true
  try {
    const data = await api.patchTodo(editing.value.id, {
      text: editForm.value.text.trim(),
      due_date: editForm.value.due_date || '',
      note: editForm.value.note.trim(),
    })
    todos.value = data.todos
    editing.value = null
  } catch (error) {
    notifyError(error)
  } finally {
    saving.value = false
  }
}

async function remove(todo) {
  if (!confirm(`Удалить задачу «${todo.text}»?`)) return
  try {
    const data = await api.deleteTodo(todo.id)
    todos.value = data.todos
  } catch (error) {
    notifyError(error)
  }
}
</script>

<template>
  <div class="space-y-5">
    <!-- Быстрое добавление -->
    <section class="card p-4" v-reveal>
      <div class="flex gap-2">
        <input
          v-model="newText"
          class="field min-w-0 flex-1"
          placeholder="Новая задача…"
          @keyup.enter="add"
        />
        <button class="btn btn-primary shrink-0" :disabled="adding" @click="add">
          {{ adding ? '…' : 'Добавить' }}
        </button>
      </div>
      <div class="mt-2 grid gap-2 sm:grid-cols-2">
        <input v-model="newDate" type="date" class="field tabular" />
        <input v-model="newNote" placeholder="Заметка (необязательно)" class="field" />
      </div>
    </section>

    <div v-if="loading" class="card animate-fade-in p-8 text-center text-[13px] text-[var(--color-muted)]">
      Загружаю…
    </div>

    <div v-else-if="!groups.length" class="card animate-fade-in p-10 text-center">
      <p class="text-[15px]">Пока пусто</p>
      <p class="mt-1 text-[13px] text-[var(--color-muted)]">Добавь первую задачу — и вперёд</p>
    </div>

    <section v-for="group in groups" :key="group.key" class="space-y-2" v-reveal>
      <h2 class="px-1 text-[13px]" :class="group.tone === 'bad' ? 'text-[var(--color-bad)]' : 'text-[var(--color-muted)]'">
        {{ group.label }}
      </h2>
      <div class="card divide-y divide-[var(--color-line)] overflow-hidden">
        <TransitionGroup name="list" tag="div" class="relative">
          <div v-for="todo in group.items" :key="todo.id" class="group flex items-start gap-3 px-4 py-3">
            <button
              class="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border transition-colors"
              :class="todo.done ? 'border-[var(--color-good)] bg-[var(--color-good)]/20 text-[var(--color-good)]' : 'border-[var(--color-line-strong)] hover:border-[var(--color-accent)]'"
              @click="toggle(todo)"
            >
              <svg v-if="todo.done" viewBox="0 0 24 24" class="h-3 w-3" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <path d="M5 12l5 5L20 6" />
              </svg>
            </button>
            <div class="min-w-0 flex-1">
              <p class="text-[14px] leading-snug" :class="todo.done ? 'text-[var(--color-muted)] line-through' : ''">
                {{ todo.text }}
              </p>
              <p v-if="todo.note" class="mt-0.5 text-[12px] text-[var(--color-muted)]">{{ todo.note }}</p>
              <p v-if="todo.due_date && !todo.done" class="mt-0.5 text-[11.5px] text-[var(--color-accent)]">
                {{ dayLabel(todo.due_date) }}
              </p>
            </div>
            <button class="shrink-0 text-[12px] text-[var(--color-muted)] transition-colors hover:text-[var(--color-ink)]" @click="startEdit(todo)">изм.</button>
            <button class="shrink-0 text-[12px] text-[var(--color-muted)] transition-colors hover:text-[var(--color-bad)]" @click="remove(todo)">удал.</button>
          </div>
        </TransitionGroup>
      </div>
    </section>

    <Modal v-if="editing" title="Изменить задачу" @close="editing = null">
      <form class="space-y-3" @submit.prevent="saveEdit">
        <input v-model="editForm.text" class="field" placeholder="Задача" />
        <input v-model="editForm.due_date" type="date" class="field tabular" />
        <textarea v-model="editForm.note" rows="2" class="field resize-none" placeholder="Заметка"></textarea>
        <div class="flex gap-2 pt-1">
          <button type="button" class="btn btn-ghost flex-1" @click="editing = null">Отмена</button>
          <button class="btn btn-primary flex-1" :disabled="saving">Сохранить</button>
        </div>
      </form>
    </Modal>
  </div>
</template>
