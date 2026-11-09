# chaos-seed

Bounded randomness for learning projects, plus a way to find out whether it helps you.

Author: TABARC-Code. Version 3.0.0. Python 3, standard library only.

## What it does

It shuffles practice order, jitters review gaps inside limits you set, suggests a difficulty level from an Elo-style rating, and hands out the occasional wildcard exercise. Draws can be sealed behind a SHA-256 hash and revealed later, so you can't peek and nudge. If you want evidence rather than vibes, it can also run a hidden control: some sessions get zero randomness, some get the real thing, and you compare.

## What it doesn't do

It doesn't make you learn faster. Spacing and interleaving have decent support. Random variation as such doesn't, as far as I could find. The experiment exists because of that gap, and with a normal amount of data it will mostly shrug and say "can't tell yet".

"Quantum" is only claimed when a live ANU quantum feed answered, passed basic health tests, and was XORed with OS randomness. I haven't been able to test that path with a real key. The unit tests mock it. Without a key you get the OS CSPRNG, which is excellent and not quantum.

## Install

Copy the folder anywhere and run `scripts/chaos.py` with Python 3. `SKILL.md` is there if you want to load it as an agent skill; the script doesn't need it. Nothing to pip install.

## First run

```
python3 scripts/chaos.py shuffle --items "scales,sight-reading,theory"
python3 scripts/chaos.py log --skill piano --level 4 --result 1 --p 0.8
python3 scripts/chaos.py next --skill piano
python3 scripts/chaos.py report --text
```

State goes in `.chaos/ledger.json` in the current directory. Use `--dir` to move it.

## The experiment

```
python3 scripts/chaos.py tune pick       # arm stays hidden
# ...do the session, logging attempts...
python3 scripts/chaos.py tune clear
python3 scripts/chaos.py tune report     # needs 4 sessions per arm
```

Assignment is in shuffled blocks of four, two control and two chaos. It doesn't adapt to results, because adaptive allocation biases the estimate. Rough error rates from simulation, assuming independent attempts: about 10% false alarms on pure noise, and a 0.10 real gain is spotted about half the time at 14 sessions per arm. Real sessions are messier, so expect worse. The report is descriptive. It doesn't model carryover or learning over time, and you can often guess which arm you're in.

## Commands

`draw`, `reveal`, `plan`, `shuffle`, `drift`, `wildcard`, `log`, `next`, `report`, `tune`, `retro`, `entropy`, `feedback`, `status`. Run with `-h` for flags.

## Tests

```
python3 -W error -I tests/test_chaos.py
```

28 tests, about a third of a second. They check the sealing, bounds, rating maths, block balance and the report's false-alarm rate on noise. They don't check that any of this helps anybody learn.

## Defaults worth questioning

Target success 0.75, safe band 0.55 to 0.95, Elo scale 200, K from 32 down to 16. These are assumptions. The famous 85% figure is one model result and shifts to about 75% or 82% under other noise assumptions. See `references/evidence.md` for sources and what was cut from v2.1 (the `fit` command, bandit allocation, a custom entropy provider), and why.

## Licence

MIT. See `LICENSE`.
