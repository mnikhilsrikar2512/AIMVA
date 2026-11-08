from app import models as M


def test_story_follows_a_picture_into_an_ad_and_a_page_to_its_sales(auth_client, other_client, db):
    me = auth_client.get("/api/auth/me").json()
    uid = (me.get("user") or me)["id"]
    pic = M.Asset(user_id=uid, kind="image", prompt="Diwali offer", model="x", url="/api/files/u/p.jpg", status="done")
    spare = M.Asset(user_id=uid, kind="image", prompt="Unused", model="x", url="/api/files/u/q.jpg", status="done")
    db.add_all([pic, spare])
    db.flush()
    camp = M.Campaign(user_id=uid, platform="meta", name="Diwali", status="active", spend=1200,
                      creative={"headline": "h", "image_url": pic.url})
    site = M.Site(user_id=uid, name="Page", slug="story-page", published=True, visits=90,
                  brief={"hero_image": f"asset:{pic.id}"}, html="<html></html>")
    db.add_all([camp, site])
    db.flush()
    db.add_all([
        M.Lead(user_id=uid, name="A", source="meta", campaign_id=camp.id, stage="won", value=5000),
        M.Lead(user_id=uid, name="B", source="meta", campaign_id=camp.id, stage="new"),
        M.Lead(user_id=uid, name="C", source="website", source_ref="story-page", stage="won", value=3000),
        M.Lead(user_id=uid, name="D", source="whatsapp", stage="new"),
    ])
    db.commit()

    s = auth_client.get("/api/story").json()
    assert s["pictures"] == {"made": 2, "used": 1, "leads": 3, "won": 2, "value": 8000}
    used = {u["kind"]: u for u in s["uses"][str(pic.id)]}
    assert used["campaign"]["leads"] == 2 and used["page"]["won"] == 1
    assert str(spare.id) not in s["uses"]
    assert s["campaigns"]["spend"] == 1200 and s["campaigns"]["leads"] == 2
    assert s["pages"]["visits"] == 90 and s["pages"]["value"] == 3000
    assert s["leads"]["leads"] == 4 and s["leads"]["waiting"] == 2 and s["leads"]["sources"]["whatsapp"] == 1
    assert s["results"]["value"] == 8000 and s["results"]["sales_by_source"][0] == {"source": "meta", "won": 1, "value": 5000}

    theirs = other_client.get("/api/story").json()
    assert theirs["pictures"]["made"] == 0 and theirs["uses"] == {} and theirs["leads"]["leads"] == 0
