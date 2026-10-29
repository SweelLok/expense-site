<script setup>
import { onMounted, ref } from 'vue'
import { api, download, eur } from '../api'
import { loadOverview, loadSettings, notifyError, state, toast } from '../store'
import Modal from '../components/Modal.vue'

const rows = ref([])
const newCategory = ref({ name: '', monthly_limit: '' })
const settings = ref(null)
const password = ref({ current: '', next: '', repeat: '' })
const resetOpen = ref(false)
const resetConfirm = ref('')
const saving = ref(false)

const load = async () => {
  try {
    const [categories, config] = await Promise.all([api.categories(), api.settings()])
    rows.value = categories.categories.map((category) => ({
      id: category.id,
      name: category.name,
      monthly_limit: category.monthly_limit === null || category.monthly_limit === undefined ? '' : String(category.monthly_limit),
      weekly_limit: category.weekly_limit,
      spent_this_month: category.spent_this_month,
    }))
    settings.value = config
  } catch (error) {
    notifyError(error)
  }
}

onMounted(load)

async function saveCategory(row) {
  const limit = row.monthly_limit === '' ? null : Number(String(row.monthly_limit).replace(',', '.'))
  try {
    const result = await api.patchCategory(row.id, { name: row.name, monthly_limit: limit })
    await refreshPlan(result)
    toast(`«${row.name}» сохранена${limit === null ? ' — план авто' : ''}`, 'good')
    await load()
  } catch (error) {
    notifyError(error)
  }
}

async function addCategory() {
  const limit = newCategory.value.monthly_limit === '' ? null : Number(newCategory.value.monthly_limit)
  try {
    await api.addCategory({ name: newCategory.value.name, monthly_limit: limit })
    newCategory.value = { name: '', monthly_limit: '' }
    toast('Категория добавлена', 'good')
    await load()
    await loadOverview()
  } catch (error) {
    notifyError(error)
  }
}

async function removeCategory(row) {
  if (!confirm(`Удалить категорию «${row.name}»?`)) return
  try {
    const result = await api.deleteCategory(row.id)
    await refreshPlan(result)
    toast('Категория удалена', 'good')
    await load()
    await loadOverview()
  } catch (error) {
    notifyError(error)
  }
}

async function saveSettings() {
  saving.value = true
  try {
    settings.value = await api.saveSettings({
      plan_mode: settings.value.plan_mode,
      planned_income: Number(settings.value.planned_income),
      plan_budget: Number(settings.value.plan_budget),
      warn_threshold: Number(settings.value.warn_threshold),
      balance: Number(settings.value.balance),
    })
    await loadOverview()
    toast('Настройки сохранены', 'good')
  } catch (error) {
    notifyError(error)
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  if (password.value.next.length < 6) return toast('Пароль минимум 6 символов', 'warn')
  if (password.value.next !== password.value.repeat) return toast('Пароли не совпадают', 'warn')
  try {
    const result = await api.changePassword(password.value.current, password.value.next)
    password.value = { current: '', next: '', repeat: '' }
    toast(result.note || 'Пароль изменён', 'good', 7000)
  } catch (error) {
    notifyError(error)
  }
}

async function doReset() {
  try {
    const result = await api.reset(resetConfirm.value)
    resetOpen.value = false
    resetConfirm.value = ''
    await refreshPlan(result)
    await load()
    toast('Все данные стёрты', 'good')
  } catch (error) {
    notifyError(error)
  }
}

async function refreshPlan(result) {
  if (result?.plan) state.overview = { ...(state.overview || {}), plan: result.plan }
  await loadOverview()
}

const rates = () => settings.value?.rate_limits || {}
</script>

<template>
  <div class="space-y-5">
    <!-- Категории и планы -->
    <section class="card animate-fade-up p-5">
      <h2 class="text-[15px] font-medium">Категории и месячные планы</h2>
      <p class="mt-1 text-[12.5px] text-[--color-muted]">
        Пустое поле = «авто»: категория делит свободный остаток месяца вместе с другими авто-категориями.
      </p>

      <div class="mt-4 space-y-2">
        <div v-for="row in rows" :key="row.id" class="flex items-center gap-2 rounded-xl border border-[--color-line] p-2">
          <input v-model="row.name" class="field flex-1 !py-1.5 text-[13.5px]" />
          <input
            v-model="row.monthly_limit"
            inputmode="decimal"
            placeholder="авто"
            class="field tabular w-20 shrink-0 !py-1.5 text-[13.5px]"
          />
          <span class="tabular hidden w-16 shrink-0 text-right text-[12px] text-[--color-muted] sm:inline">
            {{ eur(row.spent_this_month) }}
          </span>
          <button class="shrink-0 text-[12px] text-[--color-muted] transition-colors hover:text-[--color-ink]" @click="saveCategory(row)">
            ок
          </button>
          <button class="shrink-0 text-[12px] text-[--color-muted] transition-colors hover:text-[--color-bad]" @click="removeCategory(row)">
            ✕
          </button>
        </div>
      </div>

      <div class="mt-3 flex items-center gap-2 rounded-xl border border-dashed border-[--color-line] p-2">
        <input v-model="newCategory.name" placeholder="новая категория" class="field flex-1 !py-1.5 text-[13.5px]" @keyup.enter="addCategory" />
        <input v-model="newCategory.monthly_limit" inputmode="decimal" placeholder="авто" class="field tabular w-20 shrink-0 !py-1.5 text-[13.5px]" />
        <button class="btn btn-ghost shrink-0 !py-1.5 text-[12.5px]" @click="addCategory">добавить</button>
      </div>
    </section>

    <!-- Настройки плана -->
    <section v-if="settings" class="card animate-fade-up p-5" style="animation-delay: 60ms">
      <h2 class="text-[15px] font-medium">Деньги месяца</h2>
      <p class="mt-1 text-[12.5px] text-[--color-muted]">От этой базы считается план; лимиты категорий задаются выше.</p>

      <div class="mt-4 space-y-3">
        <label class="block">
          <span class="mb-1.5 block text-[12px] text-[--color-muted]">Режим базы</span>
          <select v-model="settings.plan_mode" class="field">
            <option v-for="mode in settings.modes" :key="mode.value" :value="mode.value">{{ mode.label }}</option>
          </select>
        </label>

        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block">
            <span class="mb-1.5 block text-[12px] text-[--color-muted]">Текущий баланс, €</span>
            <input v-model="settings.balance" inputmode="decimal" class="field tabular" />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[12px] text-[--color-muted]">Плановый доход месяца, €</span>
            <input v-model="settings.planned_income" inputmode="decimal" class="field tabular" />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[12px] text-[--color-muted]">Бюджет месяца, €</span>
            <input v-model="settings.plan_budget" inputmode="decimal" class="field tabular" />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[12px] text-[--color-muted]">Порог предупреждения, €</span>
            <input v-model="settings.warn_threshold" inputmode="decimal" class="field tabular" />
          </label>
        </div>

        <button class="btn btn-primary w-full" :disabled="saving" @click="saveSettings">
          {{ saving ? 'Сохраняю…' : 'Сохранить настройки' }}
        </button>
      </div>
    </section>

    <!-- Данные -->
    <section class="card animate-fade-up p-5" style="animation-delay: 110ms">
      <h2 class="text-[15px] font-medium">Данные</h2>
      <div class="mt-4 flex flex-wrap gap-2">
        <button class="btn btn-ghost text-[13px]" @click="download('/export.csv')">Экспорт CSV</button>
        <button class="btn btn-ghost text-[13px]" @click="download('/backup')">Скачать базу (.db)</button>
      </div>
      <p v-if="Object.keys(rates()).length" class="mt-3 text-[12px] text-[--color-muted]">
        Курсы на сейчас: <span v-for="(value, code) in rates()" :key="code" class="tabular ml-1.5">{{ code }} {{ value.toFixed(3) }}</span>
      </p>
    </section>

    <!-- Пароль -->
    <section class="card animate-fade-up p-5" style="animation-delay: 150ms">
      <h2 class="text-[15px] font-medium">Пароль</h2>
      <p class="mt-1 text-[12.5px] text-[--color-muted]">После смены пароля все открытые сессии закрываются.</p>
      <div class="mt-4 space-y-3">
        <input v-model="password.current" type="password" placeholder="текущий пароль" class="field" autocomplete="current-password" />
        <input v-model="password.next" type="password" placeholder="новый пароль" class="field" autocomplete="new-password" />
        <input v-model="password.repeat" type="password" placeholder="новый пароль ещё раз" class="field" autocomplete="new-password" />
        <button class="btn btn-ghost w-full text-[13px]" @click="changePassword">Сменить пароль</button>
      </div>
    </section>

    <!-- Опасная зона -->
    <section class="card animate-fade-up border-[#fecaca] p-5" style="animation-delay: 190ms">
      <h2 class="text-[15px] font-medium text-[--color-bad]">Опасная зона</h2>
      <p class="mt-1 text-[12.5px] text-[--color-muted]">
        Стирает все траты, доходы, подписки, баланс и настройки. Перед этим скачай базу.
      </p>
      <button class="btn btn-ghost mt-4 w-full border-[#fecaca] text-[13px] text-[--color-bad]" @click="resetOpen = true">
        Стереть все данные
      </button>
    </section>

    <Modal v-if="resetOpen" title="Стереть все данные" width="24rem" @close="resetOpen = false">
      <p class="text-[13px] text-[--color-muted]">Это необратимо. Напиши <span class="font-medium text-[--color-ink]">УДАЛИТЬ</span>, чтобы подтвердить.</p>
      <input v-model="resetConfirm" class="field mt-3" placeholder="УДАЛИТЬ" />
      <div class="mt-4 flex gap-2">
        <button class="btn btn-ghost flex-1" @click="resetOpen = false">Отмена</button>
        <button class="btn flex-1 bg-[--color-bad] text-white" :disabled="resetConfirm !== 'УДАЛИТЬ'" @click="doReset">Стереть</button>
      </div>
    </Modal>
  </div>
</template>
