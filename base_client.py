import abc
import re
import asyncio
import collections
import logging
import platform
import time
import typing
import datetime
from telethon import TelegramClient as TC
from telethon import version, helpers, __name__ as __base_name__
from telethon.crypto import rsa
from telethon.extensions import markdown
from telethon.network import MTProtoSender, Connection, ConnectionTcpFull, TcpMTProxy
from telethon.sessions import Session, SQLiteSession, MemorySession
from telethon.tl import functions, types
from telethon.tl.alltlobjects import LAYER
from telethon._updates import MessageBox, EntityCache as MbEntityCache, SessionState, ChannelState, Entity, EntityType


DEFAULT_DC_ID = 2
DEFAULT_IPV4_IP = '149.154.167.51'
DEFAULT_IPV6_IP = '2001:67c:4e8:f002::a'
DEFAULT_PORT = 443

_base_log = logging.getLogger(__base_name__)

# In seconds, how long to wait before disconnecting a exported sender.
_DISCONNECT_EXPORTED_AFTER = 60


class TelegramClient(TC):
    def __init__(
            self: 'TelegramClient',
            session: 'typing.Union[str, Session]',
            api_id: int,
            api_hash: str,
            *,
            connection: 'typing.Type[Connection]' = ConnectionTcpFull,
            use_ipv6: bool = False,
            proxy: typing.Union[tuple, dict] = None,
            local_addr: typing.Union[str, tuple] = None,
            timeout: int = 10,
            request_retries: int = 5,
            connection_retries: int = 5,
            retry_delay: int = 1,
            auto_reconnect: bool = True,
            sequential_updates: bool = False,
            flood_sleep_threshold: int = 60,
            raise_last_call_error: bool = False,
            device_model: str = None,
            system_version: str = None,
            app_version: str = None,
            lang_code: str = 'en',
            lang_pack: str = 'android',  #только для оф версий!!!!
            system_lang_code: str = 'en',
            base_logger: typing.Union[str, logging.Logger] = None,
            receive_updates: bool = True,
            catch_up: bool = False,
            entity_cache_limit: int = 5000
    ):
        if not api_id or not api_hash:
            raise ValueError(
                "Your API ID or Hash cannot be empty or None. "
                "Refer to telethon.rtfd.io for more information.")

        self._use_ipv6 = use_ipv6

        if isinstance(base_logger, str):
            base_logger = logging.getLogger(base_logger)
        elif not isinstance(base_logger, logging.Logger):
            base_logger = _base_log

        class _Loggers(dict):
            def __missing__(self, key):
                if key.startswith("telethon."):
                    key = key.split('.', maxsplit=1)[1]

                return base_logger.getChild(key)

        self._log = _Loggers()

        # Determine what session object we have
        if isinstance(session, str) or session is None:
            try:
                session = SQLiteSession(session)
            except ImportError:
                import warnings
                warnings.warn(
                    'The sqlite3 module is not available under this '
                    'Python installation and no custom session '
                    'instance was given; using MemorySession.\n'
                    'You will need to re-login every time unless '
                    'you use another session storage'
                )
                session = MemorySession()
        elif not isinstance(session, Session):
            raise TypeError(
                'The given session must be a str or a Session instance.'
            )

        # ':' in session.server_address is True if it's an IPv6 address
        if (not session.server_address or
                (':' in session.server_address) != use_ipv6):
            session.set_dc(
                DEFAULT_DC_ID,
                DEFAULT_IPV6_IP if self._use_ipv6 else DEFAULT_IPV4_IP,
                DEFAULT_PORT
            )

        self.flood_sleep_threshold = flood_sleep_threshold

        # TODO Use AsyncClassWrapper(session)
        # ChatGetter and SenderGetter can use the in-memory _mb_entity_cache
        # to avoid network access and the need for await in session files.
        #
        # The session files only wants the entities to persist
        # them to disk, and to save additional useful information.
        # TODO Session should probably return all cached
        #      info of entities, not just the input versions
        self.session = session
        self.api_id = int(api_id)
        self.api_hash = api_hash

        # Current proxy implementation requires `sock_connect`, and some
        # event loops lack this method. If the current loop is missing it,
        # bail out early and suggest an alternative.
        #
        # TODO A better fix is obviously avoiding the use of `sock_connect`
        #
        # See https://github.com/LonamiWebs/Telethon/issues/1337 for details.
        if not callable(getattr(self.loop, 'sock_connect', None)):
            raise TypeError(
                'Event loop of type {} lacks `sock_connect`, which is needed to use proxies.\n\n'
                'Change the event loop in use to use proxies:\n'
                '# https://github.com/LonamiWebs/Telethon/issues/1337\n'
                'import asyncio\n'
                'asyncio.set_event_loop(asyncio.SelectorEventLoop())'.format(
                    self.loop.__class__.__name__
                )
            )

        if local_addr is not None:
            if use_ipv6 is False and ':' in local_addr:
                raise TypeError(
                    'A local IPv6 address must only be used with `use_ipv6=True`.'
                )
            elif use_ipv6 is True and ':' not in local_addr:
                raise TypeError(
                    '`use_ipv6=True` must only be used with a local IPv6 address.'
                )

        self._raise_last_call_error = raise_last_call_error

        self._request_retries = request_retries
        self._connection_retries = connection_retries
        self._retry_delay = retry_delay or 0
        self._proxy = proxy
        self._local_addr = local_addr
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect

        assert isinstance(connection, type)
        self._connection = connection
        init_proxy = None if not issubclass(connection, TcpMTProxy) else \
            types.InputClientProxy(*connection.address_info(proxy))

        # Used on connection. Capture the variables in a lambda since
        # exporting clients need to create this InvokeWithLayerRequest.
        system = platform.uname()

        if system.machine in ('x86_64', 'AMD64'):
            default_device_model = 'PC 64bit'
        elif system.machine in ('i386', 'i686', 'x86'):
            default_device_model = 'PC 32bit'
        else:
            default_device_model = system.machine
        default_system_version = re.sub(r'-.+', '', system.release)

        self._init_request = functions.InitConnectionRequest(
            api_id=self.api_id,
            device_model=device_model or default_device_model or 'Unknown',
            system_version=system_version or default_system_version or '1.0',
            app_version=app_version or self.__version__,
            lang_code=lang_code,
            system_lang_code=system_lang_code,
            lang_pack='' if lang_pack is None else lang_pack,  # "langPacks are for official apps only"
            query=None,
            proxy=init_proxy
        )

        # Remember flood-waited requests to avoid making them again
        self._flood_waited_requests = {}

        # Cache ``{dc_id: (_ExportState, MTProtoSender)}`` for all borrowed senders
        self._borrowed_senders = {}
        self._borrow_sender_lock = asyncio.Lock()

        self._loop = None  # only used as a sanity check
        self._updates_error = None
        self._updates_handle = None
        self._keepalive_handle = None
        self._last_request = time.time()
        self._no_updates = not receive_updates

        # Used for non-sequential updates, in order to terminate all pending tasks on disconnect.
        self._sequential_updates = sequential_updates
        self._event_handler_tasks = set()

        self._authorized = None  # None = unknown, False = no, True = yes

        # Some further state for subclasses
        self._event_builders = []

        # {chat_id: {Conversation}}
        self._conversations = collections.defaultdict(set)

        # Hack to workaround the fact Telegram may send album updates as
        # different Updates when being sent from a different data center.
        # {grouped_id: AlbumHack}
        #
        # FIXME: We don't bother cleaning this up because it's not really
        #        worth it, albums are pretty rare and this only holds them
        #        for a second at most.
        self._albums = {}

        # Default parse mode
        self._parse_mode = markdown

        # Some fields to easy signing in. Let {phone: hash} be
        # a dictionary because the user may change their mind.
        self._phone_code_hash = {}
        self._phone = None
        self._tos = None

        # A place to store if channels are a megagroup or not (see `edit_admin`)
        self._megagroup_cache = {}

        # This is backported from v2 in a very ad-hoc way just to get proper update handling
        self._catch_up = catch_up
        self._updates_queue = asyncio.Queue()
        self._message_box = MessageBox(self._log['messagebox'])
        self._mb_entity_cache = MbEntityCache()  # required for proper update handling (to know when to getDifference)
        self._entity_cache_limit = entity_cache_limit

        self._sender = MTProtoSender(
            self.session.auth_key,
            loggers=self._log,
            retries=self._connection_retries,
            delay=self._retry_delay,
            auto_reconnect=self._auto_reconnect,
            connect_timeout=self._timeout,
            auth_key_callback=self._auth_key_callback,
            updates_queue=self._updates_queue,
            auto_reconnect_callback=self._handle_auto_reconnect
        )
