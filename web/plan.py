"""Монетарная часть веб-версии: план месяца и курсы валют.

Здесь намеренно нет своей арифметики бюджета — она берётся из budget.build_plan,
того же модуля, что использует телеграм-бот. Если появится второе место с
формулой плана, отчёты разойдутся, и починить это будет дороже, чем переиспользовать.
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from budget import build_plan, month_bounds
from db import Database, SET_PLANNED_INCOME, SET_PLAN_BUDGET, SET_PLAN_MODE, SET_WARN_THRESHOLD

log = logging.getLogger("web.plan")

PLAN_MODE_AVAILABLE = "available"
PLAN_MODE_INCOME = "income"
PLAN_MODE_BUDGET = "budget"

PLAN_MODE_LABELS = {
    PLAN_MODE_AVAILABLE: "деньги в наличии",
    PLAN_MODE_INCOME: "доход этого месяца",
    PLAN_MODE_BUDGET: "бюджет месяца",
}

DEFAULT_WARN_THRESHOLD = 7.0
DEFAULT_PLAN_BUDGET = 350.0

_rates: dict[str, float] = {}
_rates_at: datetime | None = None


async def exchange_rates() -> dict[str, float]:
    """Курсы USD/UAH к EUR, кэш на час (тот же источник, что у бота)."""
    global _rates, _rates_at
    if _rates_at and (datetime.now() - _rates_at).total_seconds() < 3600:
        return _rates
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://open.er-api.com/v6/latest/EUR")
            data = resp.json()
            _rates = {k: v for k, v in (data.get("rates") or {}).items() if k in ("USD", "UAH")}
            _rates_at = datetime.now()
    except Exception as exc:  # сеть недоступна — считаем по последнему известному курсу
        log.error("failed to fetch exchange rates: %s", exc)
    return _rates


async def to_eur(amount: float, currency: str) -> float:
    if currency.upper() == "EUR":
        return amount
    rate = (await exchange_rates()).get(currency.upper())
    return amount / rate if rate else amount


async def load_plan(db: Database, user_id: int) -> dict:
    """Месячный план пользователя — порт bot.load_plan на те же настройки и таблицы."""
    month_start, today_str, _ = month_bounds()
    income_this_month = await db.get_income_total(user_id, month_start, today_str)
    planned_income = await db.get_setting_float(user_id, SET_PLANNED_INCOME, 0.0)
    plan_budget = await db.get_setting_float(user_id, SET_PLAN_BUDGET, DEFAULT_PLAN_BUDGET)
    balance = await db.get_balance(user_id)
    mode = await db.get_setting(user_id, SET_PLAN_MODE, PLAN_MODE_AVAILABLE) or PLAN_MODE_AVAILABLE
    if mode not in PLAN_MODE_LABELS:
        mode = PLAN_MODE_AVAILABLE

    categories = await db.get_categories(user_id)
    subs = await db.get_subscriptions(user_id)
    spending = await db.get_spending_by_category(user_id, month_start, today_str)
    spent_by_cat = {row["category_name"]: float(row["spent"]) for row in spending}
    spent_this_month = sum(spent_by_cat.values())

    if mode == PLAN_MODE_BUDGET:
        base, base_source = plan_budget, "бюджет месяца"
    elif mode == PLAN_MODE_INCOME:
        if income_this_month > 0:
            base, base_source = income_this_month, "доход этого месяца"
        elif planned_income > 0:
            base, base_source = planned_income, "плановый доход"
        else:
            base, base_source = balance, "текущий баланс"
    else:
        base, base_source = balance + spent_this_month, "деньги в наличии"

    warn_threshold = await db.get_setting_float(user_id, SET_WARN_THRESHOLD, DEFAULT_WARN_THRESHOLD)
    plan = build_plan(base, categories, subs, spent_by_cat, warn_threshold)
    today_rows = await db.get_daily_spending(user_id, today_str, today_str)
    plan["today_spent"] = float(today_rows[0]["spent"]) if today_rows else 0.0
    plan["today_date"] = today_str
    plan["base_source"] = base_source
    plan["mode"] = mode
    plan["mode_label"] = PLAN_MODE_LABELS[mode]
    plan["income_this_month"] = income_this_month
    plan["planned_income"] = planned_income
    plan["plan_budget"] = plan_budget
    plan["balance"] = balance
    plan["spent_this_month"] = spent_this_month
    plan["month_start"] = month_start
    plan["categories"] = categories
    plan["subscriptions"] = subs
    return plan
