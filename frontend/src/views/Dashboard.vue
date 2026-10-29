<script setup>
import { computed, ref, onMounted } from 'vue'
import { api, eur } from '../api'
import { applyMutation, loadOverview, notifyError, state, toast, todayISO, shortDate, monthName } from '../store'
import AnimatedNumber from '../components/AnimatedNumber.vue'
import Bar from '../components/Bar.vue'
import Modal from '../components/Modal.vue'

const amount = ref('')
const currency = ref('EUR')
const categoryId = ref(null)
const date = ref(todayISO())
const description = ref('')
const saving = ref(false)
const rates = ref({})

const editing = ref(null)
const editForm = ref({ amount: '', category_id: null, date: '', description: '' })
const incomeOpen = ref(false)
const incomeForm = ref({ amount: '', currency: 'EUR', description: '', date: todayISO() })

// История трат свёрнута по умолчанию: список длинный и мешает добраться до плана.
// Выбор запоминаем, чтобы не разворачивать её заново на каждом заходе.
const HISTORY_KEY = 'expense.history.open'
const readHistoryState = () => {
  try {
    return localStorage.getItem(HISTORY_KEY) === '1'
  } catch {
    return false
  }
}
const historyOpen = ref(readHistoryState())
const toggleHistory = () => {
  historyOpen.value = !historyOpen.value
  try {
    localStorage.setItem(HISTORY_KEY, historyOpen.value ? '1' : '0')
  } catch {
    /* приватный режим — просто не запоминаем */
  }
}

const plan = computed(() => state.overview?.plan || null)
const items = computed(() => (plan.value?.items || []).filter((it) => it.plan > 0 || it.spent > 0))
const categories = computed(() => state.overview?.categories || [])
const expenses = computed(() => state.overview?.recent_expenses || [])
const incomes = computed(() => state.overview?.recent_incomes || [])
const monthProgress = computed(() => {
  if (!plan.value) return 0
  const day = new Date().getDate()
  const days = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate()
  return Math.round((day / days) * 100)
})

onMounted(async () => {
  if (!state.overview) await loadOverview().catch(notifyError)
  categoryId.value = categories.value[0]?.id ?? null
  api.settings().then((data) => { rates.value = data.rate_limits || {} }).catch(() => {})
})

async function addExpense() {
  const value = Number(String(amount.value).replace(',', '.'))
  if (!value || value <= 0) return toast('Введи сумму', 'warn')
  if (!categoryId.value) return toast('Выбери категорию', 'warn')
  saving.value = true
  try {
    const result = await api.addExpense({
      amount: value,
      currency: currency.value,
      category_id: categoryId.value,
      description: description.value.trim() || null,
      date: date.value,
    })
    const name = categories.value.find((c) => c.id === categoryId.value)?.name
    await applyMutation(result)
    toast(`Записано: ${eur(result.converted_eur)} — ${name}`, 'good')
    amount.value = ''
    description.value = ''
    await loadOverview()
  } catch (error) {
    notifyError(error)
  } finally {
    saving.value = false
  }
}

function startEdit(expense) {
  editing.value = expense
  editForm.value = {
    amount: String(expense.amount),
    category_id: expense.category_id,
    date: expense.expense_date,
    description: expense.description || '',
  }
}

async function saveEdit() {
  const value = Number(String(editForm.value.amount).replace(',', '.'))
  try {
    const result = await api.patchExpense(editing.value.id, {
      amount: value,
      category_id: Number(editForm.value.category_id),
      date: editForm.value.date,
      description: editForm.value.description.trim() || null,
    })
    await applyMutation(result)
    toast('Трата обновлена', 'good')
    editing.value = null
    await loadOverview()
  } catch (error) {
    notifyError(error)
  }
}

async function removeExpense(expense) {
  if (!confirm(`Удалить «${expense.category_name}» на ${eur(expense.amount)}?`)) return
  try {
    const result = await api.deleteExpense(expense.id)
    await applyMutation(result)
    toast('Трата удалена, деньги вернулись в баланс', 'good')
    await loadOverview()
  } catch (error) {
    notifyError(error)
  }
}

async function addIncome() {
  const value = Number(String(incomeForm.value.amount).replace(',', '.'))
  if (!value || value <= 0) return toast('Введи сумму дохода', 'warn')
  try {
    const result = await api.addIncome({
      amount: value,
      currency: incomeForm.value.currency,
      description: incomeForm.value.description.trim() || null,
      date: incomeForm.value.date,
    })
    await applyMutation(result)
    toast(`Доход ${eur(result.converted_eur)} добавлен`, 'good')
    incomeOpen.value = false
    incomeForm.value = { amount: '', currency: 'EUR', description: '', date: todayISO() }
    await loadOverview()
  } catch (error) {
    notifyError(error)
  }
}

async function removeIncome(income) {
  if (!confirm(`Удалить доход ${eur(income.amount)}?`)) return
  try {
    const result = await api.deleteIncome(income.id)
    await applyMutation(result)
    toast('Доход удалён', 'good')
    await loadOverview()
  } catch (error) {
    notifyError(error)
  }
}

const toneOf = (item) => (item.left < 0 ? 'bad' : item.left <= (plan.value?.warn_threshold || 7) ? 'warn' : 'auto')
</script>

<template>
  <div v-if="plan" class="space-y-5">
    <!-- Сводка месяца -->
    <section class="card animate-fade-up p-5">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="text-[12px] uppercase tracking-wide text-[--color-muted]">Баланс</p>
          <p class="mt-1 text-[34px] font-medium leading-none">
            <AnimatedNumber :value="plan.balance" />
            <span class="ml-1 text-[20px] text-[--color-muted]">€</span>
          </p>
          <p class="mt-2 text-[12.5px] text-[--color-muted]">
            {{ monthName(plan.month_start) }} · план от «{{ plan.base_source }}» — {{ eur(plan.base) }}
          </p>
        </div>
        <button class="btn btn-ghost shrink-0 text-[13px]" @click="incomeOpen = true">+ доход</button>
      </div>

      <div class="mt-5 grid grid-cols-3 gap-3 text-center">
        <div class="rounded-xl bg-[#fafafa] px-3 py-2.5">
          <p class="text-[11px] text-[--color-muted]">Сегодня</p>
          <p class="tabular mt-0.5 text-[15px] font-medium">{{ eur(plan.today_spent) }}</p>
        </div>
        <div class="rounded-xl bg-[#fafafa] px-3 py-2.5">
          <p class="text-[11px] text-[--color-muted]">С 1-го числа</p>
          <p class="tabular mt-0.5 text-[15px] font-medium">{{ eur(plan.spent_this_month) }}</p>
        </div>
        <div class="rounded-xl bg-[#fafafa] px-3 py-2.5">
          <p class="text-[11px] text-[--color-muted]">За 7 дней</p>
          <p class="tabular mt-0.5 text-[15px] font-medium">{{ eur(state.overview.week_spent) }}</p>
        </div>
      </div>

      <div class="mt-4">
        <Bar :value="monthProgress" :max="100" tone="accent" height="4px" />
        <div class="mt-2 flex justify-between text-[11.5px] text-[--color-muted]">
          <span>распределено {{ eur(plan.planned_total) }}</span>
          <span>до конца месяца {{ plan.days_left }} дн.</span>
        </div>
      </div>

      <p
        v-if="plan.unallocated < 0"
        class="mt-3 rounded-xl bg-[#fef2f2] px-3 py-2 text-[12.5px] text-[--color-bad]"
      >
        План не сходится: не хватает {{ eur(Math.abs(plan.unallocated)) }}
      </p>
      <p v-else class="mt-3 text-[12.5px] text-[--color-muted]">
        Не распределено: {{ eur(plan.unallocated) }}
      </p>
    </section>

    <!-- Быстрый ввод траты -->
    <section class="card animate-fade-up p-5" style="animation-delay: 60ms">
      <div class="flex items-baseline justify-between">
        <h2 class="text-[15px] font-medium">Новая трата</h2>
        <span v-if="currency !== 'EUR' && rates[currency]" class="text-[11.5px] text-[--color-muted]">
          1 € = {{ (1 / rates[currency]).toFixed(2) }} {{ currency }}
        </span>
      </div>

      <form class="mt-3 space-y-3" @submit.prevent="addExpense">
        <div class="flex gap-2">
          <input
            v-model="amount"
            type="text"
            inputmode="decimal"
            placeholder="0.00"
            class="field tabular min-w-0 flex-1 !py-3 text-[22px] font-medium"
            autocomplete="off"
          />
          <select v-model="currency" class="field w-24 shrink-0 tabular">
            <option value="EUR">EUR</option>
            <option value="USD">USD</option>
            <option value="UAH">UAH</option>
          </select>
        </div>

        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="category in categories"
            :key="category.id"
            type="button"
            class="rounded-full border px-3 py-1.5 text-[12.5px] transition-all duration-200"
            :class="categoryId === category.id
              ? 'border-[--color-ink] bg-[--color-ink] text-white'
              : 'border-[--color-line] bg-white text-[--color-muted] hover:border-[#d8d8dd] hover:text-[--color-ink]'"
            @click="categoryId = category.id"
          >
            {{ category.name }}
          </button>
        </div>

        <div class="grid gap-2 sm:grid-cols-2">
          <input v-model="date" type="date" class="field tabular" />
          <input v-model="description" type="text" placeholder="Описание (необязательно)" class="field" />
        </div>

        <button class="btn btn-primary w-full" :disabled="saving">
          {{ saving ? 'Записываю…' : 'Добавить трату' }}
        </button>
      </form>
    </section>

    <!-- План по категориям -->
    <section class="space-y-2">
      <h2 class="px-1 text-[13px] text-[--color-muted]">План по категориям</h2>
      <div class="stagger grid gap-2 sm:grid-cols-2">
        <div v-for="(item, index) in items" :key="item.name" class="card card-hover p-4" :style="{ animationDelay: index * 35 + 'ms' }">
          <div class="flex items-baseline justify-between gap-3">
            <span class="text-[14px] font-medium">{{ item.name }}</span>
            <span class="tabular text-[13px] text-[--color-muted]">{{ eur(item.spent) }} / {{ eur(item.plan) }}</span>
          </div>
          <div class="mt-2.5">
            <Bar :value="item.spent" :max="item.plan || item.spent || 1" :tone="toneOf(item)" />
          </div>
          <div class="mt-2 flex justify-between text-[11.5px]" :class="item.left < 0 ? 'text-[--color-bad]' : 'text-[--color-muted]'">
            <span v-if="item.plan > 0">остаток {{ eur(item.left) }}</span>
            <span v-else>план не задан — траты сверх плана</span>
            <span v-if="item.plan > 0" class="tabular">{{ item.per_day.toFixed(2) }} €/день</span>
          </div>
        </div>
      </div>
    </section>

    <!-- История трат: свёрнута по умолчанию, чтобы длинный список не отодвигал план -->
    <section class="space-y-2">
      <button
        type="button"
        class="flex w-full items-center gap-1.5 rounded-lg px-1 py-1 text-[13px] text-[--color-muted] transition-colors hover:text-[--color-ink]"
        :aria-expanded="historyOpen"
        aria-controls="history-list"
        @click="toggleHistory"
      >
        <svg
          viewBox="0 0 24 24"
          class="h-3.5 w-3.5 shrink-0 transition-transform duration-200"
          :class="historyOpen ? 'rotate-90' : ''"
          fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
        >
          <path d="M9 6l6 6-6 6" />
        </svg>
        <span>История трат</span>
        <span v-if="expenses.length">· {{ expenses.length }}
          {{ expenses.length % 10 === 1 && expenses.length % 100 !== 11 ? 'последняя' : 'последних' }}</span>
      </button>

      <div v-show="historyOpen" id="history-list" class="card divide-y divide-[--color-line] overflow-hidden">
        <TransitionGroup name="list" tag="div" class="relative">
          <div v-for="expense in expenses" :key="expense.id" class="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-[#fafafa]">
            <div class="min-w-0 flex-1">
              <p class="truncate text-[14px]">
                <span class="font-medium">{{ expense.category_name }}</span>
                <span v-if="expense.description" class="text-[--color-muted]"> · {{ expense.description }}</span>
              </p>
              <p class="text-[11.5px] text-[--color-muted]">
                {{ shortDate(expense.expense_date) }}
                <span v-if="expense.currency !== 'EUR'"> · {{ expense.currency }}</span>
              </p>
            </div>
            <span class="tabular text-[14px] font-medium">−{{ eur(expense.amount) }}</span>
            <button class="text-[12px] text-[--color-muted] transition-colors hover:text-[--color-ink]" @click="startEdit(expense)">изм.</button>
            <button class="text-[12px] text-[--color-muted] transition-colors hover:text-[--color-bad]" @click="removeExpense(expense)">удал.</button>
          </div>
        </TransitionGroup>
        <p v-if="!expenses.length" class="px-4 py-6 text-center text-[13px] text-[--color-muted]">Пока ничего не записано</p>
      </div>
    </section>

    <!-- Доходы -->
    <section v-if="incomes.length" class="space-y-2">
      <h2 class="px-1 text-[13px] text-[--color-muted]">Доходы</h2>
      <div class="card divide-y divide-[--color-line] overflow-hidden">
        <div v-for="income in incomes" :key="income.id" class="flex items-center gap-3 px-4 py-3">
          <div class="min-w-0 flex-1">
            <p class="truncate text-[14px]">{{ income.description || 'Доход' }}</p>
            <p class="text-[11.5px] text-[--color-muted]">{{ shortDate(income.income_date) }}</p>
          </div>
          <span class="tabular text-[14px] font-medium text-[--color-good]">+{{ eur(income.amount) }}</span>
          <button class="text-[12px] text-[--color-muted] transition-colors hover:text-[--color-bad]" @click="removeIncome(income)">удал.</button>
        </div>
      </div>
    </section>

    <Modal v-if="editing" title="Изменить трату" @close="editing = null">
      <form class="space-y-3" @submit.prevent="saveEdit">
        <input v-model="editForm.amount" inputmode="decimal" class="field tabular" />
        <select v-model="editForm.category_id" class="field">
          <option v-for="category in categories" :key="category.id" :value="category.id">{{ category.name }}</option>
        </select>
        <input v-model="editForm.date" type="date" class="field tabular" />
        <input v-model="editForm.description" placeholder="Описание" class="field" />
        <div class="flex gap-2 pt-1">
          <button type="button" class="btn btn-ghost flex-1" @click="editing = null">Отмена</button>
          <button class="btn btn-primary flex-1">Сохранить</button>
        </div>
      </form>
    </Modal>

    <Modal v-if="incomeOpen" title="Новый доход" @close="incomeOpen = false">
      <form class="space-y-3" @submit.prevent="addIncome">
        <div class="flex gap-2">
          <input v-model="incomeForm.amount" inputmode="decimal" placeholder="0.00" class="field tabular !py-3 text-[20px]" />
          <select v-model="incomeForm.currency" class="field w-24">
            <option value="EUR">EUR</option>
            <option value="USD">USD</option>
            <option value="UAH">UAH</option>
          </select>
        </div>
        <input v-model="incomeForm.description" placeholder="Описание" class="field" />
        <input v-model="incomeForm.date" type="date" class="field tabular" />
        <div class="flex gap-2 pt-1">
          <button type="button" class="btn btn-ghost flex-1" @click="incomeOpen = false">Отмена</button>
          <button class="btn btn-primary flex-1">Добавить</button>
        </div>
      </form>
    </Modal>
  </div>

  <div v-else class="card animate-fade-in p-8 text-center text-[13px] text-[--color-muted]">Загружаю данные…</div>
</template>
