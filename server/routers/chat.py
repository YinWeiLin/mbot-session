from pydantic import BaseModel
from fastapi import APIRouter
from server.session_store import create_session, get_session
from server.response import ok, fail

router = APIRouter()


class StartRequest(BaseModel):
    user_id: str = "default_user"
    message: str


class ChatRequest(BaseModel):
    ssid: str
    message: str


@router.post("/session/start")
async def session_start(body: StartRequest):
    try:
        session = await create_session(body.user_id)
        reply = await session.process_query(body.message)
        return ok({"ssid": session.session_id, "reply": reply})
    except Exception as e:
        return fail(str(e))


@router.post("/chat")
async def chat(body: ChatRequest):
    session = get_session(body.ssid)
    if session is None:
        return fail("会话不存在，请先调用 /session/start")
    try:
        reply = await session.process_query(body.message)
        return ok({"reply": reply})
    except Exception as e:
        return fail(str(e))
