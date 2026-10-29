"""
Держит процессы контейнера: почтовый бот и веб-версию трекера трат.

Один процесс — одно приложение: у почтового бота long polling по IMAP, у сайта
uvicorn; склеивать их в один цикл — переписывать оба, а два процесса дают ту же
экономию и изолируют падения.

Бот расходов (bot.py) больше не запускается — его заменил сайт, который работает
с той же базой. Вернуть его можно переменной ENABLE_EXPENSE_BOT=1: бот и сайт
могут жить одновременно (разные интерфейсы, одна база и один user_id), но бот
добавит ~57 МБ памяти — на 256 МБ это уже впритык.

Падение ребёнка больше не роняет контейнер сразу: процесс поднимается заново
после короткой паузы, и только если он падает MAX_RESTARTS раз за WINDOW секунд,
контейнер выходит — тогда Fly перезапускает машину целиком.
"""

import logging
import os
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] supervisor: %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("supervisor")

PYTHON = sys.executable
PORT = os.environ.get("PORT", "8080")

MAX_RESTARTS = 5        # столько падений подряд
WINDOW = 600            # за такое окно секунд — и контейнер уходит на перезапуск
RESTART_DELAY = 3

PROCS = [("mail", [PYTHON, "-u", "/app/mailbot/bot.py"])]

if os.environ.get("ENABLE_EXPENSE_BOT") == "1":
    PROCS.append(("expense", [PYTHON, "-u", "/app/bot.py"]))

PROCS.append((
    "web",
    [PYTHON, "-m", "uvicorn", "web.main:app",
     "--host", "0.0.0.0", "--port", PORT, "--workers", "1"],
))


def main() -> int:
    children = []
    for name, cmd in PROCS:
        log.info("старт: %s — %s", name, " ".join(cmd))
        children.append({"name": name, "cmd": cmd, "proc": subprocess.Popen(cmd), "failures": []})

    while True:
        for child in children:
            rc = child["proc"].poll()
            if rc is None:
                continue

            now = time.time()
            child["failures"] = [t for t in child["failures"] if now - t < WINDOW]
            child["failures"].append(now)
            log.error("%s завершился с кодом %s (падений за %s мин: %s)",
                      child["name"], rc, WINDOW // 60, len(child["failures"]))

            if len(child["failures"]) >= MAX_RESTARTS:
                log.error("%s падает слишком часто — останавливаю контейнер", child["name"])
                for other in children:
                    if other["proc"].poll() is None:
                        log.info("останавливаю %s", other["name"])
                        other["proc"].terminate()
                for other in children:
                    try:
                        other["proc"].wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        other["proc"].kill()
                return rc if rc else 1

            time.sleep(RESTART_DELAY)
            log.info("перезапускаю %s", child["name"])
            child["proc"] = subprocess.Popen(child["cmd"])
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
