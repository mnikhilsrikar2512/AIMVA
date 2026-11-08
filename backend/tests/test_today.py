from datetime import datetime, timedelta

from app.models import Lead, LeadEvent, User


def _lead(db, uid, **kw):
    l = Lead(user_id=uid, **{"name": "Asha", "phone": "+919800000001", "source": "website", "stage": "new", **kw})
    db.add(l)
    db.commit()
    return l


def test_today_counts_what_came_in_since_the_last_visit_and_who_is_waiting(auth_client, db):
    uid = db.query(User).filter_by(email="owner@example.com").one().id
    old = _lead(db, uid, name="Old", phone="+919800000002", created_at=datetime.utcnow() - timedelta(days=3))
    _lead(db, uid, name="Fresh")
    won = _lead(db, uid, name="Buyer", phone="+919800000003", stage="won", value=5000,
                created_at=datetime.utcnow() - timedelta(days=5))
    db.add(LeadEvent(user_id=uid, lead_id=won.id, kind="stage", title="Stage: qualified → won"))
    db.commit()
    since = (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z"
    t = auth_client.get("/api/today", params={"since": since}).json()
    assert t["new"]["count"] == 1 and t["new"]["leads"][0]["name"] == "Fresh"
    assert {l["name"] for l in t["waiting"]["leads"]} == {"Fresh", "Old"}  # new and never answered
    assert t["won"] == {"count": 1, "value": 5000}
    assert old.id in [l["id"] for l in t["waiting"]["leads"]]


def test_today_without_since_looks_back_a_day_and_bad_since_is_ignored(auth_client, db):
    uid = db.query(User).filter_by(email="owner@example.com").one().id
    _lead(db, uid, created_at=datetime.utcnow() - timedelta(hours=20))
    assert auth_client.get("/api/today").json()["new"]["count"] == 1
    assert auth_client.get("/api/today", params={"since": "nonsense"}).json()["new"]["count"] == 1
