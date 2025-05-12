import textwrap


class InteractiveAuthRequired(Exception):
    """It is being raised by Telethon, if phone is required"""

    def __init__(self):
        super().__init__(textwrap.dedent(self.__class__.__name__))


class SessionFileNotFound(Exception):
    """Raises when .session file not found in ./sessions directory"""

    def __int__(self):
        super().__init__(textwrap.dedent(f"{self.__class__.__name__} ({self.__class__.__doc__})"))
