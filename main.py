import asyncio
import contextlib
import os

import config
from proxy import ProxyManager
from session import Session, logger
import logging


logger.add("log.txt", format="{time} {level} {message}", colorize=False)

logging.basicConfig(level=logging.CRITICAL)
proxy_manager = ProxyManager("./proxy.txt")
stats = {
    "success": 0,
    "failed": 0,
    "wrong_2fa_sessions": 0,
    "dead_sessions": 0,
}


def load_sessions(limit: int = 99999) -> list[Session]:
    res = []
    for file in os.listdir("./sessions"):
        if file.endswith(".session"):
            session_name = file.split(".")[0]
            session = Session(session_name, proxy=proxy_manager.get_proxy())

            if not hasattr(session, 'client'):
                continue

            res.append(session)
        elif file.endswith("journal"):
            try:
                os.remove(f"./sessions/{file}")
            except (PermissionError, FileNotFoundError):
                pass

        if len(res) == limit:
            break
    return res


async def process_sessions(sessions: list[Session], thread: int = 0):
    while sessions:
        # print(len(sessions))
        session = sessions.pop()

        success_authorisation = None
        try:
            result = await session.connect(thread)

            if result is None:
                stats["dead_sessions"] += 1
                continue
            elif not result:
                stats["failed"] += 1
                continue

            if config.WORK_MODE == "CLOSE_ALL":
                await session.close_all_sessions()

            success_authorisation = await session.create_new_session("new_sessions", proxy=proxy_manager.get_proxy())

            if success_authorisation == "wrong_2fa_sessions":
                stats["wrong_2fa_sessions"] += 1
                continue
            elif not success_authorisation:
                stats["failed"] += 1
                continue

            if config.WORK_MODE == "CLOSE_SELF" or config.WORK_MODE == "CLOSE_ALL":
                await session.logout()

            stats["success"] += 1
        except Exception as e:
            session.log(message=f"Неизвестная ошибка - {e}", level='critical')

            if success_authorisation is None:
                stats["failed"] += 1

            with contextlib.suppress(BaseException):
                os.remove(f"./new_sessions/{session.session_name}.session")
        finally:
            await session.disconnect()

        if success_authorisation:
            with contextlib.suppress(BaseException):
                os.remove(f"./sessions/{session.session_name}.session")
            with contextlib.suppress(BaseException):
                os.remove(f"./sessions/{session.session_name}.json")


async def run_main():
    work_dirs = [
        "./sessions",
        "./dead_sessions",
        "./new_sessions",
        "./wrong_2fa_sessions",
    ]
    for work_dir in work_dirs:
        if not os.path.exists(work_dir):
            os.mkdir(work_dir)

    logger.opt(colors=True).info(
        f"<c>Запуск скрипта в режиме <u>{config.WORK_MODE}</u>. Потоков: {config.THREAD_COUNT}</c>")
    sessions = load_sessions()
    logger.info(f"Загружено сессий: {len(sessions)}")
    logger.info(f"Загружено прокси: {proxy_manager.count}")

    await asyncio.gather(
        *[process_sessions(sessions, thread=i + 1) for i in range(config.THREAD_COUNT)]
    )
    logger.opt(colors=True).info(f"<G>Успешно создано сессий: {stats['success']}</G>")
    logger.opt(colors=True).info(f"<R>Не удалось создать сессий: {stats['failed']}</R>")
    logger.opt(colors=True).info(f"<R>Неверный пароль: {stats['wrong_2fa_sessions']}</R>")
    logger.opt(colors=True).info(f"<R>Мертвых: {stats['dead_sessions']}</R>")



