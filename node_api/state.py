from collections import deque
from os import environ
from threading import Lock

from asgiref.sync import async_to_sync

from core import Database

_db = None
_db_lock = Lock()

started = False
is_syncing = False
self_url = None
transactions_cache = deque(maxlen=100)
last_pending_transactions_clean = [0]


def get_db():
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                Database.credentials = {
                    "user": environ.get("DENARO_DATABASE_USER", "postgres"),
                    "password": environ.get("DENARO_DATABASE_PASSWORD", "root"),
                    "database": environ.get("DENARO_DATABASE_NAME", "denaro2"),
                    "host": environ.get("DENARO_DATABASE_HOST", None),
                }
                _db = async_to_sync(Database.create)(**Database.credentials)
    return _db
