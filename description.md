# chaos-seed: design notes

Author: TABARC-Code. Version 3.0.0.

## Why it's shaped this way

The first version did too much. It had a bandit picking how much chaos you got, a fitted difficulty scale, three entropy providers and a hash mixer. Then I went and read the literature, and most of it wasn't earning its place. v3 is the result of cutting.

What stayed is what the evidence will carry: spacing and interleaving dials, a difficulty target in a safe band, calibration tracking, and a plain experiment for the one question nobody has answered, which is whether arbitrary variation helps a given person.

## The pieces

**Entropy.** `get_bytes` returns OS bytes, or ANU bytes XORed with OS bytes when a key is set and the batch passes monobit, runs and chi-square screens. XOR means a bad quantum feed can't weaken the OS stream. The label travels with every draw, so a draw made during a feed outage says so. `Pool.below` uses rejection sampling to avoid modulo bias.

**Sealed draws.** A draw's values go into the ledger with a nonce and a SHA-256 commit. The caller sees only the hash until `reveal`. This is about stopping yourself from steering, not about security.

**Ability.** A logistic model, rating 1000 to start, level L at difficulty 600+100L, scale 200. K decays from 32 to 16. Wildcard attempts don't touch the rating, so trying something odd never punishes you. Under ten counted attempts the rating is flagged provisional.

**Difficulty.** `next` picks the level where expected success equals the target, adds a chaos offset, then clamps to the safe band. `--push` lowers the target by 0.10 on a plateau and widens the offset.

**Experiment.** `tune pick` pops an arm from a shuffled block of four. The residual per session is result minus expected, averaged. The report compares arms with a 90% interval and flags lag-1 autocorrelation above 0.3. While an experiment is active, automatic amplitude damping is off so it can't contaminate the arms.

## Known limits

- The live ANU path has not been run against a real key.
- The CURBy beacon had stopped publishing quantum chains when I looked, so it's out.
- Simulated error rates assume independent attempts. They are optimistic.
- The 85% rule, the 0.75 default and the Elo constants are assumptions, not findings.
- Calibration feedback is not shown to improve learning, and predicting may help simply by being retrieval practice.

## If you change it

Keep the label honest. Keep results out of allocation. If you add something, take something out, and add a test that would fail if it broke.
