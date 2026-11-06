<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { state, toast } from './store'
import SpaceBackground from './components/SpaceBackground.vue'

const route = useRoute()
const router = useRouter()

// Главные разделы — всегда на виду. Всё остальное прячем под «Ещё» (десктоп)
// и в выдвижную панель (телефон), чтобы навбар не разрастался.
const primary = [
  { name: 'calendar', label: 'Календарь', icon: 'M7 3h10M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1zM4 9h16M9 3v3M15 3v3' },
  { name: 'todo', label: 'Задачи', icon: 'M9 12l2 2 4-4M12 21a9 9 0 100-18 9 9 0 000 18z' },
  { name: 'notes', label: 'Заметки', icon: 'M7 3h7l5 5v13H7a1 1 0 01-1-1V4a1 1 0 011-1zM14 3v5h5M9 13h6M9 17h4' },
  { name: 'habits', label: 'Привычки', icon: 'M17 2l4 4-4 4M3 11V9a4 4 0 014-4h14M7 22l-4-4 4-4M21 13v2a4 4 0 01-4 4H3' },
]
const menu = [
  { name: 'dashboard', label: 'Траты', icon: 'M3 12l9-8 9 8v8a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z' },
  { name: 'stats', label: 'Статистика', icon: 'M4 20V10m5 10V4m5 16v-7m5 7V8' },
  { name: 'subs', label: 'Подписки', icon: 'M4 7h16M4 12h16M4 17h10' },
  { name: 'admin', label: 'Настройки', icon: 'M12 3l8 4v5c0 5-3.4 8.3-8 9-4.6-.7-8-4-8-9V7z' },
]

const isLogin = computed(() => route.name === 'login')
const moreOpen = ref(false)
const drawerOpen = ref(false)

function closeMore() { moreOpen.value = false }
function toggleMore() { moreOpen.value = !moreOpen.value }
function closeDrawer() { drawerOpen.value = false }

function onDocClick(event) {
  if (moreOpen.value && !event.target.closest('[data-more]')) closeMore()
}
onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))

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
  <div class="relative min-h-full">
    <SpaceBackground />

    <template v-if="!isLogin">
      <header class="sticky top-0 z-30 border-b border-[var(--color-line)] bg-[var(--color-bg)]/70 backdrop-blur-xl">
        <div class="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <RouterLink :to="{ name: 'dashboard' }" class="flex items-center gap-2.5">
            <span class="relative grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-[#ffb46b] to-[#ff8a5c] shadow-[0_0_18px_-4px_rgba(255,158,92,0.7)]">
              <span class="h-2 w-2 rounded-full bg-white/85"></span>
            </span>
            <span class="text-[15px] font-medium tracking-tight">Орбита</span>
          </RouterLink>

          <!-- Десктоп: три главных раздела + «Ещё» -->
          <nav class="ml-auto hidden items-center gap-0.5 sm:flex">
            <RouterLink
              v-for="item in primary"
              :key="item.name"
              :to="{ name: item.name }"
              class="rounded-lg px-3 py-1.5 text-[13px] text-[var(--color-muted)] transition-colors duration-200 hover:text-[var(--color-ink)]"
              active-class="!text-[var(--color-accent)] bg-[var(--color-accent)]/10"
            >
              {{ item.label }}
            </RouterLink>

            <div class="relative" data-more>
              <button
                class="flex items-center gap-1 rounded-lg px-3 py-1.5 text-[13px] transition-colors duration-200"
                :class="moreOpen ? 'text-[var(--color-ink)]' : 'text-[var(--color-muted)] hover:text-[var(--color-ink)]'"
                @click.stop="toggleMore"
              >
                Ещё
                <svg viewBox="0 0 24 24" class="h-3.5 w-3.5 transition-transform" :class="moreOpen ? 'rotate-180' : ''" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </button>

              <Transition name="page">
                <div v-if="moreOpen" class="absolute right-0 top-full z-40 mt-2 w-52 card p-1.5">
                  <RouterLink
                    v-for="item in menu"
                    :key="item.name"
                    :to="{ name: item.name }"
                    class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13.5px] transition-colors"
                    :class="route.name === item.name ? 'text-[var(--color-accent)]' : 'text-[var(--color-ink)] hover:bg-black/[0.05]'"
                    @click="closeMore"
                  >
                    <svg viewBox="0 0 24 24" class="h-4 w-4 text-[var(--color-muted)]" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                      <path :d="item.icon" />
                    </svg>
                    {{ item.label }}
                  </RouterLink>
                  <div class="my-1 h-px bg-[var(--color-line)]"></div>
                  <button class="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-[13.5px] text-[var(--color-muted)] transition-colors hover:bg-black/[0.05] hover:text-[var(--color-bad)]" @click="closeMore(); logout()">
                    <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M15 12H4m0 0l4-4m-4 4l4 4M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3" />
                    </svg>
                    Выйти
                  </button>
                </div>
              </Transition>
            </div>
          </nav>

          <!-- Телефон: бургер → выдвижная панель -->
          <button
            class="ml-auto grid h-9 w-9 place-items-center rounded-lg text-[var(--color-muted)] transition-colors hover:text-[var(--color-ink)] sm:hidden"
            aria-label="Меню"
            @click="drawerOpen = true"
          >
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      </header>

      <main class="relative z-10 mx-auto max-w-3xl px-4 pb-20 pt-6">
        <RouterView v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>

      <!-- Выдвижная панель (телефон) -->
      <Teleport to="body">
        <div v-if="drawerOpen" class="fixed inset-0 z-50 sm:hidden">
          <div class="absolute inset-0 bg-black/30 backdrop-blur-[2px]" @click="closeDrawer"></div>
          <aside class="absolute right-0 top-0 flex h-full w-[82vw] max-w-[20rem] animate-drawer-in flex-col border-l border-[var(--color-line)] bg-[#fbfaf7] p-4">
            <div class="flex items-center justify-between">
              <span class="flex items-center gap-2.5">
                <span class="relative grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-[#ffb46b] to-[#ff8a5c]">
                  <span class="h-2 w-2 rounded-full bg-white/85"></span>
                </span>
                <span class="text-[15px] font-medium tracking-tight">Орбита</span>
              </span>
              <button class="grid h-8 w-8 place-items-center rounded-lg text-[var(--color-muted)] transition-colors hover:text-[var(--color-ink)]" aria-label="Закрыть" @click="closeDrawer">
                <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </div>

            <nav class="mt-4 flex flex-1 flex-col gap-0.5 overflow-y-auto">
              <p class="px-3 pb-1.5 pt-2 text-[11px] uppercase tracking-wide text-[var(--color-muted)]">Основное</p>
              <RouterLink
                v-for="item in primary"
                :key="item.name"
                :to="{ name: item.name }"
                class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-[14px] transition-colors"
                :class="route.name === item.name ? 'text-[var(--color-accent)] bg-[var(--color-accent)]/10' : 'text-[var(--color-ink)] hover:bg-black/[0.05]'"
                @click="closeDrawer"
              >
                <svg viewBox="0 0 24 24" class="h-4.5 w-4.5 text-[var(--color-muted)]" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                  <path :d="item.icon" />
                </svg>
                {{ item.label }}
              </RouterLink>

              <p class="px-3 pb-1.5 pt-5 text-[11px] uppercase tracking-wide text-[var(--color-muted)]">Ещё</p>
              <RouterLink
                v-for="item in menu"
                :key="item.name"
                :to="{ name: item.name }"
                class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-[14px] transition-colors"
                :class="route.name === item.name ? 'text-[var(--color-accent)]' : 'text-[var(--color-ink)] hover:bg-black/[0.05]'"
                @click="closeDrawer"
              >
                <svg viewBox="0 0 24 24" class="h-4.5 w-4.5 text-[var(--color-muted)]" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                  <path :d="item.icon" />
                </svg>
                {{ item.label }}
              </RouterLink>
            </nav>

            <button class="mt-3 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-[14px] text-[var(--color-muted)] transition-colors hover:bg-black/[0.05] hover:text-[var(--color-bad)]" @click="closeDrawer(); logout()">
              <svg viewBox="0 0 24 24" class="h-4.5 w-4.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                <path d="M15 12H4m0 0l4-4m-4 4l4 4M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3" />
              </svg>
              Выйти
            </button>
          </aside>
        </div>
      </Teleport>
    </template>

    <RouterView v-else v-slot="{ Component }">
      <Transition name="page" mode="out-in">
        <component :is="Component" />
      </Transition>
    </RouterView>

    <div class="pointer-events-none fixed bottom-6 right-4 z-50 flex w-[min(92vw,22rem)] flex-col gap-2">
      <TransitionGroup name="list">
        <div
          v-for="item in state.toasts"
          :key="item.id"
          class="pointer-events-auto card animate-pop px-4 py-3 text-[13px] leading-snug"
          :class="{
            'border-l-2 border-l-[var(--color-warn)]': item.kind === 'warn',
            'border-l-2 border-l-[var(--color-bad)]': item.kind === 'bad',
            'border-l-2 border-l-[var(--color-good)]': item.kind === 'good',
          }"
        >
          {{ item.text }}
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>
