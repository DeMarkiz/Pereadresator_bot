import os
import sys
import zipfile
import rarfile
import shutil
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
from main import run_main
import re
import io
from contextlib import redirect_stdout
from dotenv import load_dotenv



load_dotenv()

TOKEN = "BOT_TOKEN"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

SESSION_DIR = "sessions"
LOG_FILE = "log.txt"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        RichHandler(markup=True),  # Rich logging для красивого вывода в консоль
        RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")  # Логирование в файл
    ]
)

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer("Привет! Пришли архив (.zip или .rar) с Telegram-сессиями.")


@dp.message()
async def handle_archive(message: types.Message):
    if not message.document:
        return await message.reply("Пришли архив в виде документа (.zip или .rar)")

    file = message.document
    if not (file.file_name.endswith(".zip") or file.file_name.endswith(".rar")):
        return await message.reply("Поддерживаются только .zip и .rar архивы")

    file_path = f"{file.file_id}_{file.file_name}"
    await bot.download(file, destination=file_path)

    # Очистка и подготовка
    if os.path.exists(SESSION_DIR):
        shutil.rmtree(SESSION_DIR)
    os.makedirs(SESSION_DIR, exist_ok=True)

    # Распаковка
    try:
        if file.file_name.endswith(".zip"):
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(SESSION_DIR)
        elif file.file_name.endswith(".rar"):
            with rarfile.RarFile(file_path, 'r') as rar_ref:
                rar_ref.extractall(SESSION_DIR)
    except Exception as e:
        return await message.reply(f"Ошибка при распаковке: {e}")

    os.remove(file_path)

    # Перенос .session и .json в корень
    for root, _, files in os.walk(SESSION_DIR):
        for fname in files:
            if fname.endswith(".session") or fname.endswith(".json"):
                src = os.path.join(root, fname)
                dst = os.path.join(SESSION_DIR, fname)
                if src != dst:
                    shutil.move(src, dst)

    await message.reply("Архив распакован. Обработка...")

    # Перехват stdout
    f = io.StringIO()
    try:
        with redirect_stdout(f):
            await run_main()
    except Exception as e:
        return await message.reply(f"Ошибка при выполнении run_main(): {e}")

    output = f.getvalue()
    await message.reply("Обработка завершена. Читаю результат...")

    # Чтение данных из лог-файла log.txt
    success = failed = wrong_2fa = dead = spam = not_spam = 0

    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as log_file:
            output = log_file.read()

        # Прочитаем каждую строку вывода и выведем отладочную информацию
        for line in output.splitlines():
            print(f"Обрабатываю строку: {line}")  # Это поможет понять, какая строка вызывает проблему

            if "Успешно создано сессий" in line:
                match = re.search(r"Успешно создано сессий:\s*(\d+)", line)
                if match:
                    success = int(match.group(1))
                    print(f"Успешно создано сессий: {success}")  # Для отладки
            elif "Не удалось создать сессий" in line:
                match = re.search(r"Не удалось создать сессий:\s*(\d+)", line)
                if match:
                    failed = int(match.group(1))
                    print(f"Не удалось создать сессий: {failed}")  # Для отладки
            elif "Неверный пароль" in line:
                match = re.search(r"Неверный пароль:\s*(\d+)", line)
                if match:
                    wrong_2fa = int(match.group(1))
                    print(f"Неверный пароль (2FA): {wrong_2fa}")  # Для отладки
            elif "Мертвых" in line:
                match = re.search(r"Мертвых:\s*(\d+)", line)
                if match:
                    dead = int(match.group(1))
                    print(f"Мертвых сессий: {dead}")  # Для отладки

            # Проверка на статус "спам" или "не спам"
            elif "Статус аккаунта: spam" in line:
                spam += 1
            elif "Статус аккаунта: not spam" in line:
                not_spam += 1

        # Проверим, что переменные получили правильные значения
        print(
            f"Итоговые данные: Успешно: {success}, Не удалось: {failed}, Неверный пароль: {wrong_2fa}, Мертвых: {dead}, Спам: {spam}, Не спам: {not_spam}")

        # Отправим сообщение в том формате, который требуется
        await message.reply(
            f"<b>Результат обработки:</b>\n"
            f"✅ Успешно создано сессий: <b>{success}</b>\n"
            f"❌ Не удалось создать сессий: <b>{failed}</b>\n"
            f"🔑 Неверный пароль (2FA): <b>{wrong_2fa}</b>\n"
            f"💀 Мертвых сессий: <b>{dead}</b>\n"
            f"🚫 Спам: <b>{spam}</b>\n"
            f"✅ Не спам: <b>{not_spam}</b>"
        )

    except FileNotFoundError:
        await message.reply("Лог-файл не найден!")
    except Exception as e:
        await message.reply(f"Ошибка при чтении лог-файла: {e}")


if __name__ == '__main__':
    import asyncio
    from aiogram import Router

    router = Router()
    router.message.register(start_handler, CommandStart())
    router.message.register(handle_archive)
    dp.include_router(router)

    async def main():
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)

    asyncio.run(main())
