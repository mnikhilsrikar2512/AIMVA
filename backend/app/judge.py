"""Is a campaign really too expensive, really cheap, or just unlucky so far?

Leads arrive at random. A campaign whose true cost per lead is right on target can easily show zero leads after
₹1,000 or double the target after three leads, purely by chance. The old rules acted on the raw numbers, so they
paused good campaigns that had a slow week and scaled ones that had a lucky one (Autopilot can do both by itself).

Here leads are treated as a Poisson count. "If this campaign really cost the target per lead, how likely is a
result this bad (or this good)?" Only when that chance is small, and the gap is big enough to matter, does it
become a suggestion. The thresholds were tuned on simulated accounts with known true costs and checked on fresh
ones: see scripts/suggestion_bench.py and docs/SUGGESTIONS.md.
"""
from dataclasses import dataclass
from math import exp, log
from typing import Optional


@dataclass(frozen=True)
class Params:
    sigma: float = 0.6       # how far campaigns usually sit from target (spread of log true-cost/target)
    broken: float = 0.08     # share of campaigns that never convert at all (broken form, wrong audience)
    tau_cut: float = 0.5     # how sure (0-1) before saying pause or fix
    tau_scale: float = 0.5   # how sure before saying spend more
    no_target_clicks: int = 100  # without any target: clicks with no lead before calling it broken


SHIPPED = Params(sigma=0.5, broken=0.05, tau_cut=0.5, tau_scale=0.45)  # from scripts/suggestion_bench.py, 2026-11-08

CUT, SCALE = 1.5, 0.7  # "really too dear" and "really cheap", as multiples of the target
_GRID = [i / 20 for i in range(-60, 61)]  # log(true cost / target) from e^-3 to e^3


def posterior(spend: float, leads: int, target: float, sigma: float, broken: float) -> tuple:
    """(P(really too dear or broken), P(really cheap)) given what was spent and the leads it brought.

    Prior: log(true cost/target) ~ Normal(0, sigma), plus a `broken` share that never converts. Likelihood: leads ~
    Poisson(spend / true cost)."""
    lam0 = spend / target
    # Everything in logs first: a campaign that spent 1,000× its target with no lead must not overflow.
    wsum = sum(exp(-0.5 * (x / sigma) ** 2) for x in _GRID)
    logs = []
    for x in _GRID:
        lam = lam0 * exp(-x)
        like = leads * log(lam) - lam if lam > 0 else (0.0 if leads == 0 else -1e9)
        logs.append(like - 0.5 * (x / sigma) ** 2 - log(wsum) + log(1 - broken))
    dead_log = log(broken) if leads == 0 and broken > 0 else None  # P(0 leads | broken) = 1
    top = max(logs + ([dead_log] if dead_log is not None else []))
    post = [exp(l - top) for l in logs]
    dead = exp(dead_log - top) if dead_log is not None else 0.0
    total = sum(post) + dead
    lc, ls = log(CUT), log(SCALE)
    p_cut = (sum(p for x, p in zip(_GRID, post) if x >= lc) + dead) / total
    p_scale = sum(p for x, p in zip(_GRID, post) if x <= ls) / total
    return p_cut, p_scale


def decide(p_cut: float, p_scale: float, leads: int, p: Params = SHIPPED):
    if p_cut >= p.tau_cut and p_cut >= p_scale:
        return "pause" if not leads else "fix"
    if p_scale >= p.tau_scale:
        return "scale"
    return None


def judge(spend: float, leads: int, clicks: int, target: Optional[float], p: Params = SHIPPED) -> dict:
    """{"verdict": "pause" | "fix" | "scale" | None, "sure": how likely the verdict is right (0-1), or None}.

    pause: money spent, no leads, and bad luck alone is unlikely. fix: leads, but really too dear.
    scale: really cheaper than target. None: fine, or too early to tell.
    """
    if spend <= 0:
        return {"verdict": None, "sure": None}
    if not target:
        if not leads and clicks >= p.no_target_clicks:
            return {"verdict": "pause", "sure": None}
        return {"verdict": None, "sure": None}
    pc, ps = posterior(spend, leads, target, p.sigma, p.broken)
    v = decide(pc, ps, leads, p)
    return {"verdict": v, "sure": round(pc if v in ("pause", "fix") else ps if v else 1 - pc - ps, 2)}


def judge_v0(spend: float, leads: int, clicks: int, target: Optional[float]) -> dict:
    """The rules before 2026-11-08, kept for the bench to compare against."""
    t = target
    if not leads and spend > 0 and (clicks >= 30 or (t and spend >= 3 * t)):
        return {"verdict": "pause", "chance": None}
    if leads and t and spend / leads > 1.5 * t and spend >= 2 * t:
        return {"verdict": "fix", "chance": None}
    if leads >= 3 and t and spend / leads <= 0.7 * t:
        return {"verdict": "scale", "chance": None}
    return {"verdict": None, "chance": None}
