"""Server-Sent Events stream: pushes new-lead notifications to the signed-in user's open tabs."""
import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from .. import live
from ..db import SessionLocal
from ..models import User
from ..security import current_user
from .leads import unseen_count

router = APIRouter(tags=["events"])
HEARTBEAT_S = 15


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/api/events")
async def stream(request: Request, user: User = Depends(current_user)):
    uid = user.id
    with SessionLocal() as db:  # own session: request-scoped ones may close before streaming ends
        unseen = unseen_count(db, uid)

    async def gen():
        sub = live.subscribe(uid)
        try:
            yield "retry: 3000\n" + _sse("hello", {"unseen": unseen})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(sub[1].get(), timeout=HEARTBEAT_S)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # keeps proxies from closing an idle connection
                    continue
                yield _sse(msg["event"], msg["data"])
        finally:
            live.unsubscribe(uid, sub)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
