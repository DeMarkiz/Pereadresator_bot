import asyncio
import contextlib
import datetime
import json
import sys
import os
import random

from typing import Optional, Union
from loguru import logger

from telethon import TelegramClient, functions
from telethon.tl import types
from telethon.tl.functions.auth import ResetAuthorizationsRequest
from telethon import password as pwd_mod
from telethon.tl.functions.account import UpdateStatusRequest, GetAuthorizationsRequest
from telethon.errors import UserDeactivatedError, UserDeactivatedBanError, SessionRevokedError, \
    SessionPasswordNeededError, AuthKeyDuplicatedError, AuthKeyNotFound, AuthKeyUnregisteredError, \
    PasswordHashInvalidError, AuthTokenExpiredError, AuthTokenAlreadyAcceptedError, AuthTokenInvalidError

from Bot.spam_checker import SpamChecker
from base_client import TelegramClient


import config
import utils

logger.remove()
logger.add(
    sys.stdout,
    format="<w>{time:YYYY-MM-DD HH:mm:ss}</w> | <level>{level: <5}</level> | <level>{message}</level>"
)


class Session:
    def __init__(self, session_name, proxy: Optional[tuple] = True, settings: dict = config.SETTINGS):
        self.json_data = {}
        self.dialogs = []
        self.archived = []
        self.__connection_attempt = 0
        self.session_name = session_name

        self.settings = settings
        self._proxy = proxy
        self.disconnected = False
        self._thread = None

        try:
            with open(f"./sessions/{self.session_name}.json", 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
        except FileNotFoundError:
            self.log(f"Не удалось найти json для аккаунта {self.session_name}")
            return
        except Exception as e:
            self.log(f"Ошибка json для аккаунта {self.session_name} ({e})")
            return

        try:
            self.client = TelegramClient(
                session=f"./sessions/{self.session_name}.session",
                api_id=self.json_data['app_id'],
                api_hash=self.json_data['app_hash'],
                device_model=self.json_data['device'],
                app_version=self.json_data['app_version'],
                lang_code=self.json_data.get("lang_pack", "ru"),
                system_lang_code=self.json_data.get("system_lang_pack", "ru-RU"),
                system_version=self.json_data['sdk'],
                lang_pack=config.API_PACKS.get(self.json_data['app_id'], ""),
                proxy=proxy,
                timeout=20,
                entity_cache_limit=1000000
            )
        except Exception as e:
            self.log(f"Ошибка json для аккаунта {self.session_name} ({e})")
            return

        self.log("Аккаунт инициализирован")

    @staticmethod
    def raise_auth():
        """Raise InteractiveAuth exception"""
        raise utils.InteractiveAuthRequired()

    async def sleep(self, a: int = 0, b: int = 1, log: bool = False, time=None):
        """Random async sleep from a to b seconds"""
        seconds = time or random.randint(a * 100, b * 100) / 100
        if log:
            self.log(f"<c>Перехожу в сон на <u>{seconds} секунд</u>...</c>")
        await asyncio.sleep(seconds)

    def log(self, message: str, level: str = 'info'):
        """Log session information"""
        thread_info = f"<e>[Поток: {self._thread}]</e>" if self._thread is not None else ""
        logger.opt(colors=True).log(level.upper(), f"{thread_info}<c>[{self.session_name}]</c> {message}")

    async def connect(self, thread: int = None) -> Optional[bool]:
        """Connecting client"""
        if not hasattr(self, 'client'):
            return False

        if thread is not None:
            self._thread = thread
        if self.__connection_attempt >= self.settings['attempts_count']:
            self.log("Не удалось подключится к аккаунту. Достигнуто максимальное количество попыток.", level='error')
            self.__connection_attempt = 0
            await self.disconnect()
            return False

        self.__connection_attempt += 1
        self.log(f"Подключаюсь... (Попытка {self.__connection_attempt})")
        try:
            try:
                # await self.client.start(phone=self.raise_auth, code_callback=self.raise_auth)
                await self.client.connect()
                self.log("<G>Аккаунт подключен</G>")
                await self.update_status(offline=False)
            except SessionPasswordNeededError as e:
                if not (password := self.json_data.get("twoFA", None)):
                    raise e

                await self.client.sign_in(password=password)
                os.system("pause")
                await self.update_status(offline=False)

            self.__connection_attempt = 0
            return True
        except (
            AuthKeyDuplicatedError,
            AuthKeyNotFound,
            AuthKeyUnregisteredError,
            SessionRevokedError,
            UserDeactivatedBanError,
            UserDeactivatedError,
        ) as e:
            self.log(f"<R>Сессия больше недоступна ({e.__class__.__name__})</R>")
            await self.disconnect()
            await self.move_session_file("dead_sessions")
            return None
        except BaseException as e:
            self.log(f"Не удалось подключится к аккаунту ({e}) (Попытка {self.__connection_attempt})",
                     level='error')
            await asyncio.sleep(self.settings['attempt_sleep'])
            return await self.connect()

    async def move_session_file(self, directory: str):
        """Move session and json files to specified directory"""
        with contextlib.suppress(BaseException):
            os.mkdir(directory)

        with contextlib.suppress(BaseException):
            os.remove(f"./{directory}/{self.session_name}.session")
        with contextlib.suppress(BaseException):
            os.remove(f"./{directory}/{self.session_name}.json")

        while True:
            await asyncio.sleep(0)
            with contextlib.suppress(BaseException):
                os.rename(f"./sessions/{self.session_name}.session", f"./{directory}/{self.session_name}.session")
                with contextlib.suppress(BaseException):
                    os.rename(f"./sessions/{self.session_name}.json", f"./{directory}/{self.session_name}.json")
                self.log(f'Сессия перенесена в папку {directory}')
                break

    async def disconnect(self) -> None:
        """Disconnecting client"""
        if not hasattr(self, 'client'):
            return

        if not self.client.is_connected():
            return

        with contextlib.suppress(BaseException):
            await self.update_status(offline=True)

        with contextlib.suppress(BaseException):
            await self.client.disconnect()
        # self.log("<R>Аккаунт отключен</R>")
        return

    async def update_status(self, offline: bool) -> None:
        """Update online status of account"""
        # self.log(f"Перевел статус на {'<r>Оффлайн</r>' if offline else '<g>Онлайн</g>'}")
        await self.client(UpdateStatusRequest(offline))

    async def create_new_session(self, folder: str, proxy: Optional[tuple]) -> Union[bool, str]:
        """Create new session"""
        self.log("Создаю новую сессию...")

        # Загружаем данные из json-файла
        session_file = f"./sessions/{self.session_name}.json"

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
        except FileNotFoundError:
            self.log(f"Файл {session_file} не найден.")
            return False

        # Получаем данные из json
        app_id = self.json_data.get('app_id', '')
        app_hash = self.json_data.get('app_hash', '')
        device_model = self.json_data.get('device', '')
        app_version = self.json_data.get('app_version', '')
        lang_code = self.json_data.get('lang_code', '')
        system_lang_code = self.json_data.get('system_lang_pack', '')
        system_version = self.json_data.get('sdk', '')
        lang_pack = self.json_data.get('lang_pack', '')
        system_lang_pack = self.json_data.get('system_lang_pack', '')

        # Логируем полученные данные
        self.log(f"app_id: {app_id}, app_hash: {app_hash}")
        self.log(f"device_model: {device_model}, app_version: {app_version}")
        self.log(f"lang_code: {lang_code}, system_lang_code: {system_lang_code}")
        self.log(f"system_version: {system_version}, lang_pack: {lang_pack}")
        self.log(f"system_lang_pack: {system_lang_pack}")

        json_data = {
            "app_id": int(app_id),
            "app_hash": app_hash,
            "device": device_model,
            "sdk": system_version,
            "app_version": app_version,
            "lang_pack": lang_pack,
            "system_lang_pack": system_lang_pack,
        }

        new_session = TelegramClient(
            session=f"./{folder}/{self.session_name}.session",
            api_id=json_data["app_id"],
            api_hash=json_data["app_hash"],
            device_model=json_data["device"],
            system_version=json_data["sdk"],
            app_version=json_data["app_version"],
            lang_code=json_data["lang_pack"],
            system_lang_code=json_data["system_lang_pack"],
            lang_pack=config.API_PACKS.get(self.json_data['app_id'], ""),
            proxy=proxy,
        )

        attempts = 5
        for i in range(attempts):
            try:
                await new_session.connect()
                if new_session.session.dc_id != self.client.session.dc_id:
                    await new_session._switch_dc(self.client.session.dc_id)

                break
            except TypeError as e:
                if i == attempts - 1:
                    raise e
            except BaseException as e:
                await new_session.disconnect()
                if i == attempts - 1:
                    raise e


        request_retries = 5
        try:
            for attempt in range(request_retries):
                self.log(f"Создаю qr code... Попытка ({attempt + 1})")
                try:
                    if attempt > 0 and await new_session.is_user_authorized():
                        break

                    qr_login = await new_session.qr_login()

                    if isinstance(qr_login._resp, types.auth.LoginTokenMigrateTo):
                        self.log("Меняю датацентр...")
                        await new_session._switch_dc(qr_login._resp.dc_id)
                        qr_login._resp = await new_session(
                            functions.auth.ImportLoginTokenRequest(qr_login._resp.token)
                        )

                    if isinstance(qr_login._resp, types.auth.LoginTokenSuccess):
                        await new_session._on_login(qr_login._resp.authorization.user)
                        break

                    time_now = datetime.datetime.now(datetime.timezone.utc)
                    time_out = (qr_login.expires - time_now).seconds + 5

                    resp = await self.client(
                        functions.auth.AcceptLoginTokenRequest(qr_login.token)
                    )

                    await qr_login.wait(time_out)

                    break
                except AuthTokenAlreadyAcceptedError:
                    pass
                except (AuthTokenExpiredError, AuthTokenInvalidError):
                    pass
                except (TimeoutError, asyncio.TimeoutError):
                    pass
            else:
                raise asyncio.TimeoutError(
                    "Вышло время ожидания"
                )

        except SessionPasswordNeededError as e:
            self.log("<y>Требуется пароль для входа. Пробую 2FA из json файла...</y>")
            try:
                if not (password := self.json_data.get("twoFA", None)):
                    raise Exception("Пароль не найден в json")

                pwd: types.account.Password = await new_session(
                    functions.account.GetPasswordRequest())
                result = await new_session(
                    functions.auth.CheckPasswordRequest(
                        pwd_mod.compute_check(pwd, password)
                    )
                )

                await new_session._on_login(result.user)
                json_data["twoFA"] = password
            except Exception as e:
                if isinstance(e, PasswordHashInvalidError):
                    self.log(f"Не удалось войти с паролем (Неверный пароль)", level='error')
                else:
                    self.log(f"Не удалось войти с паролем ({e})", level='error')

                await new_session.disconnect()
                await self.disconnect()

                os.remove(f"./{folder}/{self.session_name}.session")
                await self.move_session_file("wrong_2fa_sessions")
                return "wrong_2fa_sessions"
        except BaseException as e:
            self.log(f"Не удалось авторизоваться ({e}, {e.__class__.__name__})", level='error')
            await new_session.disconnect()
            os.remove(f"./{folder}/{self.session_name}.session")
            return False

        self.log("<g>Авторизация прошла успешно!</g>")

        with open(f"./{folder}/{self.session_name}.json", "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4)

        self.log("Проверяю на спам...")

        checker = SpamChecker(new_session)
        spam_status = await checker.check()

        self.log(f"Статус аккаунта: {spam_status}")

        await new_session.disconnect()
        return True

    async def get_my_session(self, client: Optional[TelegramClient] = None):
        if client is None:
            client = self.client

        sessions = (await client(GetAuthorizationsRequest())).authorizations

        for session in sessions:
            if not session.current:
                continue

            return session

    async def close_all_sessions(self) -> bool:
        my_session = await self.get_my_session()

        difference = datetime.datetime.now(tz=my_session.date_created.tzinfo) - my_session.date_created
        if difference < datetime.timedelta(days=1):
            self.log(f"<y>Сессия создана менее 24х часов назад</y>")
            return False

        self.log("Закрываю все сессии...")

        try:
            await self.client(ResetAuthorizationsRequest())
        except Exception as e:
            self.log(f"Не удалось закрыть все сессии ({e})", level='error')
            return False
        self.log("<g>Все сессии закрыты!</g>")
        return True

    async def logout(self) -> bool:
        self.log("Закрываю сессию...")
        try:
            await self.client.log_out()
            with contextlib.suppress(BaseException):
                os.remove(f"./sessions/{self.session_name}.session")
            os.remove(f"./sessions/{self.session_name}.json")
            return True
        except BaseException as e:
            self.log(f"Не удалось закрыть сессию ({e})", level='error')
            return False
