# How AIMVA reads what people type

`backend/app/prompt_sense.py` reads prompts without an AI model, so it works with no keys set.

- **Picture comments, remove or change.** A comment that only takes something away goes to the eraser. Anything
  that puts something there goes to fill. The reader understands English, Hinglish, Hindi, Telugu and Tamil. It
  also fixes typos like "remvoe" and "chnage", and handles comments like "don't remove the logo, make it bigger".
- **New-picture prompts.**
  - Format: "story", "reel" or "status" means 9:16, "banner", "thumbnail" or "cover" means 16:9, and so on. It is
    shown as a hint with a one-click switch, and never changed silently.
  - Words meant for the picture ("poster saying 'Diwali Sale'"): these are kept away from the image model, which
    misspells them, and offered afterwards as real text.

## Train and test: `python backend/scripts/prompt_bench.py`

The hand-labelled sets are in `backend/scripts/prompt_sets/`:

- **dev** sets were used while writing the rules.
- **test** sets were held out.
- **fresh** sets were written after each round of fixes, to see how the rules cope with phrasings they have never
  seen. Each fresh set's misses were then moved into dev, and a new fresh set was written.

Scores on 2026-11-08:

| Set | Comments, old → new | Prompt format, old → new | Words on the picture, old → new |
|---|---|---|---|
| Held-out test | 61% → 100% | 44% → 100% | 64% → 100% |
| Fresh, round 1 (before its fixes) | 54% → 86% | 52% → 95% | 62% → 100% |
| Fresh, round 2 (before its fixes) | 58% → 85% | 50% → 100% | 62% → 100% |
| Fresh, round 3 (before its fixes) | 57% → 70% | not written, round 2 was already 100% | |

The test set was written by the same hand as the rules, so its 100% flatters them. The fresh rounds are the
honest figure: about 70 to 86% on comments worded in ways nobody has written down yet.

Every miss in the fresh rounds was a "remove" read as a "change", never the other way round. That is the safer
way to be wrong: fill repaints the spot following the comment, while sending a "change" to the eraser would
delete what the owner wanted to keep. The owner can also force either one from the ⋯ menu on the comment.

When an AI writer is connected, use it for the comments the rules do not recognise. Until then, add every real
comment the reader gets wrong to a fresh set.
