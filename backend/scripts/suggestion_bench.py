"""Train and test the campaign suggestions on simulated accounts whose true cost per lead is known.

    python scripts/suggestion_bench.py            # tune on training accounts, then test on fresh ones
    python scripts/suggestion_bench.py --quick    # smaller run, for CI

Real accounts never tell you the truth ("was that campaign really bad, or unlucky?"), so the bench makes
accounts where it is known: every campaign gets a true cost per lead, then leads arrive at random like real ones.
A suggestion is right when it matches the truth:
  cut   (pause / fix): the campaign really costs 1.5× the target or more, or never converts
  scale:              it really costs 0.7× the target or less
  nothing:            anything in between
"Training" picks the judge's thresholds on one set of accounts; "testing" scores them on accounts it never saw,
several times with different random seeds, and on harder scenarios (one week of data, no targets set...).
"""
import argparse
import itertools
import math
import os
import random
import sys
from dataclasses import replace
from statistics import mean, median, pstdev

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.judge import SHIPPED, Params, decide, judge, judge_v0, posterior  # noqa: E402

SCENARIOS = {
    "typical": {},
    "every product has a target": {"targets": 1.0},
    "first 1-3 days": {"days": (1, 2, 3)},
    "one week of data": {"days": (7,)},
    "no targets set": {"targets": 0.0},
    "small budgets": {"budget": (300, 800)},
    "mostly fine campaigns": {"sigma": 0.3},
    "very uneven campaigns": {"sigma": 1.0},
}


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 60:  # normal approximation, fine at this size
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def account_target(camps: list, how: str):
    """The target the app falls back on when the owner set none: what the account's campaigns typically cost."""
    cpls = [c["spend"] / c["leads"] for c in camps if c["leads"]]
    if how == "median":  # the rule before 2026-11-08
        return median(cpls) if cpls else None
    spend, leads = sum(c["spend"] for c in camps), sum(c["leads"] for c in camps)
    if how == "pooled":
        return spend / leads if leads else None
    if how == "median+":  # median, but only when at least two campaigns have leads, else pooled
        return median(cpls) if len(cpls) >= 2 else (spend / leads if leads else None)
    raise ValueError(how)


def simulate(seed: int, accounts: int, days=(2, 3, 7, 14, 30, 30, 30, 90), targets=0.5, budget=(300, 5000), sigma=0.6,
             broken=0.08, estimator="median") -> list:
    """Campaign rows: what the app would see (spend, leads, clicks, target it would use) plus the hidden truth."""
    rng = random.Random(seed)
    rows = []
    for _ in range(accounts):
        t_true = math.exp(rng.uniform(math.log(150), math.log(2500)))
        has_target = rng.random() < targets
        d = rng.choice(days)
        camps = []
        for _ in range(rng.randint(1, 4)):
            dead = rng.random() < broken
            m = math.inf if dead else math.exp(rng.gauss(0, sigma))
            daily = math.exp(rng.uniform(math.log(budget[0]), math.log(budget[1])))
            spend = daily * d * rng.uniform(0.7, 1.0)
            cpc = math.exp(rng.uniform(math.log(5), math.log(40)))
            clicks = _poisson(rng, spend / cpc)
            leads = 0 if dead else min(clicks, _poisson(rng, spend / (t_true * m)))
            camps.append({"spend": spend, "leads": leads, "clicks": clicks, "m": m})
        # Like compute(): the product's target when there is one, else the median cost per lead of the account.
        target = t_true if has_target else account_target(camps, estimator)
        for c in camps:
            truth = "cut" if c["m"] >= 1.5 else "scale" if c["m"] <= 0.7 else None
            rows.append({**c, "target": target, "truth": truth, "estimated": not has_target})
    return rows


def score(rows: list, fn) -> dict:
    said = {"cut": 0, "scale": 0}
    right = {"cut": 0, "scale": 0}
    real = {"cut": 0, "scale": 0}
    good_paused = correct = 0
    for r in rows:
        v = fn(r["spend"], r["leads"], r["clicks"], r["target"])["verdict"]
        v = "cut" if v in ("pause", "fix") else v
        if r["truth"]:
            real[r["truth"]] += 1
        if v:
            said[v] += 1
            right[v] += v == r["truth"]
        if v == "cut" and r["m"] < 1.2:
            good_paused += 1  # a campaign that's actually fine, told to pause
        correct += v == r["truth"]
    out = {"accuracy": correct / len(rows)}
    for k in ("cut", "scale"):
        p = right[k] / said[k] if said[k] else 1.0
        rc = right[k] / real[k] if real[k] else 1.0
        out[f"{k}_precision"], out[f"{k}_recall"] = p, rc
    out["good_paused_per_100"] = good_paused / len(rows) * 100
    out["suggestions_per_100"] = (said["cut"] + said["scale"]) / len(rows) * 100
    # What "better" means when tuning: the most right answers, among settings that tell at most 1 in 100 fine
    # campaigns to pause (Autopilot may pause it by itself, and the owner loses leads they were getting).
    out["objective"] = out["accuracy"] - (0 if out["good_paused_per_100"] <= 1.0 else 1)
    return out


GRID = {"sigma": (0.4, 0.5, 0.6, 0.7, 0.8, 1.0), "broken": (0.03, 0.05, 0.08, 0.12, 0.15)}
TAUS = (0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7)


def train(rows: list) -> tuple:
    """Learn the prior (how spread out campaigns are, how many are broken) and how sure to be before speaking.
    The posteriors only depend on the prior, so they are worked out once per prior and reused for every threshold."""
    best = None
    for sigma, broken in itertools.product(*GRID.values()):
        post = [posterior(r["spend"], r["leads"], r["target"], sigma, broken) if r["target"] and r["spend"] > 0 else None
                for r in rows]
        for tc, ts in itertools.product(TAUS, TAUS):
            p = Params(sigma=sigma, broken=broken, tau_cut=tc, tau_scale=ts)

            def fn(spend, leads, clicks, target, _it=iter(post), p=p):
                q = next(_it)
                if q is None:
                    return judge(spend, leads, clicks, target, p)
                return {"verdict": decide(q[0], q[1], leads, p)}
            s = score(rows, fn)
            if best is None or s["objective"] > best[1]["objective"]:
                best = (p, s)
    return best


def fmt(s: dict) -> str:
    return (f"accuracy {s['accuracy']:.1%} | pause/fix right {s['cut_precision']:.1%}, caught {s['cut_recall']:.1%} | "
            f"scale right {s['scale_precision']:.1%}, caught {s['scale_recall']:.1%} | "
            f"good campaigns told to pause: {s['good_paused_per_100']:.1f} per 100")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--rounds", type=int, default=5)
    args = ap.parse_args()
    n = 300 if args.quick else 3000

    print(f"TRAIN on {n} simulated accounts (seed 1)")
    tr = simulate(1, n)
    p, s = train(tr)
    print(f"  best thresholds: {p}")
    print(f"  train  new: {fmt(s)}")
    print(f"  train  old: {fmt(score(tr, judge_v0))}")
    if p != SHIPPED:
        print(f"  NOTE: shipped thresholds differ from this run's best: {SHIPPED}")

    print(f"\nTEST on fresh accounts, {args.rounds} rounds each (seeds 1001+); shipped thresholds vs the old rules")
    for name, kw in SCENARIOS.items():
        new, old = [], []
        for i in range(args.rounds):
            rows = simulate(1001 + i, n, **kw)
            new.append(score(rows, judge))
            old.append(score(rows, judge_v0))
        avg = lambda xs: {k: mean(x[k] for x in xs) for k in xs[0]}  # noqa: E731
        sd = pstdev(x["accuracy"] for x in new)
        print(f"\n  {name}")
        print(f"    new: {fmt(avg(new))}  (accuracy ±{sd:.1%})")
        print(f"    old: {fmt(avg(old))}")


if __name__ == "__main__":
    main()
