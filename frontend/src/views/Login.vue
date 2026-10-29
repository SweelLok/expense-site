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
        <div class="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-[--color-ink] text-xl font-semibold text-white">€</div>
        <h1 class="text-[19px] font-medium tracking-tight">Траты</h1>
        <p class="mt-1 text-[13px] text-[--color-muted]">Личный трекер расходов</p>
      </div>

      <form class="card space-y-3 p-5" @submit.prevent="submit">
        <label class="block">
          <span class="mb-1.5 block text-[12px] text-[--color-muted]">Логин</span>
          <input v-model="username" class="field" autocomplete="username" autocapitalize="none" required />
        </label>
        <label class="block">
          <span class="mb-1.5 block text-[12px] text-[--color-muted]">Пароль</span>
          <input v-model="password" type="password" class="field" autocomplete="current-password" required />
        </label>

        <Transition name="page">
          <p v-if="error" class="rounded-xl bg-[#fef2f2] px-3 py-2 text-[12.5px] text-[--color-bad]">{{ error }}</p>
        </Transition>

        <button class="btn btn-primary w-full" :disabled="busy">
          {{ busy ? 'Проверяю…' : 'Войти' }}
        </button>
      </form>

      <p class="mt-6 text-center text-[12px] text-[--color-muted]">Доступ только для владельца аккаунта</p>
    </div>
  </div>
</template>
