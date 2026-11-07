"""Live updates: event hub, SSE stream, unseen-lead badge."""
import asyncio
import json
import threading

from sqlalchemy import select

from app import live
from app.models import User
from app.routers.events import stream


def collect(user_id, action, n=1, timeout=3):
    """Subscribe like an open browser tab, run `action` (sync, may publish from any thread), return messages."""
    async def main():
        sub = live.subscribe(user_id)
        try:
            await asyncio.get_running_loop().run_in_executor(None, action)
            out = []
            for _ in range(n):
                out.append(await asyncio.wait_for(sub[1].get(), timeout))
            return out
        finally:
            live.unsubscribe(user_id, sub)
    return asyncio.run(main())


def uid(db, email="owner@example.com"):
    return db.scalar(select(User).where(User.email == email)).id


def test_hub_delivers_across_threads_and_cleans_up(db, auth_client):
    u = uid(db)
    msgs = collect(u, lambda: live.publish(u, "lead", {"x": 1}))
    assert msgs == [{"event": "lead", "data": {"x": 1}}]
    assert live.subscriber_count(u) == 0


def test_publish_without_subscribers_is_a_noop():
    live.publish(424242, "lead", {"x": 1})


def test_new_lead_publishes_created_event_with_unseen_count(db, auth_client):
    u = uid(db)
    [msg] = collect(u, lambda: auth_client.post("/api/leads", json={"name": "Asha", "email": "a@x.com"}))
    assert msg["event"] == "lead"
    d = msg["data"]
    assert d["type"] == "created" and d["lead"]["name"] == "Asha" and d["unseen"] == 1 and d["source"] == "manual"


def test_repeat_contact_publishes_activity_not_created(db, auth_client):
    auth_client.post("/api/leads", json={"phone": "+919876543210"})
    u = uid(db)
    [msg] = collect(u, lambda: auth_client.post("/api/whatsapp/simulate-inbound",
                                               json={"from": "919876543210", "body": "Price?", "name": "Ravi"}))
    assert msg["data"]["type"] == "activity" and msg["data"]["source"] == "whatsapp"
    assert len(auth_client.get("/api/leads").json()) == 1


def test_public_form_lead_reaches_owner_live(db, auth_client, client):
    site = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    auth_client.post(f"/api/sites/{site['id']}/deploy", json={"target": "aimva"})
    u = uid(db)
    [msg] = collect(u, lambda: client.post(f"/api/public/sites/{site['slug']}/lead", data={"phone": "+919999999999"}))
    assert msg["data"]["lead"]["source"] == "website"


def test_events_are_per_user(db, auth_client, other_client):
    mine, theirs = uid(db), uid(db, "intruder@example.com")

    async def main():
        a, b = live.subscribe(mine), live.subscribe(theirs)
        await asyncio.get_running_loop().run_in_executor(None, lambda: auth_client.post("/api/leads", json={"email": "a@x.com"}))
        got = await asyncio.wait_for(a[1].get(), 3)
        await asyncio.sleep(0.1)
        leaked = not b[1].empty()
        live.unsubscribe(mine, a)
        live.unsubscribe(theirs, b)
        return got, leaked

    got, leaked = asyncio.run(main())
    assert got["data"]["lead"]["email"] == "a@x.com" and leaked is False


def test_unseen_and_seen(auth_client, client):
    assert auth_client.get("/api/leads/unseen").json() == {"unseen": 0}
    auth_client.post("/api/leads", json={"email": "a@x.com"})
    auth_client.post("/api/leads", json={"email": "b@x.com"})
    assert auth_client.get("/api/leads/unseen").json() == {"unseen": 2}
    assert auth_client.post("/api/leads/seen").json() == {"unseen": 0}
    assert auth_client.get("/api/leads/unseen").json() == {"unseen": 0}
    auth_client.post("/api/leads", json={"email": "c@x.com"})
    assert auth_client.get("/api/leads/unseen").json() == {"unseen": 1}
    assert client.get("/api/leads/unseen").status_code == 401
    assert client.get("/api/events").status_code == 401


def test_mark_seen_clears_badge_in_other_tabs(db, auth_client):
    u = uid(db)
    [msg] = collect(u, lambda: auth_client.post("/api/leads/seen"))
    assert msg == {"event": "seen", "data": {"unseen": 0}}


class FakeRequest:
    """Stands in for a browser connection that disconnects after `polls` checks."""
    def __init__(self, polls):
        self.polls = polls

    async def is_disconnected(self):
        self.polls -= 1
        return self.polls < 0


def test_sse_stream_format(db, auth_client):
    auth_client.post("/api/leads", json={"email": "a@x.com"})
    user = db.scalar(select(User))

    async def main():
        resp = await stream(FakeRequest(polls=1), user)
        assert resp.media_type == "text/event-stream" and resp.headers["cache-control"] == "no-cache"
        chunks = []
        it = resp.body_iterator.__aiter__()
        chunks.append(await it.__anext__())  # hello
        threading.Thread(target=lambda: live.publish(user.id, "lead", {"type": "created", "unseen": 2})).start()
        chunks.append(await asyncio.wait_for(it.__anext__(), 3))
        async for c in it:  # disconnect ends the stream and unsubscribes
            chunks.append(c)
        return chunks

    chunks = asyncio.run(main())
    assert chunks[0].startswith("retry: 3000\nevent: hello\n")
    assert json.loads(chunks[0].split("data: ")[1]) == {"unseen": 1}
    assert chunks[1] == 'event: lead\ndata: {"type": "created", "unseen": 2}\n\n'
    assert live.subscriber_count(user.id) == 0
