"""Publishing and reporting for Google Ads and LinkedIn Ads.

Both platforms only let approved apps call these APIs:
- Google Ads: a developer token with Basic (or Standard) access, GOOGLE_ADS_DEVELOPER_TOKEN, plus the user's OAuth.
- LinkedIn: the Advertising API product on the LinkedIn app (Marketing Developer Platform), plus the user's OAuth.
Until then the platforms refuse the calls and the user sees their error. The code follows the documented REST APIs
and is tested against recorded shapes; it has not run against a live account yet.

Safety rule, same as Meta: AIMVA never starts spending. Campaigns are created paused (Google) or as drafts (LinkedIn),
and the owner switches them on in the platform after adding ads.
"""
import os
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .models import Campaign
from .services import get_integration

GOOGLE_ADS_VERSION = os.getenv("GOOGLE_ADS_API_VERSION", "v21").strip()
GOOGLE_ADS = f"https://googleads.googleapis.com/{GOOGLE_ADS_VERSION}"
LINKEDIN_VERSION = os.getenv("LINKEDIN_API_VERSION", "202510").strip()  # YYYYMM; LinkedIn retires versions after a year
LINKEDIN = "https://api.linkedin.com/rest"


def _digits(v) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def _error(platform: str, r: httpx.Response) -> HTTPException:
    try:
        data = r.json()
        msg = (data.get("error") or {}).get("message") or data.get("message") or r.text
    except ValueError:
        msg = r.text
    return HTTPException(502, f"{platform} refused the request: {str(msg)[:300]}")


# ---- Google Ads -------------------------------------------------------------------------------------------
def _google(db: Session, user_id: int, token: Optional[str]) -> tuple:
    if not settings.google_ads_developer_token:
        raise HTTPException(400, "Google Ads publishing needs AIMVA's Google Ads developer token (GOOGLE_ADS_DEVELOPER_TOKEN). "
                                 "See docs/INTEGRATIONS.md.")
    integ = get_integration(db, user_id, "google")
    meta = (integ.meta or {}) if integ else {}
    customer = _digits(meta.get("ads_customer_id"))
    if not token or not customer:
        raise HTTPException(400, "Connect Google and enter your Google Ads customer ID (10 digits, top right in Google Ads) first.")
    headers = {"Authorization": f"Bearer {token}", "developer-token": settings.google_ads_developer_token}
    if _digits(meta.get("ads_login_customer_id")):  # when access goes through a manager (MCC) account
        headers["login-customer-id"] = _digits(meta["ads_login_customer_id"])
    return customer, headers


def google_publish(db: Session, c: Campaign, token: Optional[str]) -> None:
    customer, headers = _google(db, c.user_id, token)
    if c.daily_budget <= 0:
        raise HTTPException(400, "Set a daily budget before publishing to Google Ads.")
    base = f"{GOOGLE_ADS}/customers/{customer}"
    r = httpx.post(f"{base}/campaignBudgets:mutate", headers=headers, timeout=30, json={"operations": [{"create": {
        "name": f"{c.name} budget #{c.id}", "amountMicros": str(int(round(c.daily_budget * 1_000_000))),
        "deliveryMethod": "STANDARD", "explicitlyShared": False}}]})
    if r.status_code >= 400:
        raise _error("Google Ads", r)
    budget = r.json()["results"][0]["resourceName"]
    r = httpx.post(f"{base}/campaigns:mutate", headers=headers, timeout=30, json={"operations": [{"create": {
        "name": c.name, "status": "PAUSED", "advertisingChannelType": "SEARCH", "campaignBudget": budget,
        "maximizeConversions": {},
        "networkSettings": {"targetGoogleSearch": True, "targetSearchNetwork": True, "targetContentNetwork": False},
        "containsEuPoliticalAdvertising": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING"}}]})
    if r.status_code >= 400:
        raise _error("Google Ads", r)
    c.external_id, c.status = r.json()["results"][0]["resourceName"], "paused"


def google_set_status(db: Session, c: Campaign, token: Optional[str], status: str) -> None:
    customer, headers = _google(db, c.user_id, token)
    r = httpx.post(f"{GOOGLE_ADS}/customers/{customer}/campaigns:mutate", headers=headers, timeout=30, json={
        "operations": [{"update": {"resourceName": c.external_id, "status": "ENABLED" if status == "active" else "PAUSED"},
                        "updateMask": "status"}]})
    if r.status_code >= 400:
        raise _error("Google Ads", r)


def google_sync(db: Session, c: Campaign, token: Optional[str]) -> None:
    customer, headers = _google(db, c.user_id, token)
    cid = c.external_id.rsplit("/", 1)[-1]
    if not cid.isdigit():
        raise HTTPException(400, "This campaign has no Google Ads ID yet. Publish it first.")
    from .models import utcnow
    today = utcnow().date().isoformat()
    # Lifetime totals (AIMVA stores cumulative numbers and snapshots them per day to work out trends).
    r = httpx.post(f"{GOOGLE_ADS}/customers/{customer}/googleAds:search", headers=headers, timeout=30, json={
        "query": "SELECT metrics.cost_micros, metrics.impressions, metrics.clicks FROM campaign "
                 f"WHERE campaign.id = {cid} AND segments.date BETWEEN '2020-01-01' AND '{today}'"})
    if r.status_code >= 400:
        raise _error("Google Ads", r)
    rows = [row.get("metrics", {}) for row in r.json().get("results", [])]
    c.spend = round(sum(int(m.get("costMicros", 0)) for m in rows) / 1_000_000, 2)
    c.impressions = sum(int(m.get("impressions", 0)) for m in rows)
    c.clicks = sum(int(m.get("clicks", 0)) for m in rows)


# ---- LinkedIn Ads -----------------------------------------------------------------------------------------
def _linkedin(db: Session, user_id: int, token: Optional[str]) -> tuple:
    integ = get_integration(db, user_id, "linkedin")
    meta = (integ.meta or {}) if integ else {}
    account = _digits(meta.get("ad_account_id"))
    if not token or not account:
        raise HTTPException(400, "Connect LinkedIn and enter your ad account ID (Campaign Manager → Account) first.")
    headers = {"Authorization": f"Bearer {token}", "LinkedIn-Version": LINKEDIN_VERSION,
               "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    return account, headers, meta


def _created_id(r: httpx.Response) -> str:
    return r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id") or str((r.json() if r.content else {}).get("id", ""))


def linkedin_publish(db: Session, c: Campaign, token: Optional[str]) -> None:
    account, headers, meta = _linkedin(db, c.user_id, token)
    if c.daily_budget <= 0:
        raise HTTPException(400, "Set a daily budget before publishing to LinkedIn.")
    geos = (c.targeting or {}).get("linkedin_geo_urns") or meta.get("default_geo_urns") or []
    if not geos:
        raise HTTPException(400, "Pick at least one LinkedIn location for this campaign (targeting.linkedin_geo_urns).")
    acct_urn = f"urn:li:sponsoredAccount:{account}"
    r = httpx.post(f"{LINKEDIN}/adAccounts/{account}/adCampaignGroups", headers=headers, timeout=30, json={
        "account": acct_urn, "name": f"{c.name} (AIMVA)", "status": "DRAFT",
        "runSchedule": {"start": 0}})
    if r.status_code >= 400:
        raise _error("LinkedIn", r)
    group = _created_id(r)
    r = httpx.post(f"{LINKEDIN}/adAccounts/{account}/adCampaigns", headers=headers, timeout=30, json={
        "account": acct_urn, "campaignGroup": f"urn:li:sponsoredCampaignGroup:{group}", "name": c.name,
        "type": "SPONSORED_UPDATES", "costType": "CPM", "status": "DRAFT",
        "objectiveType": "LEAD_GENERATION" if c.objective == "leads" else "WEBSITE_VISIT",
        "dailyBudget": {"amount": f"{c.daily_budget:.2f}", "currencyCode": meta.get("currency", "INR")},
        "locale": {"country": meta.get("locale_country", "IN"), "language": "en"},
        "offsiteDeliveryEnabled": False, "politicalIntent": "NOT_POLITICAL",
        "targetingCriteria": {"include": {"and": [{"or": {"urn:li:adTargetingFacet:locations": list(geos)}}]}}})
    if r.status_code >= 400:
        raise _error("LinkedIn", r)
    c.external_id, c.status = _created_id(r), "paused"


def linkedin_set_status(db: Session, c: Campaign, token: Optional[str], status: str) -> None:
    account, headers, _ = _linkedin(db, c.user_id, token)
    r = httpx.post(f"{LINKEDIN}/adAccounts/{account}/adCampaigns/{c.external_id}", timeout=30,
                   headers={**headers, "X-RestLi-Method": "PARTIAL_UPDATE"},
                   json={"patch": {"$set": {"status": "ACTIVE" if status == "active" else "PAUSED"}}})
    if r.status_code >= 400:
        raise _error("LinkedIn", r)


def linkedin_sync(db: Session, c: Campaign, token: Optional[str]) -> None:
    _, headers, _ = _linkedin(db, c.user_id, token)
    urn = quote(f"urn:li:sponsoredCampaign:{c.external_id}", safe="")
    url = (f"{LINKEDIN}/adAnalytics?q=analytics&pivot=CAMPAIGN&timeGranularity=ALL"
           f"&dateRange=(start:(year:2020,month:1,day:1))&campaigns=List({urn})"
           f"&fields=impressions,clicks,costInLocalCurrency")
    r = httpx.get(url, headers={k: v for k, v in headers.items() if k != "Content-Type"}, timeout=30)
    if r.status_code >= 400:
        raise _error("LinkedIn", r)
    rows = r.json().get("elements", [])
    c.spend = round(sum(float(e.get("costInLocalCurrency") or 0) for e in rows), 2)
    c.impressions = sum(int(e.get("impressions") or 0) for e in rows)
    c.clicks = sum(int(e.get("clicks") or 0) for e in rows)
