"""Builds the public site's sample pages with the real page builder (template mode, no AI, no keys).

Run from backend/:  python -m scripts.landing_samples
Then take the screenshots:  node ../frontend/scripts/sample-shots.cjs  (see docs/LANDING.md)
"""
import re
from pathlib import Path

from app.routers.sites import Brief, build_html

OUT = (Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples")
# Example businesses. Keep them fictional: no real brand names.
briefs = {
 "dental": Brief(business="Smile Studio Dental", industry="Dental clinic", headline="Painless root canal in one visit",
   subheadline="Gentle care in Jubilee Hills, Hyderabad. Same-week appointments.", offer="Free check-up this month",
   cta="Book a free check-up", features=["Painless root canal", "Clear aligners", "Kids' dentistry", "Open till 9 pm"],
   primary="#0b6b67", accent="#f4a21c", layout="split", look="modern", page_type="service", use_ai=False,
   sections=["features","testimonials","faq"], faqs=[{"q":"Do you take walk-ins?","a":"Yes, until 8 pm."}],
   testimonials=[{"name":"Ravi K.","quote":"No pain at all. Done in one visit.","role":"Patient"}]),
 "coaching": Brief(business="Vidya Coaching Centre", industry="Coaching institute", headline="JEE and NEET coaching that fits after school",
   subheadline="Small batches of 20 in Vijayawada. Weekly tests, doubt sessions in Telugu or English.", offer="Free demo class",
   cta="Book a demo class", features=["Batches of 20", "Weekly mock tests", "Telugu or English", "Evening timings"],
   primary="#1e3a8a", accent="#f59e0b", layout="bento", look="bold", page_type="service", use_ai=False, sections=["features","pricing"],
   pricing=[{"name":"Foundation","price":"₹2,500/mo","features":["Class 9-10","3 days a week"]},{"name":"JEE/NEET","price":"₹4,500/mo","features":["Class 11-12","6 days a week"]}]),
 "homes": Brief(business="Skyline Homes", industry="Real estate", headline="2 & 3 BHK homes near the metro",
   subheadline="RERA approved. Possession December 2027. Whitefield, Bengaluru.", offer="Free site visit this weekend",
   cta="Book a site visit", features=["Clubhouse", "Swimming pool", "Kids play area", "24x7 security", "Power backup"],
   primary="#0b3d2e", accent="#c9a45c", layout="showcase", look="elegant", page_type="real_estate", use_ai=False),
 "cafe": Brief(business="Annapurna Tiffins", industry="Cafe", headline="Fresh filter coffee and tiffin from 7 am",
   subheadline="Idli, dosa and pongal in Indiranagar. Order on WhatsApp for pickup.", offer="10% off your first order",
   cta="Order on WhatsApp", features=["Filter coffee", "Ghee dosa", "Open 7 am", "Pickup in 10 min"],
   primary="#7c2d12", accent="#f4a21c", layout="centered", look="playful", page_type="restaurant", use_ai=False),
}


# Forms on the samples never send: the guard stops the submit and the bar says why.
GUARD = """<script>/* AIMVA sample: forms here don't send anything */
document.addEventListener('submit',function(e){e.preventDefault();e.stopImmediatePropagation();
var b=document.getElementById('aimva-sample');if(b){b.textContent='This is a sample page, so nothing was sent. Your own page sends leads straight to AIMVA.';b.style.background='#a35700';}},true);
</script>"""
BAR = """<div id="aimva-sample" style="position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:2147483647;max-width:calc(100% - 32px);background:#0f2b2d;color:#fff;font:500 13px/1.4 system-ui,sans-serif;padding:10px 16px;border-radius:999px;box-shadow:0 10px 30px rgba(0,0,0,.25);text-align:center">Sample page made with AIMVA's page builder · <a href="/" style="color:#f4a21c;font-weight:600">Back to AIMVA</a></div>"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for key, brief in briefs.items():
        html, how = build_html(brief, key)
        html = html.replace("<head>", "<head>" + GUARD + '<meta name="robots" content="noindex">', 1)
        html = re.sub(r"</body>", lambda _: BAR + "</body>", html, count=1)
        (OUT / f"{key}.html").write_text(html)
        print(key, how, len(html))


if __name__ == "__main__":
    main()
