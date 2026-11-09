#!/usr/bin/env python3
"""chaos.py v3.0.0 - bounded randomness, ability tracking, a self-test. TABARC-Code.
Python 3 stdlib only.

Entropy label (printed every call):
  os-csprng       OS CSPRNG. Strong, not quantum.
  quantum-mixed   ANU quantum bytes XORed with OS bytes (needs env ANU_QRNG_API_KEY).
                  This adds provenance, not better dice. Not for cryptography.

Commands
  draw reveal plan shuffle drift wildcard      randomness (draws are sealed by hash)
  log next report                              ability (Elo-style) and calibration
  tune pick|report|clear                       balanced blocks: chaos vs hidden control
  retro                                        one-page review with proposals
  entropy feedback status

Assumptions, not findings: Elo scale 200, K 32 decaying to 16, target success 0.75,
safe band 0.55-0.95. See references/evidence.md.
"""
import argparse, hashlib, json, math, os, random, secrets, sys, time, urllib.request

VERSION = "3.0.0"
UA = "chaos-seed/3.0 (learning-tool)"
ANU_URL = "https://api.quantumnumbers.anu.edu.au/?length={n}&type=uint8"
LEDGER = "ledger.json"
AMP_MIN, AMP_MAX = 1, 5
ELO_S, BASE, START = 200.0, 600.0, 1000.0
MIN_PER_ARM = 4   # replicate floor from the N-of-1 literature's worked examples (a synthesis, not a standard)

WILDCARDS = [
    "Teach it back in five minutes to an imaginary beginner, no notes.",
    "Retrieval first: write everything you recall before opening the material.",
    "Halve the time-box. Ship something rough.",
    "Smallest working example that demonstrates the idea.",
    "Predict the result before you run, read or check it. Write the prediction down.",
    "Swap the medium: sketch it, speak it, or build it instead of reading it.",
    "Explain it without the technical vocabulary.",
    "Interleave: do one item from the previous topic first.",
    "Work backwards from a finished example to the steps.",
    "Find the flaw: ask for a deliberately flawed example, labelled as such, and fix it.",
    "Constraint round: solve it with one tool or one rule removed.",
    "Free choice: spend ten minutes on whatever pulls at you, then name what you learned.",
]


# ---------- entropy ----------
def health(b):
    """Monobit + runs (+ byte chi-square from 2048 bytes), alpha 0.001. A screen for broken sources."""
    n = len(b) * 8
    ones = sum(bin(x).count("1") for x in b)
    out = {"bits": n, "monobit_p": math.erfc(abs(2 * ones - n) / math.sqrt(2 * n))}
    pi = ones / n
    if abs(pi - 0.5) >= 2 / math.sqrt(n):
        out["runs_p"] = 0.0
    else:
        bits = "".join("{:08b}".format(x) for x in b)
        v = 1 + sum(1 for i in range(n - 1) if bits[i] != bits[i + 1])
        out["runs_p"] = math.erfc(abs(v - 2 * n * pi * (1 - pi)) / (2 * math.sqrt(2 * n) * pi * (1 - pi)))
    if len(b) >= 2048:
        e, cnt = len(b) / 256.0, [0] * 256
        for x in b:
            cnt[x] += 1
        chi = sum((c - e) ** 2 / e for c in cnt)
        z = ((chi / 255.0) ** (1 / 3) - (1 - 2 / (9 * 255.0))) / math.sqrt(2 / (9 * 255.0))
        out["chi2_p"] = math.erfc(abs(z) / math.sqrt(2))
    out["pass"] = all(v >= 0.001 for k, v in out.items() if k.endswith("_p"))
    return out


def anu_bytes(n, key):
    """(bytes, None) or (None, reason)."""
    try:
        req = urllib.request.Request(ANU_URL.replace("{n}", str(n)),
                                     headers={"User-Agent": UA, "x-api-key": key})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.load(r).get("data", [])
    except Exception as e:
        return None, "request failed (%s)" % type(e).__name__
    if len(data) < n or not all(isinstance(x, int) and 0 <= x < 256 for x in data[:n]):
        return None, "unusable data"
    b = bytes(data[:n])
    return (b, None) if health(b)["pass"] else (None, "batch failed health test")


def get_bytes(n, want="auto"):
    ob = secrets.token_bytes(n)
    key = None if want == "os" else os.environ.get("ANU_QRNG_API_KEY")
    if not key:
        return ob, "os-csprng"
    qb, why = anu_bytes(n, key)
    if qb:
        return bytes(x ^ y for x, y in zip(qb, ob)), "quantum-mixed(anu-aqn+os-csprng)"
    return ob, "os-csprng (anu-aqn unavailable: %s)" % why


class Pool:
    def __init__(self, want="auto"):
        self.want, self.buf, self.source = want, b"", None

    def ensure(self):
        """Fetch now so the source label exists even for zero-width draws."""
        if not self.buf:
            self.buf, s = get_bytes(256, self.want)
            self.source = self.source or s
        return self

    def byte(self):
        self.ensure()
        b, self.buf = self.buf[0], self.buf[1:]
        return b

    def below(self, span):
        """Uniform int in [0, span) by rejection sampling (no modulo bias)."""
        if span <= 1:
            return 0
        if span > 256:
            return secrets.randbelow(span)
        limit = 256 - (256 % span)
        while True:
            b = self.byte()
            if b < limit:
                return b % span

    def shuffle(self, xs):
        for i in range(len(xs) - 1, 0, -1):
            j = self.below(i + 1)
            xs[i], xs[j] = xs[j], xs[i]
        return xs


# ---------- ledger ----------
def path(d):
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, LEDGER)


def load(d):
    led = {}
    if os.path.exists(path(d)):
        with open(path(d)) as f:
            led = json.load(f)
    led.setdefault("amp", 2)
    led.setdefault("session", 0)
    led.setdefault("active", None)
    led.setdefault("block", [])
    for k in ("draws", "skills"):
        led.setdefault(k, {})
    for k in ("history", "attempts"):
        led.setdefault(k, [])
    return led


def save(d, led):
    tmp = path(d) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(led, f, indent=2)
    os.replace(tmp, path(d))


def seal(led, values, amp, source, label, extra=None):
    body = {"values": values, "nonce": secrets.token_hex(8)}
    body.update(extra or {})
    payload = json.dumps(body, sort_keys=True)
    commit = hashlib.sha256(payload.encode()).hexdigest()
    did = "d" + secrets.token_hex(3)
    led["draws"][did] = {"payload": payload, "commit": commit, "amp": amp, "source": source,
                         "t": int(time.time()), "revealed": False, "label": label or ""}
    return did, commit


def eff_amp(led, override):
    """Explicit --amp, else the active session arm (0 = control), else the learned amplitude."""
    v = override if override is not None else (led["active"]["arm"] if led["active"] else led["amp"])
    return max(0, min(AMP_MAX, v))


def draw_values(pool, amp, n):
    return [pool.below(2 * amp + 1) - amp for _ in range(n)]


# ---------- randomness ----------
def cmd_draw(a):
    led, pool = load(a.dir), Pool(a.source).ensure()
    amp = eff_amp(led, a.amp)
    vals = draw_values(pool, amp, a.n)
    did, commit = seal(led, vals, amp, pool.source, a.label)
    save(a.dir, led)
    print(json.dumps({"id": did, "n": a.n, "commit": commit, "source": pool.source, "sealed": True}))
    if not a.sealed:
        print(json.dumps({"values": vals, "amp": amp}), file=sys.stderr)


def cmd_reveal(a):
    led = load(a.dir)
    d = led["draws"].get(a.id) or sys.exit("no such draw")
    ok = hashlib.sha256(d["payload"].encode()).hexdigest() == d["commit"]
    d["revealed"] = True
    save(a.dir, led)
    p = json.loads(d["payload"])
    out = {"id": a.id, "values": p["values"], "amp": d["amp"], "source": d["source"],
           "commit_ok": ok, "label": d["label"]}
    out.update({k: p[k] for k in ("dials", "kind") if k in p})
    print(json.dumps(out))


def cmd_plan(a):
    led, pool = load(a.dir), Pool(a.source).ensure()
    amp = eff_amp(led, a.amp)
    dials = []
    for spec in a.dial:
        try:
            name, lo, hi, cur = spec.split(":")
            lo, hi, cur = float(lo), float(hi), float(cur)
        except ValueError:
            sys.exit("bad --dial, want name:min:max:current  got " + spec)
        if not lo <= cur <= hi:
            sys.exit("current outside range for " + name)
        dials.append((name, lo, hi, cur))
    vals = draw_values(pool, amp, len(dials))
    result = []
    for (name, lo, hi, cur), v in zip(dials, vals):
        new = min(hi, max(lo, cur + v * a.step))
        result.append({"dial": name, "from": cur, "to": new, "clamped": new != cur + v * a.step})
    did, commit = seal(led, vals, amp, pool.source, a.label, {"dials": result})
    save(a.dir, led)
    print(json.dumps({"id": did, "dials": len(dials), "commit": commit, "source": pool.source,
                      "sealed": True, "clamped": sum(r["clamped"] for r in result)}))
    if not a.sealed:
        print(json.dumps({"plan": result, "amp": amp}), file=sys.stderr)


def cmd_shuffle(a):
    items = a.items.split(",") if a.items else [l.rstrip("\n") for l in sys.stdin if l.strip()]
    pool = Pool(a.source).ensure()
    print(json.dumps({"order": pool.shuffle(items), "source": pool.source}))


def cmd_drift(a):
    """Logistic-map stream (r=3.99), seeded from entropy. Autocorrelated variation; decorative-leaning."""
    b, src = get_bytes(8, a.source)
    x = min(max((int.from_bytes(b, "big") % 10**9) / 10**9, 0.001), 0.999)
    for _ in range(50):
        x = 3.99 * x * (1 - x)
    out = []
    for _ in range(a.n):
        x = 3.99 * x * (1 - x)
        out.append(round((x - 0.5) * 2 * a.amp, 3))
    print(json.dumps({"drift": out, "amp": a.amp, "seed_source": src}))


def cmd_wildcard(a):
    pool, items, picks = Pool(a.source).ensure(), list(WILDCARDS), []
    for _ in range(min(a.n, len(items))):
        picks.append(items.pop(pool.below(len(items))))
    print(json.dumps({"wildcards": picks, "source": pool.source,
                      "safe_fail": "log wildcard attempts with --wild: recorded, never lower your rating"}))


# ---------- ability ----------
def expected(rating, level):
    return 1.0 / (1.0 + 10 ** (((BASE + 100 * level) - rating) / ELO_S))


def kfac(n):
    return max(16.0, 32.0 - n * 0.5)


def cmd_log(a):
    led = load(a.dir)
    sk = led["skills"].setdefault(a.skill, {"rating": START, "n": 0})
    e, act = expected(sk["rating"], a.level), led["active"]
    if not a.wild:
        sk["rating"] = round(sk["rating"] + kfac(sk["n"]) * (a.result - e), 2)
        sk["n"] += 1
    led["attempts"].append({"t": int(time.time()), "skill": a.skill, "level": a.level,
                            "result": a.result, "p": a.p, "wild": a.wild, "expected": round(e, 3),
                            "rating_after": sk["rating"], "arm": act["arm"] if act else None,
                            "session": act["session"] if act else None, "note": a.note or ""})
    note = None
    if not act:   # automatic damping would contaminate a running experiment
        last = [x["result"] for x in led["attempts"] if x["skill"] == a.skill and not x["wild"]][-5:]
        if len(last) >= 3 and sum(last[-3:]) == 0 and led["amp"] > AMP_MIN:
            led["amp"] -= 1
            note = "three misses in a row: amplitude damped to %d" % led["amp"]
        elif len(last) == 5 and sum(last) == 5 and led["amp"] < AMP_MAX:
            led["amp"] += 1
            note = "five clears in a row: amplitude widened to %d" % led["amp"]
    save(a.dir, led)
    print(json.dumps({"skill": a.skill, "level_est": round((sk["rating"] - BASE) / 100, 2),
                      "expected_success": round(e, 3), "counted": not a.wild, "note": note}))


def is_plateau(led, skill, window=10, tol=15.0):
    r = [x["rating_after"] for x in led["attempts"]
         if x["skill"] == skill and not x["wild"] and "rating_after" in x]
    return len(r) >= window and abs(r[-1] - r[-window]) < tol


def cmd_next(a):
    led = load(a.dir)
    sk = led["skills"].get(a.skill, {"rating": START, "n": 0})
    r, plateau, target, step, pushed = sk["rating"], is_plateau(led, a.skill), a.target, 0.25, False
    if a.push and plateau:
        target, step, pushed = max(a.floor + 0.05, a.target - 0.10), 0.5, True
    lvl_for = lambda p: (r + ELO_S * math.log10(1.0 / p - 1.0) - BASE) / 100.0
    base_level, lo, hi = lvl_for(target), lvl_for(a.ceiling), lvl_for(a.floor)
    amp, pool = eff_amp(led, a.amp), Pool(a.source).ensure()
    raw = base_level + (pool.below(2 * amp + 1) - amp) * step
    lvl = min(10.0, max(1.0, min(hi, max(lo, raw))))
    print(json.dumps({"skill": a.skill, "target_success": round(target, 2),
                      "level_at_target": round(base_level, 2), "suggested_level": round(lvl, 2),
                      "expected_success": round(expected(r, lvl), 3), "chaos_clamped": lvl != raw,
                      "plateau": plateau, "push_applied": pushed, "attempts_counted": sk["n"],
                      "rating_is_provisional": sk["n"] < 10, "source": pool.source}))


def calibration(atts):
    pa = [x for x in atts if x.get("p") is not None and not x["wild"]]
    if not pa:
        return None
    return {"n": len(pa),
            "brier": round(sum((x["p"] - x["result"]) ** 2 for x in pa) / len(pa), 3),
            "bias": round(sum(x["p"] for x in pa) / len(pa) - sum(x["result"] for x in pa) / len(pa), 3)}


def report_data(led):
    atts, cal = led["attempts"], calibration(led["attempts"])
    out = {"amp": led["amp"], "attempts": len(atts), "wild_attempts": sum(1 for x in atts if x["wild"]),
           "skills": {}}
    for name, sk in led["skills"].items():
        cleared = [x["level"] for x in atts if x["skill"] == name and x["result"] == 1 and not x["wild"]]
        out["skills"][name] = {"level_est": round((sk["rating"] - BASE) / 100, 2), "counted": sk["n"],
                               "provisional": sk["n"] < 10,
                               "highest_cleared": max(cleared) if cleared else None,
                               "clears_at_highest": cleared.count(max(cleared)) if cleared else 0,
                               "plateau": is_plateau(led, name)}
    if cal:
        cal["read"] = ("too few predictions to judge (need 10)" if cal["n"] < 10 else
                       "overconfident: you predict more success than you get" if cal["bias"] > 0.10 else
                       "underconfident: you succeed more than you predict" if cal["bias"] < -0.10 else
                       "predictions within +/-0.10 of outcomes")
        cal["caveat"] = "predicting may itself act as retrieval practice; calibration is not shown to raise learning"
    out["calibration"] = cal
    return out


def cmd_report(a):
    o = report_data(load(a.dir))
    if not a.text:
        return print(json.dumps(o, indent=2))
    lines = ["Amplitude %d, %d attempts (%d wildcard)" % (o["amp"], o["attempts"], o["wild_attempts"])]
    for n, s in o["skills"].items():
        hc = "none yet" if s["highest_cleared"] is None else "level %s (x%d)" % (s["highest_cleared"], s["clears_at_highest"])
        lines.append("  %s: est level %.2f over %d counted%s; highest cleared %s%s" % (
            n, s["level_est"], s["counted"], " (provisional)" if s["provisional"] else "", hc,
            "; PLATEAU" if s["plateau"] else ""))
    c = o["calibration"]
    if c:
        lines.append("Calibration: n=%d brier=%.3f bias=%+.3f - %s" % (c["n"], c["brier"], c["bias"], c["read"]))
    print("\n".join(lines))


# ---------- the self-test: balanced blocks, no adaptive allocation ----------
def next_arm(led, pool):
    """Blocks of four: two control (0), two chaos (current amplitude), shuffled. Results never steer allocation."""
    if not led["block"]:
        led["block"] = pool.shuffle([0, 0, max(AMP_MIN, led["amp"]), max(AMP_MIN, led["amp"])])
    return led["block"].pop()


def session_series(led):
    by = {}
    for x in led["attempts"]:
        if not x.get("wild") and x.get("arm") is not None and x.get("session") is not None:
            by.setdefault(x["session"], (x["arm"], []))[1].append(x["result"] - x["expected"])
    return [(s, arm, sum(rs) / len(rs)) for s, (arm, rs) in sorted(by.items())]


def tune_data(led):
    ser = session_series(led)
    c = [m for _, arm, m in ser if arm == 0]
    h = [m for _, arm, m in ser if arm > 0]
    out = {"control_sessions": len(c), "chaos_sessions": len(h)}
    if min(len(c), len(h)) < MIN_PER_ARM:
        out["read"] = "no estimate yet: need %d sessions per arm (have %d control, %d chaos)" % (MIN_PER_ARM, len(c), len(h))
        return out

    def var(xs):
        m = sum(xs) / len(xs)
        return max(sum((x - m) ** 2 for x in xs) / (len(xs) - 1), 1e-6)
    diff = sum(h) / len(h) - sum(c) / len(c)
    se = math.sqrt(var(h) / len(h) + var(c) / len(c))
    lo, hi = diff - 1.645 * se, diff + 1.645 * se
    mc, mh = sum(c) / len(c), sum(h) / len(h)
    e = [m - (mc if arm == 0 else mh) for _, arm, m in ser]
    den = sum(x * x for x in e)
    r1 = sum(e[i] * e[i + 1] for i in range(len(e) - 1)) / den if den else 0.0
    out.update({"chaos_minus_control": round(diff, 4), "ci90": [round(lo, 4), round(hi, 4)],
                "interval_excludes_zero": lo > 0 or hi < 0, "lag1_autocorr": round(r1, 2)})
    warn = ["descriptive only: carryover between sessions, order effects and novelty are not modelled",
            "the learner can often infer the arm from plan changes, so blinding is partial"]
    if abs(r1) > 0.3:
        warn.append("sessions are serially correlated: the interval is too narrow")
    out["caveats"] = warn
    return out


def cmd_tune(a):
    led = load(a.dir)
    if a.tcmd == "pick":
        pool = Pool(a.source).ensure()
        arm = next_arm(led, pool)
        led["session"] += 1
        did, commit = seal(led, [arm], arm, pool.source, "tune", {"kind": "arm"})
        led["active"] = {"arm": arm, "draw": did, "session": led["session"]}
        save(a.dir, led)
        out = {"session": led["session"], "draw": did, "commit": commit, "source": pool.source, "sealed": True}
        if a.open:
            out["arm"] = arm
        print(json.dumps(out))
        if not a.open:
            print(json.dumps({"arm": arm}), file=sys.stderr)
    elif a.tcmd == "report":
        print(json.dumps(tune_data(led), indent=2))
    else:
        led["active"] = None
        save(a.dir, led)
        print(json.dumps({"active": None}))


def cmd_retro(a):
    led = load(a.dir)
    rep, tune, props = report_data(led), tune_data(led), []
    props.append("experiment: " + (tune["read"] if "read" in tune else
                 "chaos minus control %+.3f, 90%% interval %s (%s)" % (
                     tune["chaos_minus_control"], tune["ci90"],
                     "excludes zero" if tune["interval_excludes_zero"] else "includes zero")))
    for n, s in rep["skills"].items():
        if s["plateau"]:
            props.append("%s has plateaued: try `next --skill %s --push` and a wildcard" % (n, n))
        if s["provisional"]:
            props.append("%s rating is provisional (under 10 counted attempts)" % n)
    c = rep["calibration"]
    if c and c["n"] >= 10 and c["bias"] > 0.10:
        props.append("overconfident by %.2f: predict lower, or take an easier level" % c["bias"])
    if not os.environ.get("ANU_QRNG_API_KEY"):
        props.append("optional: ANU_QRNG_API_KEY (free key) adds quantum provenance; it does not improve the dice")
    print(json.dumps({"report": rep, "tune": tune, "proposals": props}, indent=2))


def cmd_entropy(a):
    key = os.environ.get("ANU_QRNG_API_KEY")
    qb, why = anu_bytes(1024, key) if key else (None, "no ANU_QRNG_API_KEY set")
    print(json.dumps({"quantum_live": qb is not None, "tier": "quantum-mixed" if qb else "os-csprng",
                      "note_if_not_live": None if qb else why,
                      "os_health": health(secrets.token_bytes(4096)),
                      "qrng_health": health(qb) if qb else None,
                      "advice": "Say quantum only when quantum_live is true. Health tests are screens, not certification."},
                     indent=2))


def cmd_feedback(a):
    led, old = load(a.dir), None
    old = led["amp"]
    led["amp"] = max(AMP_MIN, min(AMP_MAX, old + a.outcome))
    led["history"].append({"t": int(time.time()), "outcome": a.outcome, "note": a.note or "",
                           "amp_before": old, "amp_after": led["amp"]})
    save(a.dir, led)
    print(json.dumps({"amp": led["amp"], "was": old}))


def cmd_status(a):
    led = load(a.dir)
    print(json.dumps({"version": VERSION, "amp": led["amp"], "experiment_active": bool(led["active"]),
                      "sessions": led["session"], "draws": len(led["draws"]),
                      "unrevealed": [k for k, v in led["draws"].items() if not v["revealed"]],
                      "skills": list(led["skills"])}))


def build():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".chaos")
    ap.add_argument("--source", default="auto", choices=["auto", "os"])
    sp = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn):
        p = sp.add_parser(name); p.set_defaults(f=fn); return p
    p = add("draw", cmd_draw); p.add_argument("--n", type=int, default=3); p.add_argument("--amp", type=int)
    p.add_argument("--label"); p.add_argument("--sealed", action="store_true")
    p = add("reveal", cmd_reveal); p.add_argument("id")
    p = add("plan", cmd_plan); p.add_argument("--dial", action="append", required=True)
    p.add_argument("--step", type=float, default=1.0); p.add_argument("--amp", type=int)
    p.add_argument("--label"); p.add_argument("--sealed", action="store_true")
    p = add("shuffle", cmd_shuffle); p.add_argument("--items")
    p = add("drift", cmd_drift); p.add_argument("--n", type=int, default=7); p.add_argument("--amp", type=float, default=2.0)
    p = add("wildcard", cmd_wildcard); p.add_argument("--n", type=int, default=1)
    p = add("log", cmd_log); p.add_argument("--skill", required=True)
    p.add_argument("--level", type=float, required=True); p.add_argument("--result", type=int, choices=[0, 1], required=True)
    p.add_argument("--p", type=float); p.add_argument("--wild", action="store_true"); p.add_argument("--note")
    p = add("next", cmd_next); p.add_argument("--skill", required=True)
    p.add_argument("--target", type=float, default=0.75); p.add_argument("--floor", type=float, default=0.55)
    p.add_argument("--ceiling", type=float, default=0.95); p.add_argument("--amp", type=int)
    p.add_argument("--push", action="store_true")
    p = add("report", cmd_report); p.add_argument("--text", action="store_true")
    t = add("tune", cmd_tune)
    ts = t.add_subparsers(dest="tcmd", required=True)
    q = ts.add_parser("pick"); q.set_defaults(f=cmd_tune); q.add_argument("--open", action="store_true")
    ts.add_parser("report").set_defaults(f=cmd_tune)
    ts.add_parser("clear").set_defaults(f=cmd_tune)
    add("retro", cmd_retro)
    add("entropy", cmd_entropy)
    p = add("feedback", cmd_feedback); p.add_argument("outcome", type=int, choices=[-1, 0, 1]); p.add_argument("--note")
    add("status", cmd_status)
    return ap


def main(argv=None):
    a = build().parse_args(argv)
    if a.source == "os":
        os.environ.pop("ANU_QRNG_API_KEY", None)
    if getattr(a, "p", None) is not None and not 0 <= a.p <= 1:
        sys.exit("--p must be between 0 and 1")
    for nm in ("target", "floor", "ceiling"):
        v = getattr(a, nm, None)
        if v is not None and not 0 < v < 1:
            sys.exit("--%s must be between 0 and 1 (exclusive)" % nm)
    if getattr(a, "n", None) is not None and a.n < 1:
        sys.exit("--n must be positive")
    a.f(a)


if __name__ == "__main__":
    main()
