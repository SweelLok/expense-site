<script setup>
import { onMounted, onUnmounted } from 'vue'

defineProps({
  title: { type: String, default: '' },
  width: { type: String, default: '28rem' },
})
const emit = defineEmits(['close'])

const onKey = (event) => {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <Transition name="page" appear>
      <div class="fixed inset-0 z-50 flex items-end justify-center bg-black/30 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" @click.self="emit('close')">
        <div
          class="card animate-pop w-full rounded-b-none p-5 shadow-[0_30px_90px_-40px_rgba(0,0,0,0.85)] sm:rounded-2xl"
          :style="{ maxWidth: width }"
        >
          <div class="mb-4 flex items-start justify-between gap-4">
            <h2 class="text-[15px] font-medium">{{ title }}</h2>
            <button class="text-[var(--color-muted)] transition-colors hover:text-[var(--color-ink)]" @click="emit('close')">✕</button>
          </div>
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
