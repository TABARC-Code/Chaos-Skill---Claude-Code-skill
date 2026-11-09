#!/usr/bin/env python3
"""Smoke tests for chaos.py v3. Run: python3 -W error -I tests/test_chaos.py"""
import contextlib, io, json, os, random, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
os.environ.pop("ANU_QRNG_API_KEY", None)
import chaos  # noqa: E402


def run(d, *args):
    """Run a command, return (stdout json-lines, stderr text)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        chaos.main(["--dir", d] + [str(x) for x in args])
    dec, s, docs, i = json.JSONDecoder(), out.getvalue(), [], 0
    while i < len(s):          # some commands print indented, multi-line JSON
        if s[i].isspace():
            i += 1
            continue
        obj, i = dec.raw_decode(s, i)
        docs.append(obj)
    return docs, err.getvalue()


def rj(p):
    with open(p) as f:
        return json.load(f)


def wj(p, o):
    with open(p, "w") as f:
        json.dump(o, f)


class T(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.d = self.t.name

    def tearDown(self):
        self.t.cleanup()

    def test_below_unbiased(self):
        p = chaos.Pool("os")
        c = [0] * 7
        for _ in range(7000):
            c[p.below(7)] += 1
        self.assertTrue(all(800 < x < 1200 for x in c), c)

    def test_below_large_span(self):
        self.assertTrue(0 <= chaos.Pool("os").below(10**6) < 10**6)

    def test_health_catches_constant_and_passes_random(self):
        self.assertFalse(chaos.health(b"\x00" * 4096)["pass"])
        self.assertFalse(chaos.health(b"\xaa" * 4096)["pass"])
        self.assertTrue(chaos.health(random.Random(1).randbytes(4096))["pass"])

    def test_no_key_is_os_only(self):
        _, src = chaos.get_bytes(8)
        self.assertEqual(src, "os-csprng")

    def test_failed_anu_never_claims_quantum(self):
        os.environ["ANU_QRNG_API_KEY"] = "x"
        old = chaos.anu_bytes
        chaos.anu_bytes = lambda n, k: (None, "boom")
        try:
            _, src = chaos.get_bytes(8)
        finally:
            chaos.anu_bytes = old
            os.environ.pop("ANU_QRNG_API_KEY")
        self.assertTrue(src.startswith("os-csprng (anu-aqn unavailable"))
        self.assertNotIn("quantum", src)

    def test_good_anu_is_mixed_not_raw(self):
        os.environ["ANU_QRNG_API_KEY"] = "x"
        old = chaos.anu_bytes
        chaos.anu_bytes = lambda n, k: (b"\x00" * n, None)   # XOR with zeros = the OS bytes
        try:
            _, src = chaos.get_bytes(8)
        finally:
            chaos.anu_bytes = old
            os.environ.pop("ANU_QRNG_API_KEY")
        self.assertEqual(src, "quantum-mixed(anu-aqn+os-csprng)")

    def test_sealed_draw_hides_values_and_reveal_verifies(self):
        o, e = run(self.d, "draw", "--n", 4, "--amp", 3, "--sealed")
        self.assertNotIn("values", json.dumps(o))
        self.assertEqual(e, "")
        r, _ = run(self.d, "reveal", o[0]["id"])
        self.assertTrue(r[0]["commit_ok"])
        self.assertEqual(len(r[0]["values"]), 4)
        self.assertTrue(all(-3 <= v <= 3 for v in r[0]["values"]))

    def test_tamper_detected(self):
        o, _ = run(self.d, "draw", "--sealed")
        led = rj(os.path.join(self.d, "ledger.json"))
        led["draws"][o[0]["id"]]["payload"] = json.dumps({"values": [9], "nonce": "x"})
        wj(os.path.join(self.d, "ledger.json"), led)
        r, _ = run(self.d, "reveal", o[0]["id"])
        self.assertFalse(r[0]["commit_ok"])

    def test_amp_zero_gives_zeros(self):
        run(self.d, "draw", "--n", 5, "--amp", 0)
        r, _ = run(self.d, "reveal", [k for k in rj(os.path.join(self.d, "ledger.json"))["draws"]][0])
        self.assertEqual(r[0]["values"], [0] * 5)

    def test_plan_clamps_to_range(self):
        o, _ = run(self.d, "plan", "--dial", "mins:10:30:30", "--dial", "n:1:5:1", "--amp", 5, "--step", 10, "--sealed")
        r, _ = run(self.d, "reveal", o[0]["id"])
        for d in r[0]["dials"]:
            lo, hi = (10, 30) if d["dial"] == "mins" else (1, 5)
            self.assertTrue(lo <= d["to"] <= hi, d)

    def test_shuffle_is_permutation(self):
        o, _ = run(self.d, "shuffle", "--items", "a,b,c,d,e")
        self.assertEqual(sorted(o[0]["order"]), list("abcde"))

    def test_drift_bounded(self):
        o, _ = run(self.d, "drift", "--n", 50, "--amp", 2)
        self.assertTrue(all(abs(x) <= 2 for x in o[0]["drift"]))

    def test_wildcards_unique(self):
        o, _ = run(self.d, "wildcard", "--n", 5)
        self.assertEqual(len(set(o[0]["wildcards"])), 5)

    def test_log_rating_moves_and_wild_does_not_count(self):
        o, _ = run(self.d, "log", "--skill", "s", "--level", 5, "--result", 1)
        self.assertGreater(o[0]["level_est"], 4.0)
        led = rj(os.path.join(self.d, "ledger.json"))
        before = led["skills"]["s"]["rating"]
        run(self.d, "log", "--skill", "s", "--level", 9, "--result", 0, "--wild")
        led = rj(os.path.join(self.d, "ledger.json"))
        self.assertEqual(led["skills"]["s"]["rating"], before)
        self.assertEqual(led["skills"]["s"]["n"], 1)

    def test_next_respects_safe_band(self):
        for _ in range(3):
            run(self.d, "log", "--skill", "s", "--level", 4, "--result", 1)
        for _ in range(20):
            o, _ = run(self.d, "next", "--skill", "s", "--amp", 5)
            self.assertGreaterEqual(o[0]["expected_success"], 0.55 - 0.02)
            self.assertLessEqual(o[0]["expected_success"], 0.95 + 0.02)

    def test_provisional_flag(self):
        o, _ = run(self.d, "next", "--skill", "new")
        self.assertTrue(o[0]["rating_is_provisional"])

    def test_damping_after_misses_but_not_during_experiment(self):
        run(self.d, "log", "--skill", "s", "--level", 5, "--result", 0)
        run(self.d, "log", "--skill", "s", "--level", 5, "--result", 0)
        o, _ = run(self.d, "log", "--skill", "s", "--level", 5, "--result", 0)
        self.assertIn("damped", o[0]["note"])
        run(self.d, "tune", "pick")
        led = rj(os.path.join(self.d, "ledger.json"))
        amp = led["amp"]
        for _ in range(3):
            o, _ = run(self.d, "log", "--skill", "t", "--level", 5, "--result", 0)
        self.assertIsNone(o[0]["note"])
        self.assertEqual(rj(os.path.join(self.d, "ledger.json"))["amp"], amp)

    def test_blocks_are_balanced_and_hidden(self):
        arms = []
        for _ in range(8):
            o, e = run(self.d, "tune", "pick")
            self.assertNotIn("arm", o[0])
            arms.append(json.loads(e)["arm"])
        self.assertEqual(sum(1 for a in arms[:4] if a == 0), 2)
        self.assertEqual(sum(1 for a in arms[4:] if a == 0), 2)

    def test_tune_needs_replicates(self):
        o, _ = run(self.d, "tune", "report")
        self.assertIn("no estimate yet", o[0]["read"])

    def _tune_on_synthetic(self, effect, seed):
        led = chaos.load(self.d)
        led["attempts"] = []
        rng = random.Random(seed)
        for s in range(1, 25):
            arm = 0 if s % 2 else 2
            for _ in range(10):
                led["attempts"].append({"skill": "s", "level": 5, "result": int(rng.random() < 0.6 + (effect if arm else 0)),
                                        "expected": 0.6, "arm": arm, "session": s, "wild": False})
        chaos.save(self.d, led)
        return run(self.d, "tune", "report")[0][0]

    def test_tune_detects_a_planted_effect(self):
        big = self._tune_on_synthetic(0.25, 7)
        self.assertGreater(big["chaos_minus_control"], 0.1)
        self.assertTrue(big["interval_excludes_zero"])
        self.assertIn("caveats", big)

    def test_tune_false_positive_rate_on_pure_noise(self):
        # nominal 10% for a 90% interval; allow slack for 60 runs. Descriptive, not a guarantee.
        hits = sum(self._tune_on_synthetic(0.0, sd)["interval_excludes_zero"] for sd in range(60))
        self.assertLess(hits / 60, 0.25, hits)

    def test_clear_ends_experiment(self):
        run(self.d, "tune", "pick")
        run(self.d, "tune", "clear")
        self.assertFalse(run(self.d, "status")[0][0]["experiment_active"])

    def test_plateau_and_push(self):
        led = chaos.load(self.d)
        led["skills"]["s"] = {"rating": 1000.0, "n": 12}
        led["attempts"] = [{"skill": "s", "level": 4, "result": 1, "wild": False, "rating_after": 1000.0}] * 12
        chaos.save(self.d, led)
        o, _ = run(self.d, "next", "--skill", "s", "--push")
        self.assertTrue(o[0]["plateau"] and o[0]["push_applied"])
        self.assertLess(o[0]["target_success"], 0.75)

    def test_calibration_reads(self):
        for _ in range(10):
            run(self.d, "log", "--skill", "s", "--level", 5, "--result", 0, "--p", 0.9)
        o, _ = run(self.d, "report")
        self.assertIn("overconfident", o[0]["calibration"]["read"])

    def test_feedback_clamps(self):
        for _ in range(10):
            run(self.d, "feedback", 1)
        self.assertEqual(run(self.d, "status")[0][0]["amp"], chaos.AMP_MAX)

    def test_bad_args_rejected(self):
        for args in (["log", "--skill", "s", "--level", 3, "--result", 1, "--p", 2],
                     ["next", "--skill", "s", "--target", 1.5], ["draw", "--n", 0]):
            with self.assertRaises(SystemExit):
                run(self.d, *args)

    def test_entropy_without_key_says_not_quantum(self):
        o, _ = run(self.d, "entropy")
        self.assertFalse(o[0]["quantum_live"])
        self.assertEqual(o[0]["tier"], "os-csprng")

    def test_retro_runs_on_empty(self):
        o, _ = run(self.d, "retro")
        self.assertIn("proposals", o[0])


if __name__ == "__main__":
    unittest.main()
