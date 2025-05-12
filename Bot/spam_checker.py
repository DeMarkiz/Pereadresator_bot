import asyncio
import logging
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import PeerUser
import time


# Настройка логирования
logging.basicConfig(filename="spam_check.log", level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")


# Функция для проверки аккаунта через @SpamBot
class SpamChecker:
    def __init__(self, client):
        self.client = client

    async def check(self) -> str:
        await self.client.send_message("@SpamBot", "/start")
        await asyncio.sleep(5)  # подожди немного, чтобы бот ответил
        messages = await self.client.get_messages('@SpamBot', limit=1)
        if messages:
            text = messages[0].message.lower()
            if "спам" in text or "Есть Ограничения" in text:
                return "spam"
            else:
                return "not_spam"
        return "unknown"



# # Пример использования
# def main():
#     # Параметры клиента
#     session_file = 'your_session_file.session'
#     api_id = 'your_api_id'
#     api_hash = 'your_api_hash'
#
#     client = TelegramClient(session_file, api_id, api_hash)
#
#     try:
#         client.connect()
#         if client.is_user_authorized():
#             result = SpamChecker(client)
#             print(result)
#         else:
#             print("Аккаунт не авторизован.")
#     except Exception as e:
#         print(f"Ошибка: {e}")
#     finally:
#         client.disconnect()
#
#
# if __name__ == "__main__":
#     main()

