# Настройки сессий
SETTINGS = {
    "attempts_count": 5,  # Количество попыток для подключения аккаунта
    "attempt_sleep": 3,  # Ожидание между попытками
}

# Режим работы:
# "CLOSE_ALL" - Закрывать все сессии
# "CLOSE_SELF" - Закрывать только себя
# "CLOSE_NONE" - Ничего не закрывать
WORK_MODE = "CLOSE_SELF"
THREAD_COUNT = 50  # Количество потоков

API_PACKS = {
    4: 'android',
    5: 'android',
    6: 'android',
    8: 'ios',
    2834: 'macos',
    2040: 'tdesktop',
    17349: 'tdesktop',
    21724: 'android',
    2496: ''
}

# Проверка настроек
assert WORK_MODE in {"CLOSE_ALL", "CLOSE_SELF", "CLOSE_NONE"}, "Установлен неверный режим работы"
