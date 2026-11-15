"""Score how well /api/start reads an owner's idea (kind of business, industry, city), on hand-labelled sets.

    python scripts/idea_bench.py          # every set, with each miss listed
    python scripts/idea_bench.py --ai     # the same, with the AI writer reading first (needs a configured AI key)

ideas_dev.tsv was used while writing app/idea_sense.py; ideas_test.tsv was written before it existed; ideas_fresh*.tsv
were written after the rules, to catch rules that only fit the first two sets. "kind" decides which modules the
owner sees, so it matters most; "city" decides the customer languages (the WhatsApp reply edge).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.idea_sense import read_idea, route  # noqa: E402

HERE = os.path.join(os.path.dirname(__file__), "prompt_sets")
SPLITS = ("dev", "test", "fresh", "fresh2", "fresh3")
WRITE = None  # set by --ai: the AI writer /api/start uses, so the score is the one owners get


def rows(name):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line.rstrip("\n").split("\t", 3 if name.startswith("ideas") else 1) for line in f if line.strip() and not line.startswith("#")]


def score(name, show=True):
    data = rows(name)
    ok = {"kind": 0, "industry": 0, "city": 0}
    for kind, industry, city, idea in data:
        p = read_idea(idea, write=WRITE)["profile"]
        got = {"kind": p["kind"], "industry": p["industry"], "city": p["city"] or "-"}
        want = {"kind": kind, "industry": industry, "city": city}
        for k in ok:
            ok[k] += got[k] == want[k]
        if show and got != want:
            diff = ", ".join(f"{k} {got[k]} (should be {want[k]})" for k in ok if got[k] != want[k])
            print(f"      miss: {idea!r} -> {diff}")
    return {k: v / len(data) for k, v in ok.items()} if data else None, len(data)


def score_routes(name, show=True):
    data = rows(name)
    miss = [(lab, txt, route(txt)) for lab, txt in (r[:2] for r in data) if route(txt) != lab]
    if show:
        for lab, txt, got in miss:
            print(f"      miss: {txt!r} -> {got} (should be {lab})")
    return (1 - len(miss) / len(data)) if data else None, len(data)


def main():
    global WRITE
    if "--ai" in sys.argv:
        from app.ai_engine import agent_writer
        from app.db import SessionLocal
        WRITE = agent_writer(SessionLocal(), None, "site_reader")
        if not WRITE:
            sys.exit("No AI engine is configured for site_reader: add a key (docs/AI_KEYS.md) and try again.")
    print("IDEAS (POST /api/start)" + (", AI first" if WRITE else ", rules only"))
    for split in SPLITS:
        acc, n = score(f"ideas_{split}.tsv")
        if n:
            print(f"  {split.upper()} ({n}): kind {acc['kind']:.0%}, city {acc['city']:.0%}, industry {acc['industry']:.0%}")
    print("HOME ROUTING (POST /api/route)")
    for split in SPLITS:
        acc, n = score_routes(f"routes_{split}.tsv")
        if n:
            print(f"  {split.upper()} ({n}): {acc:.0%}")


if __name__ == "__main__":
    main()
