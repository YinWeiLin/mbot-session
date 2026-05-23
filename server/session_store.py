from typing import Dict
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mbot import MbotSession

# session_id -> MbotSession 实例
_store: Dict[str, MbotSession] = {}


def get_or_create_session(session_id: str, user_id: str) -> MbotSession:
    if session_id not in _store:
        _store[session_id] = MbotSession(user_id=user_id, session_id=session_id)
    return _store[session_id]


def remove_session(session_id: str) -> None:
    _store.pop(session_id, None)
