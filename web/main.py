"""Веб-версия трекера трат: FastAPI поверх тех же таблиц и той же логики плана.

Заменяет телеграм-бота как интерфейс, ничего не меняя в данных: та же база
expenses.db на томе /data, те же таблицы (expenses/incomes/categories/
subscriptions/settings/balances), тот же user_id. Новых таблиц нет — пароль
веб-версии лежит строкой в settings, поэтому миграция аддитивная.

Арифметика плана живёт в budget.build_plan, запросы к БД — в db.Database:
и веб, и бот считают одним и тем же кодом, иначе один и тот же месяц покажет
разные итоги на двух экранах.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from budget import month_bounds, monthly_amount, months_of, period_label, warning_lines  # noqa: E402
from db import (  # noqa: E402
    Database,
    SET_PLANNED_INCOME,
    SET_PLAN_MODE,
    SET_PLAN_BUDGET,
    SET_WARN_THRESHOLD,
)
from web.plan import (  # noqa: E402
    DEFAULT_PLAN_BUDGET,
    DEFAULT_WARN_THRESHOLD,
    PLAN_MODE_LABELS,
    exchange_rates,
    load_plan,
    to_eur,
)
from web.security import (  # noqa: E402
    COOKIE_NAME,
    LoginLimiter,
    hash_password,
    make_token,
    password_fingerprint,
    read_token,
    verify_password,
)

# --- Часовой пояс --------------------------------------------------------
# Без TZ контейнер живёт в UTC и «сегодня» съезжает на день назад.
DEFAULT_TZ = "Europe/Bratislava"
if not os.environ.get("TZ"):
    os.environ["TZ"] = DEFAULT_TZ
try:
    time.tzset()
except AttributeError:  # не POSIX — оставляем системную зону
    pass

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("web")

DB_PATH = os.environ.get("DB_PATH", str(ROOT / "expenses.db"))
USER_ID = int(os.environ.get("APP_USER_ID") or 0)
AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "vadim")
SESSION_SECRET = os.environ.get("SESSION_SECRET") or "dev-insecure-secret"
ENV_PASSWORD_HASH = os.environ.get("AUTH_PASSWORD_HASH")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") != "0"
STATIC_DIR = Path(__file__).resolve().parent / "static"

PASSWORD_SETTING_KEY = "web_password_hash"
DEFAULT_CATEGORIES = [
    "еда", "бытовое", "подписки", "общежитие", "стрижка", "транспорт", "развлечения", "прочее", "резерв",
]
PERIODS = ["monthly", "2months", "quarterly", "halfyear", "yearly", "custom"]
PERIOD_LABELS = {
    "monthly": "каждый месяц",
    "2months": "каждые 2 месяца",
    "quarterly": "раз в квартал",
    "halfyear": "раз в полгода",
    "yearly": "раз в год",
    "custom": "свой период",
}

db = Database(DB_PATH)
limiter = LoginLimiter()
app = FastAPI(title="Expense tracker", docs_url=None, redoc_url=None, openapi_url=None)


# --- Служебное -----------------------------------------------------------

async def resolve_user_id() -> int:
    """APP_USER_ID из окружения; иначе — единственный user_id, который есть в базе."""
    global USER_ID
    if USER_ID:
        return USER_ID
    import aiosqlite

    async with aiosqlite.connect(DB_PATH) as conn:
        row = None
        for table in ("balances", "expenses", "categories"):
            async with conn.execute(f"SELECT user_id FROM {table} LIMIT 1") as cur:
                row = await cur.fetchone()
            if row:
                break
    if not row:
        raise RuntimeError("APP_USER_ID не задан и в базе нет ни одного пользователя")
    USER_ID = int(row[0])
    log.info("user_id определён по базе: %s", USER_ID)
    return USER_ID


@app.on_event("startup")
async def on_startup() -> None:
    await db.init()
    user_id = await resolve_user_id()
    # WAL + busy_timeout: веб-процесс пишет чаще бота, без этого ловим database is locked.
    import aiosqlite

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.commit()
    if not ENV_PASSWORD_HASH and not await db.get_setting(user_id, PASSWORD_SETTING_KEY):
        log.warning("пароль веб-версии не задан (ни AUTH_PASSWORD_HASH, ни запись в settings)")
    log.info("web готов: user_id=%s db=%s", user_id, DB_PATH)


async def current_password_hash(user_id: int) -> str | None:
    """Хеш из settings (его ставит смена пароля), иначе из окружения."""
    return await db.get_setting(user_id, PASSWORD_SETTING_KEY) or ENV_PASSWORD_HASH


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("fly-client-ip") or request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


async def require_user(request: Request) -> int:
    """Проверка сессионной куки. 401 — фронт уводит на /login."""
    user_id = await resolve_user_id()
    fp = password_fingerprint(await current_password_hash(user_id))
    username = read_token(SESSION_SECRET, request.cookies.get(COOKIE_NAME), fp)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="нужен вход")
    return user_id


@app.middleware("http")
async def guard_mutations(request: Request, call_next):
    """CSRF-щит: изменяющие запросы принимаем только с нашего же origin."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if origin and host and origin.split("//")[-1] != host:
            return JSONResponse({"detail": "чужой origin"}, status_code=403)
    response = await call_next(request)
    # Личный трекер не должен попадать в поисковые индексы.
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


# --- Модели запросов -----------------------------------------------------

class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    current: str
    new: str = Field(min_length=6, max_length=200)


class ExpenseIn(BaseModel):
    amount: float = Field(gt=0)
    category_id: int
    currency: str = "EUR"
    description: str | None = None
    date: str | None = None


class ExpensePatch(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    category_id: int | None = None
    currency: str | None = None
    description: str | None = None
    date: str | None = None


class IncomeIn(BaseModel):
    amount: float = Field(gt=0)
    currency: str = "EUR"
    description: str | None = None
    date: str | None = None


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    monthly_limit: float | None = None      # None = авто (делит свободный остаток)
    weekly_limit: float | None = None


class SubscriptionIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    amount: float = Field(gt=0)
    period: str = "monthly"
    months: float | None = None
    category_id: int | None = None


class SettingsIn(BaseModel):
    plan_mode: str | None = None
    planned_income: float | None = None
    plan_budget: float | None = None
    warn_threshold: float | None = None
    balance: float | None = None


class ResetIn(BaseModel):
    confirm: str


# --- Хелперы -------------------------------------------------------------

def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def normalize_date(value: str | None) -> str:
    """'12.10', '12.10.2026', '' → YYYY-MM-DD (пусто = сегодня)."""
    text = (value or "").strip()
    if text in ("", "-", "сегодня", "today"):
        return today_str()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        day, month = text.split(".")
        return datetime(datetime.now().year, int(month), int(day)).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"не понимаю дату: {value!r}")


async def expense_payload(expense_id: int, user_id: int) -> dict:
    row = await db.get_expense_by_id(user_id, expense_id)
    if not row:
        raise HTTPException(status_code=404, detail="трата не найдена")
    return row


def plan_summary(plan: dict) -> dict:
    """Компактная выжимка плана — её рисует шапка дашборда."""
    return {
        "base": plan["base"],
        "base_source": plan["base_source"],
        "mode": plan["mode"],
        "mode_label": plan["mode_label"],
        "balance": plan["balance"],
        "spent_this_month": plan["spent_this_month"],
        "spent_total": plan["spent_total"],
        "today_spent": plan["today_spent"],
        "periodic_total": plan["periodic_total"],
        "planned_total": plan["planned_total"],
        "unallocated": plan["unallocated"],
        "days_left": plan["days_left"],
        "fits": plan["fits"],
        "month_start": plan["month_start"],
        "warn_threshold": plan["warn_threshold"],
        "income_this_month": plan["income_this_month"],
        "planned_income": plan["planned_income"],
        "plan_budget": plan["plan_budget"],
        "items": [
            {
                "name": it["name"],
                "plan": it["plan"],
                "spent": it["spent"],
                "left": it["left"],
                "per_day": it["per_day"],
                "auto": it["auto"],
                "periodic": it["periodic"],
                "fixed": it["fixed"],
                "source": it["source"],
            }
            for it in plan["items"]
        ],
        "warnings": warning_lines(plan),
    }


# --- Авторизация ---------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/robots.txt", include_in_schema=False)
async def robots() -> Response:
    return Response("User-agent: *\nDisallow: /\n", media_type="text/plain")


@app.get("/api/auth/me")
async def whoami(request: Request) -> dict:
    user_id = await resolve_user_id()
    fp = password_fingerprint(await current_password_hash(user_id))
    username = read_token(SESSION_SECRET, request.cookies.get(COOKIE_NAME), fp)
    return {"authenticated": bool(username), "username": username or AUTH_USERNAME, "user_id": user_id}


@app.post("/api/auth/login")
async def login(payload: LoginIn, request: Request, response: Response) -> dict:
    ip = client_ip(request)
    blocked = limiter.blocked_for(ip)
    if blocked:
        raise HTTPException(status_code=429, detail=f"слишком много попыток, подожди {blocked // 60 + 1} мин.")

    user_id = await resolve_user_id()
    stored = await current_password_hash(user_id)
    ok = payload.username.strip().lower() == AUTH_USERNAME.lower() and verify_password(payload.password, stored)
    if not ok:
        limiter.register_fail(ip)
        left = max(0, limiter.max_fails - len(limiter._fails.get(ip, [])))
        log.warning("неудачный вход с %s (осталось попыток: %s)", ip, left)
        raise HTTPException(status_code=401, detail="неверный логин или пароль")

    limiter.reset(ip)
    token = make_token(SESSION_SECRET, AUTH_USERNAME, password_fingerprint(stored))
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=30 * 24 * 3600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    log.info("вход выполнен с %s", ip)
    return {"ok": True, "username": AUTH_USERNAME}


@app.post("/api/auth/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.post("/api/auth/password")
async def change_password(payload: PasswordIn, user_id: int = Depends(require_user)) -> dict:
    stored = await current_password_hash(user_id)
    if not verify_password(payload.current, stored):
        raise HTTPException(status_code=403, detail="текущий пароль неверный")
    await db.set_setting(user_id, PASSWORD_SETTING_KEY, hash_password(payload.new))
    log.info("пароль веб-версии изменён")
    return {"ok": True, "note": "старые сессии закрыты, войди заново"}


# --- Обзор ---------------------------------------------------------------

@app.get("/api/overview")
async def overview(user_id: int = Depends(require_user)) -> dict:
    plan = await load_plan(db, user_id)
    week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    week_spent = round(sum(e["amount"] for e in await db.get_expenses(user_id, start_date=week_start, limit=1000)), 2)
    month_start, today, _ = month_bounds()
    daily = await db.get_daily_spending(user_id, month_start, today)
    return {
        "plan": plan_summary(plan),
        "week_spent": week_spent,
        "week_start": week_start,
        "today": today,
        "daily": daily,
        "categories": await db.get_categories(user_id),
        "recent_expenses": await db.get_expenses(user_id, limit=15),
        "recent_incomes": await db.get_incomes(user_id, limit=10),
        "periods": [{"value": p, "label": PERIOD_LABELS[p]} for p in PERIODS],
    }


# --- Траты ---------------------------------------------------------------

@app.get("/api/expenses")
async def list_expenses(
    start: str | None = None,
    end: str | None = None,
    category_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: int = Depends(require_user),
) -> dict:
    items = await db.get_expenses(
        user_id,
        start_date=normalize_date(start) if start else None,
        end_date=normalize_date(end) if end else None,
        category_id=category_id,
        limit=max(1, min(limit, 500)),
        offset=max(0, offset),
    )
    total = await db.get_expenses_count(
        user_id,
        start_date=normalize_date(start) if start else None,
        end_date=normalize_date(end) if end else None,
    )
    return {"expenses": items, "total": total}


@app.post("/api/expenses", status_code=201)
async def create_expense(payload: ExpenseIn, user_id: int = Depends(require_user)) -> dict:
    category = await _category_by_id(user_id, payload.category_id)
    amount_eur = round(await to_eur(payload.amount, payload.currency), 2)
    date = normalize_date(payload.date)
    expense_id = await db.add_expense(
        user_id, amount_eur, payload.currency.upper(), category["id"], (payload.description or None), date
    )
    await db.add_to_balance(user_id, -amount_eur)
    plan = await load_plan(db, user_id)
    return {
        "expense": await expense_payload(expense_id, user_id),
        "converted_eur": amount_eur,
        "plan": plan_summary(plan),
        "warnings": warning_lines(plan, only_category=category["name"]),
    }


@app.patch("/api/expenses/{expense_id}")
async def edit_expense(expense_id: int, payload: ExpensePatch, user_id: int = Depends(require_user)) -> dict:
    old = await expense_payload(expense_id, user_id)
    fields: dict = {}
    if payload.amount is not None or payload.currency is not None:
        currency = (payload.currency or old["currency"] or "EUR").upper()
        amount_in = payload.amount if payload.amount is not None else old["amount"]
        new_amount = round(await to_eur(amount_in, currency), 2) if currency != "EUR" else round(amount_in, 2)
        # Баланс держим в EUR: сначала откатываем старую сумму, потом списываем новую.
        await db.add_to_balance(user_id, old["amount"])
        await db.add_to_balance(user_id, -new_amount)
        fields.update(amount=new_amount, currency=currency)
    if payload.category_id is not None:
        fields["category_id"] = (await _category_by_id(user_id, payload.category_id))["id"]
    if payload.description is not None:
        fields["description"] = payload.description or None
    if payload.date is not None:
        fields["expense_date"] = normalize_date(payload.date)
    if fields:
        await db.update_expense(user_id, expense_id, **fields)
    plan = await load_plan(db, user_id)
    return {"expense": await expense_payload(expense_id, user_id), "plan": plan_summary(plan)}


@app.delete("/api/expenses/{expense_id}")
async def remove_expense(expense_id: int, user_id: int = Depends(require_user)) -> dict:
    expense = await expense_payload(expense_id, user_id)
    await db.delete_expense(user_id, expense_id)
    await db.add_to_balance(user_id, expense["amount"])
    plan = await load_plan(db, user_id)
    return {"ok": True, "deleted": expense, "plan": plan_summary(plan)}


async def _category_by_id(user_id: int, category_id: int) -> dict:
    for category in await db.get_categories(user_id):
        if category["id"] == category_id:
            return category
    raise HTTPException(status_code=404, detail="категория не найдена")


# --- Доходы --------------------------------------------------------------

@app.get("/api/incomes")
async def list_incomes(
    start: str | None = None, end: str | None = None, limit: int = 50, user_id: int = Depends(require_user)
) -> dict:
    incomes = await db.get_incomes(
        user_id,
        start_date=normalize_date(start) if start else None,
        end_date=normalize_date(end) if end else None,
        limit=max(1, min(limit, 500)),
    )
    total = await db.get_income_total(
        user_id,
        start_date=normalize_date(start) if start else None,
        end_date=normalize_date(end) if end else None,
    )
    return {"incomes": incomes, "total": total}


@app.post("/api/incomes", status_code=201)
async def create_income(payload: IncomeIn, user_id: int = Depends(require_user)) -> dict:
    amount_eur = round(await to_eur(payload.amount, payload.currency), 2)
    income_id = await db.add_income(
        user_id, amount_eur, payload.currency.upper(), payload.description or None, normalize_date(payload.date)
    )
    await db.add_to_balance(user_id, amount_eur)
    plan = await load_plan(db, user_id)
    return {"income": await db.get_income_by_id(user_id, income_id), "converted_eur": amount_eur,
            "plan": plan_summary(plan)}


@app.delete("/api/incomes/{income_id}")
async def remove_income(income_id: int, user_id: int = Depends(require_user)) -> dict:
    income = await db.get_income_by_id(user_id, income_id)
    if not income:
        raise HTTPException(status_code=404, detail="доход не найден")
    await db.delete_income(user_id, income_id)
    await db.add_to_balance(user_id, -income["amount"])
    plan = await load_plan(db, user_id)
    return {"ok": True, "deleted": income, "plan": plan_summary(plan)}


# --- Категории -----------------------------------------------------------

@app.get("/api/categories")
async def list_categories(user_id: int = Depends(require_user)) -> dict:
    categories = await db.get_categories(user_id)
    month_start, today, _ = month_bounds()
    spent = {row["category_name"]: float(row["spent"]) for row in
             await db.get_spending_by_category(user_id, month_start, today)}
    for category in categories:
        category["spent_this_month"] = spent.get(category["name"], 0.0)
    return {"categories": categories}


@app.post("/api/categories", status_code=201)
async def create_category(payload: CategoryIn, user_id: int = Depends(require_user)) -> dict:
    name = payload.name.strip().lower()
    if not name:
        raise HTTPException(status_code=422, detail="пустое имя категории")
    if await db.get_category_by_name(user_id, name):
        raise HTTPException(status_code=409, detail="такая категория уже есть")
    category = await db.add_category(user_id, name)
    if payload.monthly_limit is not None:
        await db.set_category_monthly_plan(user_id, name, payload.monthly_limit)
    if payload.weekly_limit is not None:
        await db.set_category_limit(user_id, name, payload.weekly_limit)
    return {"category": await db.get_category_by_name(user_id, name), "created": category is not None}


@app.patch("/api/categories/{category_id}")
async def edit_category(category_id: int, payload: CategoryIn, user_id: int = Depends(require_user)) -> dict:
    current = await _category_by_id(user_id, category_id)
    new_name = payload.name.strip().lower()
    if new_name != current["name"]:
        if await db.get_category_by_name(user_id, new_name):
            raise HTTPException(status_code=409, detail="такая категория уже есть")
        await db.rename_category(user_id, category_id, new_name)
    if payload.monthly_limit is not None:
        plan_value: float | None = payload.monthly_limit
    else:
        plan_value = None
    await db.set_category_monthly_plan(user_id, new_name, plan_value)
    if payload.weekly_limit is not None:
        await db.set_category_limit(user_id, new_name, payload.weekly_limit)
    plan = await load_plan(db, user_id)
    return {"category": await db.get_category_by_name(user_id, new_name), "plan": plan_summary(plan)}


@app.delete("/api/categories/{category_id}")
async def remove_category(category_id: int, user_id: int = Depends(require_user)) -> dict:
    category = await _category_by_id(user_id, category_id)
    used = await db.get_expenses_count(user_id, category_id=category_id)
    if used:
        raise HTTPException(
            status_code=409,
            detail=f"в категории «{category['name']}» {used} трат — сначала перенеси или удали их",
        )
    await db.delete_category(user_id, category_id)
    plan = await load_plan(db, user_id)
    return {"ok": True, "deleted": category["name"], "plan": plan_summary(plan)}


# --- Подписки ------------------------------------------------------------

@app.get("/api/subscriptions")
async def list_subscriptions(user_id: int = Depends(require_user)) -> dict:
    return await subscriptions_payload(user_id)


async def subscriptions_payload(user_id: int) -> dict:
    """Единый формат подписок для GET/POST/PATCH — иначе свежесозданная строка
    приходит без посчитанных полей и фронт падает на несуществующем ключе."""
    subs = await db.get_subscriptions(user_id)
    for sub in subs:
        sub["months"] = months_of(sub)
        sub["monthly_amount"] = round(monthly_amount(sub), 2)
        sub["period_label"] = period_label(sub["months"])
    total = round(sum(s["monthly_amount"] for s in subs), 2)
    return {"subscriptions": subs, "monthly_total": total,
            "periods": [{"value": p, "label": PERIOD_LABELS[p]} for p in PERIODS]}


@app.post("/api/subscriptions", status_code=201)
async def create_subscription(payload: SubscriptionIn, user_id: int = Depends(require_user)) -> dict:
    months = payload.months if payload.months else months_of({"period": payload.period})
    await db.add_subscription(
        user_id, payload.name.strip(), payload.amount, payload.period, months=months, category_id=payload.category_id
    )
    plan = await load_plan(db, user_id)
    return {"subscriptions": (await subscriptions_payload(user_id))["subscriptions"], "plan": plan_summary(plan)}


@app.patch("/api/subscriptions/{sub_id}")
async def edit_subscription(sub_id: int, payload: SubscriptionIn, user_id: int = Depends(require_user)) -> dict:
    if not await db.get_subscription(user_id, sub_id):
        raise HTTPException(status_code=404, detail="платёж не найден")
    months = payload.months if payload.months else months_of({"period": payload.period})
    await db.update_subscription(
        user_id, sub_id, name=payload.name.strip(), amount=payload.amount,
        period=payload.period, months=months, category_id=payload.category_id,
    )
    plan = await load_plan(db, user_id)
    return {"subscriptions": (await subscriptions_payload(user_id))["subscriptions"], "plan": plan_summary(plan)}


@app.delete("/api/subscriptions/{sub_id}")
async def remove_subscription(sub_id: int, user_id: int = Depends(require_user)) -> dict:
    sub = await db.get_subscription(user_id, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="платёж не найден")
    await db.delete_subscription(user_id, sub_id)
    plan = await load_plan(db, user_id)
    return {"ok": True, "deleted": sub, "plan": plan_summary(plan)}


# --- Настройки -----------------------------------------------------------

@app.get("/api/settings")
async def get_settings(user_id: int = Depends(require_user)) -> dict:
    return {
        "plan_mode": await db.get_setting(user_id, SET_PLAN_MODE, "available"),
        "planned_income": await db.get_setting_float(user_id, SET_PLANNED_INCOME, 0.0),
        "plan_budget": await db.get_setting_float(user_id, SET_PLAN_BUDGET, DEFAULT_PLAN_BUDGET),
        "warn_threshold": await db.get_setting_float(user_id, SET_WARN_THRESHOLD, DEFAULT_WARN_THRESHOLD),
        "balance": await db.get_balance(user_id),
        "username": AUTH_USERNAME,
        "user_id": user_id,
        "rate_limits": {k: v for k, v in (await exchange_rates()).items()},
        "modes": [{"value": k, "label": v} for k, v in PLAN_MODE_LABELS.items()],
    }


@app.put("/api/settings")
async def put_settings(payload: SettingsIn, user_id: int = Depends(require_user)) -> dict:
    if payload.plan_mode is not None:
        if payload.plan_mode not in PLAN_MODE_LABELS:
            raise HTTPException(status_code=422, detail="неизвестный режим плана")
        await db.set_setting(user_id, SET_PLAN_MODE, payload.plan_mode)
    if payload.planned_income is not None:
        await db.set_setting(user_id, SET_PLANNED_INCOME, payload.planned_income)
    if payload.plan_budget is not None:
        await db.set_setting(user_id, SET_PLAN_BUDGET, payload.plan_budget)
    if payload.warn_threshold is not None:
        await db.set_setting(user_id, SET_WARN_THRESHOLD, payload.warn_threshold)
    if payload.balance is not None:
        await db.set_balance(user_id, payload.balance)
    return await get_settings(user_id)


# --- Статистика, экспорт, бэкап ------------------------------------------

def _period_range(period: str) -> tuple[str, str]:
    today = datetime.now()
    if period == "week":
        start = today - timedelta(days=7)
    elif period == "month":
        start = today - timedelta(days=30)
    elif period == "year":
        start = today - timedelta(days=365)
    elif period == "current_month":
        start = today.replace(day=1)
    else:
        start = datetime(2000, 1, 1)
    return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


@app.get("/api/stats")
async def stats(period: str = "month", user_id: int = Depends(require_user)) -> dict:
    start, end = _period_range(period)
    by_category = await db.get_spending_by_category(user_id, start, end)
    by_category = sorted(
        (row for row in by_category if row["spent"] > 0), key=lambda row: row["spent"], reverse=True
    )
    daily = await db.get_daily_spending(user_id, start, end)
    expenses = await db.get_expenses(user_id, start_date=start, end_date=end, limit=500)
    total = round(sum(row["spent"] for row in by_category), 2)
    days = len(daily) or 1
    plan = await load_plan(db, user_id)
    plan_by_name = {it["name"]: it for it in plan["items"]}
    for row in by_category:
        item = plan_by_name.get(row["category_name"])
        row["plan"] = item["plan"] if item else 0.0
        row["left"] = item["left"] if item else 0.0
        row["share"] = round(row["spent"] / total * 100, 1) if total else 0.0
    return {
        "period": period,
        "start": start,
        "end": end,
        "total": total,
        "count": len(expenses),
        "days": days,
        "avg_per_day": round(total / days, 2),
        "by_category": by_category,
        "daily": daily,
        "expenses": expenses,
        "income_total": round(await db.get_income_total(user_id, start, end), 2),
    }


# Названия месяцев для подписи оси: короткие — на графике, полные — в подсказке.
MONTH_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
MONTH_FULL = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]


def _month_label(month: str, full: bool = False) -> str:
    """'2026-10' → 'окт 26' либо 'октябрь 2026'."""
    year, number = month.split("-")
    names = MONTH_FULL if full else MONTH_SHORT
    return f"{names[int(number) - 1]} {year}" if full else f"{names[int(number) - 1]} {year[2:]}"


@app.get("/api/monthly")
async def monthly(months: int = 12, user_id: int = Depends(require_user)) -> dict:
    """Траты/доходы по месяцам с накоплением.

    Окно — последние `months` месяцев включая текущий; пустые месяцы внутри окна
    присутствуют нулями, иначе на графике соседние точки склеились бы.
    """
    months = max(1, min(60, months))
    last_month = datetime.now().replace(day=1)
    first_month = last_month
    for _ in range(months - 1):
        first_month = (first_month - timedelta(days=1)).replace(day=1)

    rows = {
        row["month"]: row
        for row in await db.get_monthly_totals(user_id, first_month.strftime("%Y-%m-%d"))
    }

    series: list[dict] = []
    cumulative = 0.0
    cursor = first_month
    while cursor <= last_month:
        key = cursor.strftime("%Y-%m")
        row = rows.get(key, {})
        spent = round(float(row.get("spent", 0.0)), 2)
        income = round(float(row.get("income", 0.0)), 2)
        cumulative = round(cumulative + spent, 2)
        series.append({
            "month": key,
            "label": _month_label(key),
            "title": _month_label(key, full=True),
            "spent": spent,
            "income": income,
            "net": round(income - spent, 2),
            "count": int(row.get("cnt", 0)),
            "cumulative": cumulative,
        })
        cursor = (cursor + timedelta(days=32)).replace(day=1)

    spent_values = [item["spent"] for item in series]
    busiest = max(series, key=lambda item: item["spent"]) if series else None
    return {
        "months": months,
        "series": series,
        "spent_total": round(sum(spent_values), 2),
        "income_total": round(sum(item["income"] for item in series), 2),
        "avg_per_month": round(sum(spent_values) / len(series), 2) if series else 0.0,
        "max_month": busiest["month"] if busiest and busiest["spent"] > 0 else None,
    }


@app.get("/api/export.csv")
async def export_csv(user_id: int = Depends(require_user)) -> StreamingResponse:
    """Тот же набор колонок, что отдавал бот через /export."""
    expenses = await db.get_expenses(user_id, limit=100000)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Дата", "Сумма (EUR)", "Категория", "Описание", "Валюта", "Исходная сумма"])
    for expense in reversed(expenses):  # от старых к новым, как в боте
        writer.writerow([
            expense["expense_date"], expense["amount"], expense["category_name"],
            expense["description"] or "", expense["currency"], expense["amount"],
        ])
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="expenses-{stamp}.csv"'},
    )


@app.get("/api/backup")
async def backup(user_id: int = Depends(require_user)) -> FileResponse:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return FileResponse(DB_PATH, media_type="application/octet-stream", filename=f"expenses-{stamp}.db")


@app.post("/api/reset")
async def reset(payload: ResetIn, user_id: int = Depends(require_user)) -> dict:
    if payload.confirm != "УДАЛИТЬ":
        raise HTTPException(status_code=422, detail="подтверждение не совпало: напиши УДАЛИТЬ")
    await db.reset_user(user_id)
    return {"ok": True, "plan": plan_summary(await load_plan(db, user_id))}


# --- Статика SPA ---------------------------------------------------------
# Фронтенд собирается в web/static и раздаётся тем же процессом: один origin,
# куки-авторизация без CORS.

if STATIC_DIR.exists():
    class HashedAssets(StaticFiles):
        """Файлы сборки содержат хеш в имени, поэтому кешируются навсегда —
        новый релиз приносит новые имена. Без этого браузер держит старый бандл."""

        async def get_response(self, path, scope):  # noqa: ANN001, ANN201
            response = await super().get_response(path, scope)
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

    app.mount("/assets", HashedAssets(directory=STATIC_DIR / "assets"), name="assets")
    STATIC_ROOT = STATIC_DIR.resolve()

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    async def spa(full_path: str):  # noqa: ANN202
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="нет такого метода")
        # resolve() + проверка каталога: без этого «/../../.env» отдавал бы файлы вне сборки
        candidate = (STATIC_DIR / full_path).resolve()
        if full_path and candidate.is_file() and STATIC_ROOT in candidate.parents:
            return FileResponse(candidate)
        # index.html — единственный файл без хеша в имени: его нельзя кешировать,
        # иначе после деплоя браузер тянет старые ссылки на ассеты. no-cache требует
        # ревалидации по ETag, а не перезагрузки: обычно это дешёвый 304.
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
else:  # pragma: no cover — до первой сборки фронтенда
    @app.get("/")
    async def placeholder() -> dict:
        return {"detail": "фронтенд не собран: npm --prefix frontend run build"}
