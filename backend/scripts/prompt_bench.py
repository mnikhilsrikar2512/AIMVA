"""Score how well AIMVA reads what people type, on hand-labelled sets (scripts/prompt_sets/).

    python scripts/prompt_bench.py          # dev and held-out test scores, old vs new, with every miss listed

*_dev.tsv were used while writing the rules in app/prompt_sense.py; *_test.tsv were written before those changes and
never used to tune them. *_fresh.tsv were written after the rules, to catch rules that only fit the phrasing of the
first two sets; they are the most honest score.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.prompt_sense import comment_intent, read_prompt  # noqa: E402

HERE = os.path.join(os.path.dirname(__file__), "prompt_sets")


def rows(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return [line.rstrip("\n").split("\t") for line in f if line.strip() and not line.startswith("#")]


def old_intent(text):  # the rule before 2026-11-08 (app/image_edit.py)
    import re
    rm = re.compile(r"\b(remove|delete|erase|get rid of|take (out|away)|eliminate|hide|lose|clear (away|out))\b", re.I)
    add = re.compile(r"\b(add|put|place|replace|swap|instead|insert|with a|with an|turn (it )?into)\b", re.I)
    return "remove" if rm.search(text) and not add.search(text) else "change"


def old_read(prompt):  # before: nothing was read; the prompt went to the model as typed
    return {"format": None, "words": None, "scene": prompt}


def score_comments(name, fn, show=False):
    data = rows(name)
    miss = [(lab, txt, fn(txt)) for lab, txt in data if fn(txt) != lab]
    if show:
        for lab, txt, got in miss:
            print(f"      miss: {txt!r} -> {got} (should be {lab})")
    return 1 - len(miss) / len(data), len(data)


def score_prompts(name, fn, show=False):
    data = rows(name)
    ok_f = ok_w = 0
    for fmt, words, prompt in data:
        r = fn(prompt)
        want_f, want_w = (None if fmt == "-" else fmt), (None if words == "-" else words)
        ok_f += r["format"] == want_f
        ok_w += r["words"] == want_w
        if show and (r["format"] != want_f or r["words"] != want_w):
            print(f"      miss: {prompt!r} -> format {r['format']}, words {r['words']!r} (should be {want_f}, {want_w!r})")
    return ok_f / len(data), ok_w / len(data), len(data)


def main():
    for split in ("dev", "test", "fresh", "fresh2", "fresh3"):
        print(f"\n{split.upper()} SET")
        a_old, n = score_comments(f"comments_{split}.tsv", old_intent)
        a_new, _ = score_comments(f"comments_{split}.tsv", comment_intent, show=True)
        print(f"  picture comments, remove vs change ({n}): old {a_old:.0%} -> new {a_new:.0%}")
        if not os.path.exists(os.path.join(HERE, f"prompts_{split}.tsv")):
            continue
        f_old, w_old, n = score_prompts(f"prompts_{split}.tsv", old_read)
        f_new, w_new, _ = score_prompts(f"prompts_{split}.tsv", read_prompt, show=True)
        print(f"  new-picture prompts ({n}): format old {f_old:.0%} -> new {f_new:.0%}; words old {w_old:.0%} -> new {w_new:.0%}")


if __name__ == "__main__":
    main()
