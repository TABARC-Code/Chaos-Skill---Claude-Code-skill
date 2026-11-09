---
name: chaos-seed
description: Adds bounded, auditable randomness to a learning project (practice order, spacing, difficulty, wildcard exercises), tracks ability, and can run a hidden control experiment to see whether the variation helps. Use when the user wants to shake up, randomise, interleave, space, level or push their learning, mentions plateaus, chaos, stochastic or quantum randomness, or asks whether randomness helps them learn.
---

# chaos-seed

Author: TABARC-Code. Needs Python 3, stdlib only. Everything lives in `scripts/chaos.py`; state is `.chaos/ledger.json` in the working directory.

## Be honest about what this is

Spacing and interleaving have real support. Arbitrary randomness does not. Say so once, early, and offer the experiment as the way to find out for this person. Never say quantum unless `entropy` reports `quantum_live: true`. Quantum adds provenance, not better dice. Details and safe wording: `references/evidence.md`.

## Start with the dials that have evidence

1. Order: `shuffle --items "a,b,c"` to interleave topics.
2. Gaps: `plan --dial gap_days:1:21:7 --sealed` to jitter review spacing inside limits.
3. Difficulty: `next --skill NAME` suggests a level aiming at 0.75 success inside a 0.55 to 0.95 band.
4. Wildcards: `wildcard --n 1` for a change of method. Log those attempts with `--wild` so a failure never lowers the rating.

Draws are sealed by default when blinding matters. `draw`/`plan --sealed` prints only a hash; `reveal ID` shows values and checks the hash.

## Loop

1. `log --skill NAME --level L --result 1|0 [--p PREDICTED]` after each attempt. Predictions feed calibration.
2. `next --skill NAME [--push]` before the next one. `--push` only acts on a detected plateau (ten counted attempts, rating moved under 15 points).
3. `report --text` or `retro` for review. Ratings under 10 counted attempts are provisional.

## The experiment (optional)

`tune pick` at session start: blocks of four, two control (amplitude 0) and two chaos, shuffled, arm hidden (`--open` shows it). While active, `draw`, `plan` and `next` use that arm. `tune clear` ends the session. `tune report` shows chaos minus control with a 90% interval once there are four sessions per arm.

Say plainly: this is descriptive. Fourteen sessions per arm detects a 0.10 gain about half the time and false-alarms about one run in ten. Carryover and order effects are not modelled.

## If you cannot run code

Do the same by hand: shuffle with a real coin or dice, keep the success rate near three in four, label wildcards, never claim quantum. Say you are not using the script.

## Boundaries

Do not use draws for security, money or anything safety related. Do not let a draw override a deadline the user stated. Ask before changing their plan beyond the clamped ranges they gave.
