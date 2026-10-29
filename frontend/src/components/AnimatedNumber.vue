<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  value: { type: Number, default: 0 },
  decimals: { type: Number, default: 2 },
  duration: { type: Number, default: 650 },
})

// Начальное значение — сразу финальное: если rAF в этой вкладке не тикает
// (фон, headless), пользователь увидит верное число, а не 0.
const shown = ref(Number(props.value) || 0)
let frame = null
let safety = null

const format = (number) =>
  new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: props.decimals,
    maximumFractionDigits: props.decimals,
  }).format(number)

function stop() {
  cancelAnimationFrame(frame)
  clearTimeout(safety)
}

function animate(from, to) {
  stop()
  const start = performance.now()
  const step = (now) => {
    const progress = Math.min(1, (now - start) / props.duration)
    const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
    shown.value = progress < 1 ? from + (to - from) * eased : to
    if (progress < 1) frame = requestAnimationFrame(step)
  }
  frame = requestAnimationFrame(step)
  // Страховка: rAF может встать на паузу (вкладка ушла в фон) — доводим цифру таймером.
  safety = setTimeout(() => {
    shown.value = to
    cancelAnimationFrame(frame)
  }, props.duration + 150)
}

watch(
  () => props.value,
  (next, previous) => animate(Number(previous) || 0, Number(next) || 0)
)

onMounted(() => {
  if (document.visibilityState !== 'visible') return // нечего анимировать, число уже верное
  animate(0, Number(props.value) || 0)
})

onUnmounted(stop)
</script>

<template>
  <span class="tabular">{{ format(shown) }}</span>
</template>
