"""Score how well AIMVA picks the language to reply to a lead in (the 60-second reply edge).

    python scripts/lead_language_bench.py          # every set, with each miss listed

leads_dev.tsv was used while tuning app/lead_reply.py detect(); leads_test.tsv was written before that and never used
to tune it; leads_fresh*.tsv were written after the tuning, to catch rules that only fit the first two sets. The label
is the language AIMVA should reply in; "en" also means "not sure", because English is the fallback.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.lead_reply import detect  # noqa: E402

HERE = os.path.join(os.path.dirname(__file__), "prompt_sets")
SPLITS = ("dev", "test", "fresh", "fresh2", "roman_dev", "roman_test", "roman_fresh")


def rows(name):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line.rstrip("\n").split("\t", 1) for line in f if line.strip() and not line.startswith("#")]


def reply_language(text):
    return detect(text) or "en"


def score(name, show=True):
    data = rows(name)
    if not data:
        return None, 0
    miss = [(lab, txt, reply_language(txt)) for lab, txt in data if reply_language(txt) != lab]
    if show:
        for lab, txt, got in miss:
            print(f"      miss: {txt!r} -> {got} (should be {lab})")
    return 1 - len(miss) / len(data), len(data)


def main():
    for split in SPLITS:
        acc, n = score(f"leads_{split}.tsv")
        if n:
            print(f"  {split.upper()} ({n}): {acc:.0%}")


if __name__ == "__main__":
    main()
