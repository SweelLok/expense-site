<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: Number, default: 0 },
  max: { type: Number, default: 1 },
  tone: { type: String, default: 'auto' }, // auto | good | warn | bad | accent
  height: { type: String, default: '6px' },
})

const percent = computed(() => {
  if (!props.max || props.max <= 0) return props.value > 0 ? 100 : 0
  return Math.max(0, Math.min(100, (props.value / props.max) * 100))
})

const color = computed(() => {
  if (props.tone !== 'auto') return `var(--color-${props.tone})`
  if (percent.value >= 100) return 'var(--color-bad)'
  if (percent.value >= 80) return 'var(--color-warn)'
  return 'var(--color-accent)'
})
</script>

<template>
  <div class="w-full overflow-hidden rounded-full bg-[#f1f1f4]" :style="{ height }">
    <div
      class="h-full rounded-full transition-[width,background-color] duration-700 ease-[cubic-bezier(0.22,1,0.36,1)]"
      :style="{ width: percent + '%', background: color }"
    />
  </div>
</template>
