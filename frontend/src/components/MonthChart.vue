<script setup>
// График по месяцам: столбики — траты за месяц, линия — накопленная сумма.
// Две панели, а не одна совмещённая: у месячной суммы и у накопления разные
// масштабы, в общей системе координат одно из двух читалось бы неверно.
//
// SVG растягивается по ширине карточки, поэтому всё считается в единицах viewBox.
// Но текст и толщины линий так масштабировать нельзя: на телефоне подпись «ноя 25»
// превратилась бы в 6 px. Поэтому ширина контейнера измеряется ResizeObserver'ом,
// и размеры шрифта/линий пересчитываются в единицы так, чтобы на экране они
// оставались заданными в пикселях.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { eur } from '../api'

const props = defineProps({
  series: { type: Array, default: () => [] },
})

const W = 600
const PAD_L = 8
const PAD_R = 8
const PLOT_W = W - PAD_L - PAD_R

const BAR_TOP = 10
const BAR_H = 100
const BAR_BOTTOM = BAR_TOP + BAR_H

const AREA_TOP = 134
const AREA_H = 68
const AREA_BOTTOM = AREA_TOP + AREA_H

const AXIS_Y = 220
const H = 227

// Ширина контейнера в экранных пикселях — от неё зависит перевод «px → единицы viewBox».
const root = ref(null)
const boxWidth = ref(W)
let observer = null

onMounted(() => {
  const measure = () => {
    const width = root.value?.clientWidth
    if (width) boxWidth.value = width
  }
  measure()
  if (typeof ResizeObserver !== 'undefined' && root.value) {
    observer = new ResizeObserver(measure)
    observer.observe(root.value)
  } else {
    window.addEventListener('resize', measure)
    observer = { disconnect: () => window.removeEventListener('resize', measure) }
  }
})
onBeforeUnmount(() => observer?.disconnect())

// Сколько единиц viewBox приходится на один экранный пиксель (обратная величина).
const scale = computed(() => Math.max(0.15, boxWidth.value / W))
const units = (px) => (px / scale.value).toFixed(2)
const px = (value) => (value * scale.value)

const count = computed(() => props.series.length)
const slot = computed(() => PLOT_W / Math.max(1, count.value))
const barW = computed(() => Math.min(26, slot.value * 0.55))

const maxBar = computed(() => Math.max(1, ...props.series.map((m) => m.spent)))
const maxCum = computed(() => Math.max(1, ...props.series.map((m) => m.cumulative)))

const center = (index) => PAD_L + slot.value * index + slot.value / 2
const barHeight = (value) => (value > 0 ? Math.max(2, (value / maxBar.value) * BAR_H) : 0)
const cumY = (value) => AREA_BOTTOM - (value / maxCum.value) * AREA_H

const linePath = computed(() =>
  props.series.map((m, i) => `${i ? 'L' : 'M'}${center(i).toFixed(1)},${cumY(m.cumulative).toFixed(1)}`).join(' '),
)

const areaPath = computed(() => {
  if (!count.value) return ''
  const base = AREA_BOTTOM.toFixed(1)
  const points = props.series.map((m, i) => `L${center(i).toFixed(1)},${cumY(m.cumulative).toFixed(1)}`).join(' ')
  return `M${center(0).toFixed(1)},${base} ${points} L${center(count.value - 1).toFixed(1)},${base} Z`
})

// Подпись месяца занимает примерно 3.2 знака её кегля; показываем каждую, только
// если она помещается в свой слот, иначе — через одну (на телефоне) и реже.
// Отсчёт ведём от последнего месяца: текущий месяц подписан всегда, а «лишними»
// на узком экране оказываются старые месяцы слева.
const labelStep = computed(() => {
  const slotPx = px(slot.value)
  const labelPx = 11 * 3.2
  return Math.max(1, Math.ceil((labelPx + 6) / Math.max(1, slotPx)))
})
const showLabel = (index) => (count.value - 1 - index) % labelStep.value === 0

const hover = ref(null)
const focus = computed(() => props.series[hover.value ?? count.value - 1] || null)
</script>

<template>
  <div ref="root">
    <!-- Считыватель: месяц под курсором, иначе — последний -->
    <div v-if="focus" class="flex flex-wrap items-baseline gap-x-4 gap-y-1">
      <span class="text-[13.5px] font-medium">{{ focus.title }}</span>
      <span class="text-[12.5px] text-[--color-muted]">
        траты <span class="tabular text-[--color-ink]">{{ eur(focus.spent) }}</span>
      </span>
      <span v-if="focus.income > 0" class="text-[12.5px] text-[--color-muted]">
        доходы <span class="tabular text-[--color-good]">{{ eur(focus.income) }}</span>
      </span>
      <span class="text-[12.5px] text-[--color-muted]">
        накоплено <span class="tabular text-[--color-accent]">{{ eur(focus.cumulative) }}</span>
      </span>
      <span v-if="focus.count" class="text-[12.5px] text-[--color-muted]">{{ focus.count }} зап.</span>
    </div>

    <svg
      :viewBox="`0 0 ${W} ${H}`"
      class="mt-3 w-full"
      role="img"
      aria-label="Траты по месяцам и накопленная сумма"
      @mouseleave="hover = null"
    >
      <!-- сетка: три линии по шкале столбиков и базовая линия накопления -->
      <g stroke="var(--color-line)" :stroke-width="units(1)">
        <line
          v-for="share in [0, 0.5, 1]"
          :key="'grid' + share"
          :x1="PAD_L" :x2="W - PAD_R"
          :y1="BAR_BOTTOM - share * BAR_H" :y2="BAR_BOTTOM - share * BAR_H"
        />
        <line :x1="PAD_L" :x2="W - PAD_R" :y1="AREA_BOTTOM" :y2="AREA_BOTTOM" />
      </g>

      <!-- накопление -->
      <path :d="areaPath" fill="var(--color-accent)" opacity="0.08" />
      <path
        :d="linePath"
        fill="none" stroke="var(--color-accent)" :stroke-width="units(2)"
        stroke-linecap="round" stroke-linejoin="round"
      />
      <circle
        v-for="(month, index) in series"
        :key="'dot' + month.month"
        :cx="center(index)" :cy="cumY(month.cumulative)"
        :r="hover === index ? units(3.4) : units(1.8)"
        fill="#fff" stroke="var(--color-accent)" :stroke-width="units(1.6)"
      />

      <!-- траты за месяц -->
      <rect
        v-for="(month, index) in series"
        :key="'bar' + month.month"
        :x="center(index) - barW / 2" :y="BAR_BOTTOM - barHeight(month.spent)"
        :width="barW" :height="barHeight(month.spent)"
        :rx="units(2)" fill="var(--color-accent)"
        :opacity="hover === null || hover === index ? 0.85 : 0.3"
      />

      <text
        v-for="(month, index) in series"
        v-show="showLabel(index)"
        :key="'label' + month.month"
        :x="center(index)" :y="AXIS_Y"
        text-anchor="middle" :font-size="units(11)"
        :fill="hover === index ? 'var(--color-ink)' : 'var(--color-muted)'"
      >{{ month.label }}</text>

      <!-- зоны наведения: прозрачные, поверх графика, чтобы курсор попадал в столбец -->
      <rect
        v-for="(month, index) in series"
        :key="'hover' + month.month"
        :x="PAD_L + slot * index" :y="BAR_TOP"
        :width="slot" :height="AXIS_Y - BAR_TOP"
        fill="transparent"
        @mouseenter="hover = index"
        @click="hover = index"
      />
    </svg>

    <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-[--color-muted]">
      <span class="inline-flex items-center gap-1.5">
        <span class="h-2 w-2 rounded-sm bg-[--color-accent]"></span>траты за месяц
      </span>
      <span class="inline-flex items-center gap-1.5">
        <span class="h-0.5 w-4 rounded-full bg-[--color-accent]"></span>накопленные траты
      </span>
      <span class="tabular ml-auto">макс. месяц {{ eur(maxBar) }} · макс. накопление {{ eur(maxCum) }}</span>
    </div>
  </div>
</template>
