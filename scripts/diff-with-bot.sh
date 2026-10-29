#!/usr/bin/env bash
# Сверка «общих» файлов между папкой сайта и папкой бота.
#
# db.py и budget.py существуют в двух местах: здесь (актуальная версия, попадает
# в образ) и в /home/q/expense-bot (состояние GitHub-репозитория, бот-легаси).
# Если они разъехались — значит правку внесли не в ту папку.
set -e
cd "$(dirname "$0")/.."
BOT=/home/q/expense-bot
status=0

for f in db.py budget.py; do
    if [ ! -f "$BOT/$f" ]; then
        echo "  нет файла в папке бота: $BOT/$f"
        status=1
        continue
    fi
    if cmp -s "$f" "$BOT/$f"; then
        echo "  ok    $f — копии совпадают"
    else
        echo "  РАСХОЖДЕНИЕ  $f (показаны первые строки diff: папка бота → папка сайта)"
        diff -u "$BOT/$f" "$f" | head -40 || true
        status=1
    fi
done

exit "$status"
