<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { state, bootstrap, toast } from '../store'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

onMounted(async () => {
  if (!state.authed) await bootstrap()
  if (state.authed) router.push({ name: 'dashboard' })
})

async function submit() {
  if (busy.value) return
  error.value = ''
  busy.value = true
  try {
    await api.login(username.value.trim(), password.value)
    await bootstrap()
    toast('Добро пожаловать', 'good')
    router.push(route.query.next || { name: 'dashboard' })
  } catch (err) {
    error.value = err.message
    password.value = ''
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="grid min-h-full place-items-center px-4 py-16">
    <div class="w-full max-w-sm animate-fade-up">
      <div class="mb-8 text-center">
        <div class="relative mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-gradient-to-br from-[#ffb46b] to-[#ff8a5c] shadow-[0_0_28px_-6px_rgba(255,158,92,0.7)]">
          <span class="h-3.5 w-3.5 rounded-full bg-white/85"></span>
        </div>
        <h1 class="text-[19px] font-medium tracking-tight">Орбита</h1>
        <p class="mt-1 text-[13px] text-[var(--color-muted)]">Календарь · задачи · заметки · траты</p>
      </div>

      <form class="card space-y-3 p-5" @submit.prevent="submit">
        <label class="block">
          <span class="mb-1.5 block text-[12px] text-[var(--color-muted)]">Логин</span>
          <input v-model="username" class="field" autocomplete="username" autocapitalize="none" required />
        </label>
        <label class="block">
          <span class="mb-1.5 block text-[12px] text-[var(--color-muted)]">Пароль</span>
          <input v-model="password" type="password" class="field" autocomplete="current-password" required />
        </label>

        <Transition name="page">
          <p v-if="error" class="rounded-xl bg-[var(--color-bad)]/10 px-3 py-2 text-[12.5px] text-[var(--color-bad)]">{{ error }}</p>
        </Transition>

        <button class="btn btn-primary w-full" :disabled="busy">
          {{ busy ? 'Проверяю…' : 'Войти' }}
        </button>
      </form>

      <p class="mt-6 text-center text-[12px] text-[var(--color-muted)]">Доступ только для владельца аккаунта</p>
    </div>
  </div>
</template>
