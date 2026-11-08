# How AIMVA decides what to suggest

Campaign suggestions (pause, fix, scale) come from `backend/app/judge.py`. Every other suggestion in
`backend/app/routers/command.py` is a plain rule, for example hot leads waiting or a product over its budget pace.

## Why the judge exists

Leads arrive at random. A campaign whose true cost per lead is exactly on target can show zero leads after
₹1,000, or twice the target after three leads, purely by chance. The old rules acted on the raw numbers. As a
result they told owners to pause healthy campaigns that had a slow week, and to scale campaigns that had a lucky
one. Autopilot in "Fix safely" mode can do the pausing by itself.

The judge treats leads as a Poisson count. It starts from a learned picture of how far campaigns usually sit from
target (the prior), and asks how likely it is that this campaign really costs at least 1.5× the target, or at most
0.7× the target. It only speaks when it is sure enough. When the product has its own target, the suggestion also
shows how sure it is, because that number is calibrated: on the bench, "70-80% sure" was right 82% of the time.

## Train and test: `python backend/scripts/suggestion_bench.py`

Real accounts never reveal the truth, so the bench simulates accounts where the truth is known. Each account
gets a true cost per lead per campaign, about 5% of campaigns never convert, and leads arrive at random.

- **Train.** Pick the prior's spread, the broken share and the two "sure enough" thresholds on 3,000 accounts
  (seed 1). The goal is the most right answers, among settings that tell at most 1 in 100 fine campaigns to pause.
- **Test.** Score the chosen settings on accounts the training never saw (seeds 1001 to 1005), in eight
  scenarios. Results for 2026-11-08, averaged over 5 rounds of 3,000 accounts each:

| Scenario | Right when it suggests pause/fix (old → new) | Fine campaigns told to pause, per 100 (old → new) | Overall accuracy (old → new) |
|---|---|---|---|
| Typical | 78% → 88% | 3.2 → 1.1 | 71.5% → 71.3% |
| Every product has a target | 79% → 90% | 3.2 → 0.7 | 80.6% → 81.0% |
| First 1-3 days | 61% → 78% | 8.3 → 1.9 | 59.5% → 59.6% |
| One week of data | 76% → 85% | 3.6 → 1.3 | 69.1% → 68.5% |
| No targets set | 76% → 84% | 3.2 → 1.4 | 63.0% → 61.9% |
| Small budgets | 71% → 84% | 5.0 → 1.5 | 67.2% → 66.9% |
| Mostly fine campaigns | 58% → 75% | 4.8 → 1.4 | 76.3% → 81.4% |
| Very uneven campaigns | 86% → 92% | 2.8 → 1.1 | 72.3% → 69.5% |

## What the numbers say

- Overall accuracy barely moves. Given the data, the best possible decision rule tops out around 72% in the typical
  case, so the old rules were already near that ceiling. The gain is in being right when the app does speak,
  and in pausing roughly a third as many good campaigns. The price is that it says "too early to tell" more often.
- The biggest lever on accuracy is a target per product: about 81% with targets against 62% without. So AIMVA now
  asks for one, and offers the break-even figure (price × the share of that product's leads who bought) when
  there are at least 10 leads.
- The simulation is an assumption. When real accounts have a few months of history, re-fit the prior from them
  and re-run the bench.

## Analytics tips

Channels are ranked by how often their leads buy, not by how many leads they send, and only channels with at
least 5 leads are compared. Page conversion is flagged only above 200 visits, and call mood only after 5 calls.
