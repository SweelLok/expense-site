<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, eur } from '../api'
import { notifyError, shortDate, state } from '../store'
import AnimatedNumber from '../components/AnimatedNumber.vue'
import Bar from '../components/Bar.vue'
import MonthChart from '../components/MonthChart.vue'

const periods = [
  { value: 'current_month', label: 'Этот месяц' },
  { value: 'week', label: '7 дней' },
  { value: 'month', label: '30 дней' },
  { value: 'year', label: 'Год' },
  { value: 'all', label: 'Всё время' },
]

// Окно графика по месяцам живёт отдельно от «периода» выше: динамика за год
// и текущий период — разные вопросы, и переключение одного не должно сбрасывать другое.
const windows = [
  { value: 6, label: '6 мес' },
  { value: 12, label: '12 мес' },
  { value: 24, label: '24 мес' },
]

const period = ref('current_month')
const data = ref(null)
const loading = ref(false)
const monthsWindow = ref(12)
const monthly = ref(null)

const load = async () => {
  loading.value = true
  try {
    data.value = await api.stats(period.value)
  } catch (error) {
    notifyError(error)
  } finally {
    loading.value = false
  }
}

const loadMonthly = async () => {
  try {
    monthly.value = await api.monthly(monthsWindow.value)
  } catch (error) {
    notifyError(error)
  }
}

onMounted(() => {
  load()
  loadMonthly()
})
watch(period, load)
watch(monthsWindow, loadMonthly)

const maxDay = computed(() => Math.max(1, ...(data.value?.daily || []).map((row) => row.spent)))
const days = computed(() => data.value?.daily || [])
const maxCategory = computed(() => Math.max(1, ...(data.value?.by_category || []).map((row) => row.spent)))
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap gap-1.5">
      <button
        v-for="item in periods"
        :key="item.value"
        class="rounded-full border px-3.5 py-1.5 text-[12.5px] transition-all duration-200"
        :class="period === item.value
          ? 'border-[--color-ink] bg-[--color-ink] text-white'
          : 'border-[--color-line] bg-white text-[--color-muted] hover:border-[#d8d8dd] hover:text-[--color-ink]'"
        @click="period = item.value"
      >
        {{ item.label }}
      </button>
    </div>

    <div v-if="data" class="space-y-5">
      <section class="card animate-fade-up p-5">
        <p class="text-[12px] uppercase tracking-wide text-[--color-muted]">Потрачено</p>
        <p class="mt-1 text-[32px] font-medium leading-none">
          <AnimatedNumber :value="data.total" /><span class="ml-1 text-[19px] text-[--color-muted]">€</span>
        </p>
        <p class="mt-2 text-[12.5px] text-[--color-muted]">
          {{ shortDate(data.start) }} — {{ shortDate(data.end) }}
        </p>
        <div class="mt-4 grid grid-cols-3 gap-3 text-center">
          <div class="rounded-xl bg-[#fafafa] px-2 py-2.5">
            <p class="text-[11px] text-[--color-muted]">Записей</p>
            <p class="tabular mt-0.5 text-[15px] font-medium">{{ data.count }}</p>
          </div>
          <div class="rounded-xl bg-[#fafafa] px-2 py-2.5">
            <p class="text-[11px] text-[--color-muted]">В среднем в день</p>
            <p class="tabular mt-0.5 text-[15px] font-medium">{{ eur(data.avg_per_day) }}</p>
          </div>
          <div class="rounded-xl bg-[#fafafa] px-2 py-2.5">
            <p class="text-[11px] text-[--color-muted]">Доходы</p>
            <p class="tabular mt-0.5 text-[15px] font-medium text-[--color-good]">{{ eur(data.income_total) }}</p>
          </div>
        </div>
      </section>

      <section v-if="monthly" class="card animate-fade-up p-5" style="animation-delay: 40ms">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-[15px] font-medium">По месяцам</h2>
          <div class="flex gap-1">
            <button
              v-for="item in windows"
              :key="item.value"
              class="rounded-full border px-2.5 py-1 text-[11.5px] transition-all duration-200"
              :class="monthsWindow === item.value
                ? 'border-[--color-ink] bg-[--color-ink] text-white'
                : 'border-[--color-line] bg-white text-[--color-muted] hover:border-[#d8d8dd] hover:text-[--color-ink]'"
              @click="monthsWindow = item.value"
            >{{ item.label }}</button>
          </div>
        </div>

        <p class="mt-1 text-[12.5px] text-[--color-muted]">
          всего {{ eur(monthly.spent_total) }} · в среднем {{ eur(monthly.avg_per_month) }} в месяц
          <template v-if="monthly.income_total"> · доходы {{ eur(monthly.income_total) }}</template>
        </p>

        <div class="mt-4">
          <MonthChart :series="monthly.series" />
        </div>
      </section>

      <section class="card animate-fade-up p-5" style="animation-delay: 60ms">
        <h2 class="text-[15px] font-medium">По категориям</h2>
        <div v-if="data.by_category.length" class="mt-4 space-y-3.5">
          <div v-for="row in data.by_category" :key="row.category_name">
            <div class="flex items-baseline justify-between gap-3 text-[13px]">
              <span>{{ row.category_name }}</span>
              <span class="tabular text-[--color-muted]">{{ eur(row.spent) }} · {{ row.share }}%</span>
            </div>
            <div class="mt-1.5">
              <Bar :value="row.spent" :max="maxCategory" tone="accent" height="5px" />
            </div>
          </div>
        </div>
        <p v-else class="mt-3 text-[13px] text-[--color-muted]">За этот период трат нет</p>
      </section>

      <section v-if="days.length" class="card animate-fade-up p-5" style="animation-delay: 110ms">
        <h2 class="text-[15px] font-medium">По дням</h2>
        <div class="mt-4 flex h-32 items-end gap-1">
          <div
            v-for="(row, index) in days"
            :key="row.day"
            class="group relative flex-1 rounded-t-[4px] bg-[--color-accent]/15 transition-all duration-500 hover:bg-[--color-accent]/35"
            :style="{ height: Math.max(4, (row.spent / maxDay) * 100) + '%', transitionDelay: index * 12 + 'ms' }"
            :title="`${row.day}: ${eur(row.spent)}`"
          />
        </div>
        <div class="mt-2 flex justify-between text-[11.5px] text-[--color-muted]">
          <span>{{ shortDate(days[0]?.day) }}</span>
          <span>{{ shortDate(days[days.length - 1]?.day) }}</span>
        </div>
      </section>

      <section class="space-y-2">
        <h2 class="px-1 text-[13px] text-[--color-muted]">Все записи за период</h2>
        <div class="card divide-y divide-[--color-line] overflow-hidden">
          <div v-for="expense in data.expenses" :key="expense.id" class="flex items-center gap-3 px-4 py-2.5">
            <div class="min-w-0 flex-1">
              <p class="truncate text-[13.5px]">
                <span class="font-medium">{{ expense.category_name }}</span>
                <span v-if="expense.description" class="text-[--color-muted]"> · {{ expense.description }}</span>
              </p>
              <p class="text-[11.5px] text-[--color-muted]">{{ shortDate(expense.expense_date) }}</p>
            </div>
            <span class="tabular text-[13.5px] font-medium">{{ eur(expense.amount) }}</span>
          </div>
          <p v-if="!data.expenses.length" class="px-4 py-6 text-center text-[13px] text-[--color-muted]">Пусто</p>
        </div>
      </section>
    </div>

    <div v-else class="card animate-fade-in p-8 text-center text-[13px] text-[--color-muted]">
      {{ loading ? 'Считаю…' : 'Нет данных' }}
    </div>
  </div>
</template>
