from typing import Dict
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mbot import MbotSession

_store: Dict[str, MbotSession] = {}


async def create_session(user_id: str = "default_user") -> MbotSession:
    ssid = str(uuid.uuid4())[:8]
    session = MbotSession(user_id=user_id, session_id=ssid)
    await session.init()
    _store[ssid] = session
    return session


def get_session(ssid: str) -> MbotSession | None:
    return _store.get(ssid)


def remove_session(ssid: str) -> None:
    _store.pop(ssid, None)
