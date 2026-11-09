---
name: evidence
description: What the research does and does not support for chaos-seed, with safe wording. Read before making any claim about learning gains.
---

# Evidence notes

Author: TABARC-Code. Compiled from a literature pass in November 2026. I read abstracts and summaries, not every full paper, so treat the numbers as pointers and check them before quoting.

## What the tool is built on

| Claim | Status | Safe wording |
|---|---|---|
| Spacing practice helps retention | Supported, broad evidence | "Spacing is supported. chaos-seed can vary the gaps." |
| Interleaving helps some material | Supported, mixed. Meta-analytic g about 0.42, nearer 0.29 after bias adjustment, depends on material | "Interleaving often helps, by an amount that varies." |
| Random variation as such helps | Not supported. No direct evidence found | "Nobody has shown arbitrary randomness improves learning. Treat it as an experiment." |
| A success rate near 85% is optimal | One model result. The same maths gives about 82% or 75% under other noise assumptions. Practice systems tend to aim for about 75% | "Default target is 0.75, an assumption. Change it." |
| Calibration feedback improves calibration | Supported | "Feedback on predictions tends to improve calibration." |
| Better calibration raises learning | Unproven | "Not shown to raise learning." |
| Predicting before attempting | May itself be retrieval practice, so it can help for that reason | "Might help, for reasons unrelated to calibration." |
| Quantum randomness makes better dice | No. The extra is provenance | "Quantum adds provenance, not better dice." |

## Experiment design

- Fixed balanced blocks beat adaptive allocation for inference. Bandits bias the estimate, so v3 uses blocks of four (two control, two chaos).
- At least four sessions per arm before any estimate is shown. That floor is my synthesis from N-of-1 worked examples, not a published standard.
- Intervals are descriptive. Carryover, order effects and novelty are not modelled, and the learner can often guess the arm.
- Check serial correlation. The tool flags lag-1 above 0.3 in absolute value.

## Measured behaviour of the tune report (simulation, independent attempts)

Success rate 0.75 in control, 400 simulated runs per cell, 90% interval, "excludes zero" rate:

| Sessions per arm x attempts | True effect 0 | 0.05 | 0.10 | 0.15 |
|---|---|---|---|---|
| 8 x 6 | 12% | 18% | 39% | 65% |
| 14 x 6 | 10% | 21% | 53% | 84% |
| 25 x 8 | 8% | 34% | 83% | 100% |

Real sessions are correlated and tired, so expect worse. A small effect needs a lot of sessions. Most people will not collect enough to see one.

## Entropy

- ANU Quantum Numbers API needs a key (`x-api-key`). The live path is untested here because I had no key. Unit tests mock it.
- The CURBy quantum beacon chains had stalled since 2025-08-22 when I checked, so it is not used.
- Monobit, runs and byte chi-square tests are sanity screens, not NIST certification.
- Output is ANU bytes XORed with OS bytes. If ANU fails, the label says so and falls back to OS randomness.

## Retracted from v2.1

- `fit` (scale recommendation): its gate was tuned on my own simulations and needed hundreds of attempts. Gone.
- Thompson sampling and posterior best-arm probabilities: biased inference. Replaced by blocks.
- Custom entropy provider, `--source qrng`, hash mixing, `entropy-check`: more surface than evidence.
- Default target 0.85 moved to 0.75.
