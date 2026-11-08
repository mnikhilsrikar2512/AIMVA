from app import alerts
from tests.test_agents import lead_form, publish


def test_owner_is_emailed_the_moment_a_lead_arrives(auth_client, client, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html="": sent.append((to, subject, text, html)) or True)
    s = publish(auth_client)
    lead_form(client, s["slug"], message="Do you have 3 BHK on a high floor?")
    assert len(sent) == 1
    to, subject, text, html = sent[0]
    assert to == "owner@example.com" and subject.startswith("New lead: Ravi Kumar")
    assert "high floor" in text and "https://wa.me/919812345678?text=Hi%20Ravi" in text and "/app/leads?lead=" in text
    assert "Reply on WhatsApp" in html

    assert auth_client.put("/api/agents/lead_alerts", json={"enabled": False}).status_code == 200
    lead_form(client, s["slug"], name="Sita", phone="+919800000001")
    assert len(sent) == 1  # switched off


def test_alerts_are_capped_and_skip_leads_you_typed_in(auth_client, client, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send_email", lambda *a, **k: sent.append(a) or True)
    auth_client.post("/api/leads", json={"name": "Typed in", "phone": "+919800000002"})
    assert sent == []
    s = publish(auth_client)
    for i in range(alerts.ALERTS_PER_HOUR + 3):
        lead_form(client, s["slug"], name=f"P{i}", phone=f"+9198000001{i:02d}")
    assert len(sent) == alerts.ALERTS_PER_HOUR


def test_whatsapp_link_adds_india_code():
    assert alerts.wa_link("98123 45678", "Hi").startswith("https://wa.me/919812345678?text=Hi")
    assert alerts.wa_link("123", "Hi") == ""
