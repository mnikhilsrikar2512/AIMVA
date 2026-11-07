"""Google Ads and LinkedIn Ads: publish paused, switch on/off, sync results (HTTP mocked)."""
import json

import httpx
import pytest

from app import ad_platforms
from app.config import settings

from .helpers import connect
from .test_engage import new_campaign

G = ad_platforms.GOOGLE_ADS
LI = ad_platforms.LINKEDIN


@pytest.fixture
def google(db, monkeypatch):
    monkeypatch.setattr(settings, "google_ads_developer_token", "DEVTOKEN")
    connect(db, "owner@example.com", "google", {"access_token": "gtok"},
            {"ads_customer_id": "123-456-7890", "ads_login_customer_id": "999-000-1111"})


@pytest.fixture
def linkedin(db):
    connect(db, "owner@example.com", "linkedin", {"access_token": "ltok"},
            {"ad_account_id": "urn:li:sponsoredAccount:5001", "currency": "INR", "default_geo_urns": ["urn:li:geo:102713980"]})


def test_google_publish_creates_a_paused_search_campaign(auth_client, google, mock_http):
    budget = mock_http.post(f"{G}/customers/1234567890/campaignBudgets:mutate").respond(
        json={"results": [{"resourceName": "customers/1234567890/campaignBudgets/77"}]})
    camp = mock_http.post(f"{G}/customers/1234567890/campaigns:mutate").respond(
        json={"results": [{"resourceName": "customers/1234567890/campaigns/88"}]})
    c = new_campaign(auth_client, platform="google")
    p = auth_client.post(f"/api/campaigns/{c['id']}/publish").json()
    assert p["external_id"] == "customers/1234567890/campaigns/88" and p["status"] == "paused"
    req = budget.calls[0].request
    assert req.headers["developer-token"] == "DEVTOKEN" and req.headers["login-customer-id"] == "9990001111"
    assert req.headers["authorization"] == "Bearer gtok"
    assert json.loads(req.content)["operations"][0]["create"]["amountMicros"] == "25000000"
    create = json.loads(camp.calls[0].request.content)["operations"][0]["create"]
    assert create["status"] == "PAUSED" and create["campaignBudget"].endswith("/77") and create["advertisingChannelType"] == "SEARCH"
    assert auth_client.post(f"/api/campaigns/{c['id']}/publish").status_code == 400  # not twice


def test_google_turn_on_and_sync(auth_client, google, mock_http):
    mock_http.post(f"{G}/customers/1234567890/campaignBudgets:mutate").respond(json={"results": [{"resourceName": "b/1"}]})
    mut = mock_http.post(f"{G}/customers/1234567890/campaigns:mutate").respond(
        json={"results": [{"resourceName": "customers/1234567890/campaigns/88"}]})
    c = new_campaign(auth_client, platform="google")
    auth_client.post(f"/api/campaigns/{c['id']}/publish")
    auth_client.patch(f"/api/campaigns/{c['id']}", json={"status": "active"})
    upd = json.loads(mut.calls[-1].request.content)["operations"][0]
    assert upd["update"]["status"] == "ENABLED" and upd["updateMask"] == "status"
    search = mock_http.post(f"{G}/customers/1234567890/googleAds:search").respond(json={"results": [
        {"metrics": {"costMicros": "12500000", "impressions": "1000", "clicks": "40"}},
        {"metrics": {"costMicros": "2500000", "impressions": "200", "clicks": "5"}}]})
    s = auth_client.post(f"/api/campaigns/{c['id']}/sync").json()
    assert (s["spend"], s["impressions"], s["clicks"]) == (15.0, 1200, 45)
    assert "campaign.id = 88" in json.loads(search.calls[0].request.content)["query"]


def test_google_needs_token_customer_and_budget(auth_client, db, mock_http, monkeypatch):
    connect(db, "owner@example.com", "google", {"access_token": "gtok"})
    c = new_campaign(auth_client, platform="google")
    assert "developer token" in auth_client.post(f"/api/campaigns/{c['id']}/publish").json()["detail"]
    monkeypatch.setattr(settings, "google_ads_developer_token", "DEVTOKEN")
    assert "customer ID" in auth_client.post(f"/api/campaigns/{c['id']}/publish").json()["detail"]
    auth_client.patch("/api/integrations/google/meta", json={"meta": {"ads_customer_id": "1234567890"}})
    zero = new_campaign(auth_client, platform="google", daily_budget=0)
    assert "budget" in auth_client.post(f"/api/campaigns/{zero['id']}/publish").json()["detail"]


def test_google_refusal_is_shown(auth_client, google, mock_http):
    mock_http.post(f"{G}/customers/1234567890/campaignBudgets:mutate").respond(
        403, json={"error": {"message": "The developer token is only approved for test accounts."}})
    c = new_campaign(auth_client, platform="google")
    r = auth_client.post(f"/api/campaigns/{c['id']}/publish")
    assert r.status_code == 502 and "only approved for test accounts" in r.json()["detail"]
    assert auth_client.get("/api/campaigns").json()[0]["status"] == "draft"


def test_linkedin_publish_as_draft_then_sync(auth_client, linkedin, mock_http):
    group = mock_http.post(f"{LI}/adAccounts/5001/adCampaignGroups").respond(201, headers={"x-restli-id": "601"})
    camp = mock_http.post(f"{LI}/adAccounts/5001/adCampaigns").respond(201, headers={"x-restli-id": "701"})
    c = new_campaign(auth_client, platform="linkedin")
    p = auth_client.post(f"/api/campaigns/{c['id']}/publish").json()
    assert p["external_id"] == "701" and p["status"] == "paused"
    assert group.calls[0].request.headers["linkedin-version"] == ad_platforms.LINKEDIN_VERSION
    body = json.loads(camp.calls[0].request.content)
    assert body["status"] == "DRAFT" and body["campaignGroup"] == "urn:li:sponsoredCampaignGroup:601"
    assert body["dailyBudget"] == {"amount": "25.00", "currencyCode": "INR"} and body["objectiveType"] == "LEAD_GENERATION"
    assert body["targetingCriteria"]["include"]["and"][0]["or"]["urn:li:adTargetingFacet:locations"] == ["urn:li:geo:102713980"]

    stats = mock_http.get(url__startswith=f"{LI}/adAnalytics").respond(json={"elements": [
        {"impressions": 500, "clicks": 12, "costInLocalCurrency": "830.50"}]})
    s = auth_client.post(f"/api/campaigns/{c['id']}/sync").json()
    assert (s["spend"], s["impressions"], s["clicks"]) == (830.5, 500, 12)
    assert "urn%3Ali%3AsponsoredCampaign%3A701" in str(stats.calls[0].request.url)

    pause = mock_http.post(f"{LI}/adAccounts/5001/adCampaigns/701").respond(204)
    auth_client.patch(f"/api/campaigns/{c['id']}", json={"status": "active"})
    assert json.loads(pause.calls[0].request.content) == {"patch": {"$set": {"status": "ACTIVE"}}}
    assert pause.calls[0].request.headers["x-restli-method"] == "PARTIAL_UPDATE"


def test_linkedin_needs_account_and_location(auth_client, db):
    connect(db, "owner@example.com", "linkedin", {"access_token": "ltok"}, {"ad_account_id": "5001"})
    c = new_campaign(auth_client, platform="linkedin")
    assert "location" in auth_client.post(f"/api/campaigns/{c['id']}/publish").json()["detail"]
