from pydantic import BaseModel
from fastapi import APIRouter
from server.session_store import get_or_create_session
from server.response import ok, fail

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    message: str


@router.post("/chat")
async def chat(body: ChatRequest):
    try:
        session = get_or_create_session(body.session_id, body.user_id)
        reply = await session.process_query(body.message)
        return ok({"reply": reply})
    except Exception as e:
        return fail(str(e))
