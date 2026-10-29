# --- сборка Vue-фронтенда -------------------------------------------------
FROM node:22-alpine AS ui

WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
# Сборка идёт в /ui/dist: локальный outDir (../web/static) внутри образа вне рабочей папки
RUN VITE_OUT_DIR=dist npm run build

# --- рантайм: бот почты + веб-версия --------------------------------------
FROM python:3.12-slim

WORKDIR /app

# Install build dependencies (for aiosqlite, etc.) + tzdata для TZ=Europe/Bratislava
RUN apt-get update && apt-get install -y --no-install-recommends gcc tzdata && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=ui /ui/dist ./web/static

CMD ["python", "supervisor.py"]
