<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { notifyError, toast } from '../store'
import Modal from '../components/Modal.vue'

const notes = ref([])
const loading = ref(true)

const editing = ref(null)          // объект заметки или null
const isNew = ref(false)
const form = ref({ title: '', body: '' })
const saving = ref(false)

const pinned = computed(() => notes.value.filter((n) => n.pinned))
const others = computed(() => notes.value.filter((n) => !n.pinned))

async function load() {
  try {
    const data = await api.notes()
    notes.value = data.notes
  } catch (error) {
    notifyError(error)
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openNew() {
  isNew.value = true
  editing.value = null
  form.value = { title: '', body: '' }
}

function openEdit(note) {
  isNew.value = false
  editing.value = note
  form.value = { title: note.title || '', body: note.body || '' }
}

function close() {
  editing.value = null
  isNew.value = false
}

async function save() {
  saving.value = true
  try {
    let data
    if (isNew.value) {
      data = await api.addNote({ title: form.value.title.trim() || null, body: form.value.body })
    } else {
      data = await api.patchNote(editing.value.id, { title: form.value.title.trim() || null, body: form.value.body })
    }
    notes.value = data.notes
    toast(isNew.value ? 'Заметка создана' : 'Заметка обновлена', 'good')
    close()
  } catch (error) {
    notifyError(error)
  } finally {
    saving.value = false
  }
}

async function togglePin(note) {
  try {
    const data = await api.patchNote(note.id, { pinned: !note.pinned })
    notes.value = data.notes
  } catch (error) {
    notifyError(error)
  }
}

async function remove(note) {
  if (!confirm(`Удалить заметку${note.title ? ` «${note.title}»` : ''}?`)) return
  try {
    const data = await api.deleteNote(note.id)
    notes.value = data.notes
  } catch (error) {
    notifyError(error)
  }
}

function preview(body) {
  return (body || '').split('\n').slice(0, 4).join(' ').trim()
}

function updatedAt(note) {
  return (note.updated_at || '').replace(' ', ' · ').slice(0, 16)
}
</script>

<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between">
      <h1 class="px-1 text-[15px] font-medium">Заметки</h1>
      <button class="btn btn-primary text-[13px]" @click="openNew">+ Новая заметка</button>
    </div>

    <div v-if="loading" class="card animate-fade-in p-8 text-center text-[13px] text-[var(--color-muted)]">
      Загружаю…
    </div>

    <div v-else-if="!notes.length" class="card animate-fade-in p-10 text-center">
      <p class="text-[15px]">Заметок пока нет</p>
      <p class="mt-1 text-[13px] text-[var(--color-muted)]">Лови мысль, пока не улетела</p>
    </div>

    <template v-else>
      <section v-if="pinned.length" class="space-y-2">
        <h2 class="px-1 text-[13px] text-[var(--color-muted)]">Закреплённые</h2>
        <div class="grid gap-2 sm:grid-cols-2">
          <div v-for="note in pinned" :key="note.id" class="card card-hover cursor-pointer p-4" @click="openEdit(note)">
            <div class="flex items-start justify-between gap-2">
              <h3 class="min-w-0 truncate text-[14px] font-medium">{{ note.title || 'Без названия' }}</h3>
              <button class="shrink-0 text-[var(--color-accent)]" title="Открепить" @click.stop="togglePin(note)">📌</button>
            </div>
            <p v-if="note.body" class="mt-1.5 whitespace-pre-wrap text-[12.5px] leading-relaxed text-[var(--color-muted)]">
              {{ preview(note.body) }}
            </p>
            <p class="mt-2 text-[11px] text-[var(--color-muted)]/70">{{ updatedAt(note) }}</p>
          </div>
        </div>
      </section>

      <section class="space-y-2">
        <h2 v-if="pinned.length" class="px-1 text-[13px] text-[var(--color-muted)]">Остальные</h2>
        <div class="grid gap-2 sm:grid-cols-2">
          <div v-for="note in others" :key="note.id" class="card card-hover cursor-pointer p-4" @click="openEdit(note)">
            <div class="flex items-start justify-between gap-2">
              <h3 class="min-w-0 truncate text-[14px] font-medium">{{ note.title || 'Без названия' }}</h3>
              <button class="shrink-0 text-[var(--color-muted)] transition-colors hover:text-[var(--color-accent)]" title="Закрепить" @click.stop="togglePin(note)">
                <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 17v5M8 14l-3 3a1.5 1.5 0 002 2l3-3m0 0l5-5 3 3 2-7-7 2 3 3-5 5-1-1z" />
                </svg>
              </button>
            </div>
            <p v-if="note.body" class="mt-1.5 whitespace-pre-wrap text-[12.5px] leading-relaxed text-[var(--color-muted)]">
              {{ preview(note.body) }}
            </p>
            <div class="mt-2 flex items-center justify-between">
              <span class="text-[11px] text-[var(--color-muted)]/70">{{ updatedAt(note) }}</span>
              <button class="text-[11.5px] text-[var(--color-muted)] transition-colors hover:text-[var(--color-bad)]" @click.stop="remove(note)">удалить</button>
            </div>
          </div>
        </div>
      </section>
    </template>

    <Modal v-if="isNew || editing" :title="isNew ? 'Новая заметка' : 'Изменить заметку'" @close="close">
      <form class="space-y-3" @submit.prevent="save">
        <input v-model="form.title" class="field" placeholder="Название (необязательно)" />
        <textarea v-model="form.body" rows="8" class="field resize-none" placeholder="Текст заметки…"></textarea>
        <div class="flex gap-2 pt-1">
          <button type="button" class="btn btn-ghost flex-1" @click="close">Отмена</button>
          <button class="btn btn-primary flex-1" :disabled="saving">{{ saving ? 'Сохраняю…' : 'Сохранить' }}</button>
        </div>
      </form>
    </Modal>
  </div>
</template>
