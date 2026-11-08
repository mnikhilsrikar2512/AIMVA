"""Calling hours: automated calls only between 9 am and 9 pm in the lead's own time (TRAI TCCCPR, India).

A call asked for outside those hours is not dropped. It is saved as a "scheduled" call and the agent
scheduler places it when the lead's window next opens (see voice.place_due_calls).

The lead's time comes from the phone number's country code. Only countries with a single time zone and
no daylight saving are mapped, so the offset is always right; any other number uses the business time
zone (TZ_OFFSET_MINUTES, IST by default). That keeps the rule correct for Indian leads, which is what
TRAI covers, without needing a time zone database on the server.
"""
from datetime import datetime, timedelta
from typing import Optional

from .config import settings
from .models import utcnow

START_HOUR = 9   # first call may start at 09:00
END_HOUR = 21    # last call must start before 21:00
STALE_AFTER = timedelta(days=2)  # a deferred call older than this is not placed any more (the moment has passed)

# Country calling code -> UTC offset in minutes. Single zone, no daylight saving only.
_OFFSETS = {
    "91": 330,    # India
    "880": 360,   # Bangladesh
    "977": 345,   # Nepal
    "94": 330,    # Sri Lanka
    "92": 300,    # Pakistan
    "975": 360,   # Bhutan
    "960": 300,   # Maldives
    "971": 240,   # UAE
    "968": 240,   # Oman
    "966": 180,   # Saudi Arabia
    "974": 180,   # Qatar
    "965": 180,   # Kuwait
    "973": 180,   # Bahrain
    "65": 480,    # Singapore
    "60": 480,    # Malaysia
    "63": 480,    # Philippines
    "86": 480,    # China
    "852": 480,   # Hong Kong
    "81": 540,    # Japan
    "82": 540,    # South Korea
    "66": 420,    # Thailand
    "27": 120,    # South Africa
    "254": 180,   # Kenya
    "234": 60,    # Nigeria
}


def now() -> datetime:
    """Naive UTC, like the rest of the database. Tests replace this to pin the clock."""
    return utcnow()


def offset_minutes(number: str) -> int:
    """The lead's UTC offset from their number (+91... -> IST). Unknown or local numbers use the business time zone."""
    raw = (number or "").strip()
    if raw.startswith("+"):
        digits = "".join(ch for ch in raw if ch.isdigit())
        for n in (3, 2, 1):
            if digits[:n] in _OFFSETS:
                return _OFFSETS[digits[:n]]
    return settings.tz_offset_minutes


def is_open(number: str, at: Optional[datetime] = None) -> bool:
    local = (at or now()) + timedelta(minutes=offset_minutes(number))
    return START_HOUR <= local.hour < END_HOUR


def next_open(number: str, at: Optional[datetime] = None) -> datetime:
    """The earliest moment (naive UTC) at or after `at` when this number may be called."""
    at = at or now()
    if is_open(number, at):
        return at
    off = timedelta(minutes=offset_minutes(number))
    local = at + off
    day = local.date() if local.hour < START_HOUR else local.date() + timedelta(days=1)
    return datetime(day.year, day.month, day.day, START_HOUR) - off


def label(number: str, at: datetime) -> str:
    """'9:00 am tomorrow (their time)' style text for the timeline and toasts."""
    off = timedelta(minutes=offset_minutes(number))
    local, today = at + off, now() + off
    day = "today" if local.date() == today.date() else "tomorrow" if local.date() == today.date() + timedelta(days=1) \
        else local.strftime("%a %d %b")
    return f"{local.strftime('%I:%M %p').lstrip('0').lower()} {day} (their time)"


def window_text() -> str:
    return f"{START_HOUR} am to {END_HOUR - 12} pm"
