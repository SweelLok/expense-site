<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { state, toast } from './store'

const route = useRoute()
const router = useRouter()

const nav = [
  { name: 'dashboard', label: 'Обзор', icon: 'M3 12l9-8 9 8v8a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z' },
  { name: 'stats', label: 'Статистика', icon: 'M4 20V10m5 10V4m5 16v-7m5 7V8' },
  { name: 'subs', label: 'Подписки', icon: 'M4 7h16M4 12h16M4 17h10' },
  { name: 'admin', label: 'Админка', icon: 'M12 3l8 4v5c0 5-3.4 8.3-8 9-4.6-.7-8-4-8-9V7z' },
]

const isLogin = computed(() => route.name === 'login')
const current = computed(() => state.overview?.plan)

async function logout() {
  try {
    await api.logout()
  } finally {
    state.authed = false
    state.overview = null
    toast('Вышел из аккаунта')
    router.push({ name: 'login' })
  }
}
</script>

<template>
  <div class="min-h-full">
    <template v-if="!isLogin">
      <header class="sticky top-0 z-30 border-b border-[--color-line] bg-[#fafafa]/85 backdrop-blur-md">
        <div class="mx-auto flex max-w-3xl items-center gap-4 px-4 py-3">
          <RouterLink :to="{ name: 'dashboard' }" class="flex items-center gap-2">
            <span class="grid h-7 w-7 place-items-center rounded-lg bg-[--color-ink] text-[13px] font-semibold text-white">€</span>
            <span class="text-[15px] font-medium tracking-tight">Траты</span>
          </RouterLink>

          <nav class="ml-auto hidden items-center gap-1 sm:flex">
            <RouterLink
              v-for="item in nav"
              :key="item.name"
              :to="{ name: item.name }"
              class="rounded-lg px-3 py-1.5 text-[13px] text-[--color-muted] transition-colors duration-200 hover:text-[--color-ink]"
              active-class="!text-[--color-ink] bg-white shadow-[0_1px_2px_rgba(15,15,16,0.06)]"
            >
              {{ item.label }}
            </RouterLink>
          </nav>

          <div class="ml-auto flex items-center gap-3 sm:ml-2">
            <span v-if="current" class="tabular hidden text-[13px] text-[--color-muted] md:inline">
              {{ state.overview.plan.balance.toFixed(2) }} €
            </span>
            <button class="text-[13px] text-[--color-muted] transition-colors hover:text-[--color-ink]" @click="logout">
              Выйти
            </button>
          </div>
        </div>
      </header>

      <main class="mx-auto max-w-3xl px-4 pb-28 pt-6 sm:pb-16">
        <RouterView v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>

      <nav class="fixed inset-x-0 bottom-0 z-30 border-t border-[--color-line] bg-white/95 backdrop-blur-md sm:hidden">
        <div class="flex">
          <RouterLink
            v-for="item in nav"
            :key="item.name"
            :to="{ name: item.name }"
            class="flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] text-[--color-muted] transition-colors"
            active-class="!text-[--color-ink]"
          >
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
              <path :d="item.icon" />
            </svg>
            {{ item.label }}
          </RouterLink>
        </div>
      </nav>
    </template>

    <RouterView v-else v-slot="{ Component }">
      <Transition name="page" mode="out-in">
        <component :is="Component" />
      </Transition>
    </RouterView>

    <div class="pointer-events-none fixed bottom-20 right-4 z-50 flex w-[min(92vw,22rem)] flex-col gap-2 sm:bottom-6">
      <TransitionGroup name="list">
        <div
          v-for="item in state.toasts"
          :key="item.id"
          class="pointer-events-auto card animate-pop px-4 py-3 text-[13px] leading-snug shadow-[0_10px_40px_-20px_rgba(15,15,16,0.45)]"
          :class="{
            'border-l-2 border-l-[--color-warn]': item.kind === 'warn',
            'border-l-2 border-l-[--color-bad]': item.kind === 'bad',
            'border-l-2 border-l-[--color-good]': item.kind === 'good',
          }"
        >
          {{ item.text }}
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>
