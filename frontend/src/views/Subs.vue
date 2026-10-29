<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, eur } from '../api'
import { applyMutation, notifyError, state, toast } from '../store'
import AnimatedNumber from '../components/AnimatedNumber.vue'
import Modal from '../components/Modal.vue'

const data = ref(null)
const categories = ref([])
const modal = ref(false)
const editingId = ref(null)
const form = ref({ name: '', amount: '', period: 'monthly', months: null, category_id: null })

const subscriptions = computed(() => data.value?.subscriptions || [])

const load = async () => {
  try {
    data.value = await api.subscriptions()
    categories.value = (await api.categories()).categories
  } catch (error) {
    notifyError(error)
  }
}

onMounted(load)

function openNew() {
  editingId.value = null
  form.value = { name: '', amount: '', period: 'monthly', months: null, category_id: categories.value[0]?.id ?? null }
  modal.value = true
}

function openEdit(sub) {
  editingId.value = sub.id
  form.value = {
    name: sub.name,
    amount: String(sub.amount),
    period: sub.period,
    months: sub.months,
    category_id: sub.category_id,
  }
  modal.value = true
}

async function save() {
  const payload = {
    name: form.value.name.trim(),
    amount: Number(String(form.value.amount).replace(',', '.')),
    period: form.value.period,
    months: form.value.period === 'custom' ? Number(form.value.months) || 1 : null,
    category_id: form.value.category_id ? Number(form.value.category_id) : null,
  }
  if (!payload.name || !payload.amount) return toast('Нужно название и сумма', 'warn')
  try {
    const result = editingId.value
      ? await api.patchSubscription(editingId.value, payload)
      : await api.addSubscription(payload)
    await applyMutation(result)
    toast(editingId.value ? 'Платёж обновлён' : 'Платёж добавлен', 'good')
    modal.value = false
    await load()
  } catch (error) {
    notifyError(error)
  }
}

async function remove(sub) {
  if (!confirm(`Удалить «${sub.name}»?`)) return
  try {
    const result = await api.deleteSubscription(sub.id)
    await applyMutation(result)
    toast('Платёж удалён', 'good')
    await load()
  } catch (error) {
    notifyError(error)
  }
}
</script>

<template>
  <div class="space-y-5">
    <section class="card animate-fade-up p-5">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="text-[12px] uppercase tracking-wide text-[--color-muted]">В месяц по подпискам</p>
          <p class="mt-1 text-[32px] font-medium leading-none">
            <AnimatedNumber :value="data?.monthly_total || 0" /><span class="ml-1 text-[19px] text-[--color-muted]">€</span>
          </p>
          <p class="mt-2 text-[12.5px] text-[--color-muted]">
            {{ subscriptions.length }} платежей · вычитаются из денег месяца в плане
          </p>
        </div>
        <button class="btn btn-ghost shrink-0 text-[13px]" @click="openNew">+ платёж</button>
      </div>
    </section>

    <div class="stagger space-y-2">
      <div v-for="(sub, index) in subscriptions" :key="sub.id" class="card card-hover flex items-center gap-3 p-4" :style="{ animationDelay: index * 35 + 'ms' }">
        <div class="min-w-0 flex-1">
          <p class="truncate text-[14px] font-medium">{{ sub.name }}</p>
          <p class="mt-0.5 text-[11.5px] text-[--color-muted]">
            {{ eur(sub.amount) }} · {{ sub.period_label }}
            <span v-if="sub.category_name"> · {{ sub.category_name }}</span>
          </p>
        </div>
        <div class="text-right">
          <p class="tabular text-[14px] font-medium">{{ eur(sub.monthly_amount) }}</p>
          <p class="text-[11px] text-[--color-muted]">в месяц</p>
        </div>
        <div class="flex flex-col gap-1 text-[12px]">
          <button class="text-[--color-muted] transition-colors hover:text-[--color-ink]" @click="openEdit(sub)">изм.</button>
          <button class="text-[--color-muted] transition-colors hover:text-[--color-bad]" @click="remove(sub)">удал.</button>
        </div>
      </div>
      <p v-if="data && !subscriptions.length" class="card p-6 text-center text-[13px] text-[--color-muted]">
        Подписок пока нет
      </p>
    </div>

    <Modal v-if="modal" :title="editingId ? 'Изменить платёж' : 'Новый платёж'" @close="modal = false">
      <form class="space-y-3" @submit.prevent="save">
        <input v-model="form.name" placeholder="Название (Зал, Vodafone…)" class="field" />
        <input v-model="form.amount" inputmode="decimal" placeholder="Сумма, €" class="field tabular" />
        <select v-model="form.period" class="field">
          <option value="monthly">каждый месяц</option>
          <option value="2months">каждые 2 месяца</option>
          <option value="quarterly">раз в квартал</option>
          <option value="halfyear">раз в полгода</option>
          <option value="yearly">раз в год</option>
          <option value="custom">свой период</option>
        </select>
        <input
          v-if="form.period === 'custom'"
          v-model="form.months"
          inputmode="decimal"
          placeholder="Период в месяцах (например 1.5 — раз в 6 недель)"
          class="field tabular animate-fade-up"
        />
        <select v-model="form.category_id" class="field">
          <option :value="null">без категории</option>
          <option v-for="category in categories" :key="category.id" :value="category.id">{{ category.name }}</option>
        </select>
        <div class="flex gap-2 pt-1">
          <button type="button" class="btn btn-ghost flex-1" @click="modal = false">Отмена</button>
          <button class="btn btn-primary flex-1">Сохранить</button>
        </div>
      </form>
    </Modal>
  </div>
</template>
