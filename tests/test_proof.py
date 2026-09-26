"""Tests for the proof: benchmark reproducibility, held-out generalization,
demo determinism, and the evolution visualization (Prompt 3)."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

os.environ["DEV_DB"] = os.path.join(tempfile.mkdtemp(), "test_proof.sqlite")

import db as db_module  # noqa: E402
import demo  # noqa: E402
import loop  # noqa: E402
from eval import benchmark as benchmark_mod  # noqa: E402
from eval import generalization as gen_mod  # noqa: E402
from viz import evolution as viz_mod  # noqa: E402


def scratch_db():
    path = os.path.join(tempfile.mkdtemp(), "scratch.sqlite")
    return db_module.SQLiteBackend(path)


def _gen_key(g):
    m = g.get("mutation") or {}
    return {
        "version": g["version"],
        "success_rate": g["success_rate"],
        "avg_steps": g["avg_steps"],
        "collisions": g["collisions"],
        "replans": g["replans"],
        "mutation_type": m.get("mutation_type"),
        "new_component": m.get("new_component"),
        "accepted": m.get("accepted"),
        "validation_passed": m.get("validation_passed"),
    }


class TestBenchmark(unittest.TestCase):
    def test_reproducible_same_seeds(self):
        kwargs = dict(tasks=["pick-and-deliver"], seeds=[7, 8],
                      generations=2, trials=1)
        r1 = benchmark_mod.run_benchmark(**kwargs)
        r2 = benchmark_mod.run_benchmark(**kwargs)
        k1 = [_gen_key(g) for g in r1["trial_reports"][0]["generations"]]
        k2 = [_gen_key(g) for g in r2["trial_reports"][0]["generations"]]
        self.assertEqual(k1, k2)

    def test_report_traces_to_stored_ids(self):
        db = scratch_db()
        history = loop.run_generations(db, ["pick-and-deliver"], [7, 8], 2)
        for g in history:
            for tid in g["trace_ids"]:
                self.assertIsNotNone(db.find_one("trajectories", {"trace_id": tid}))
            m = g.get("mutation")
            if m:
                self.assertIsNotNone(
                    db.find_one("mutations", {"mutation_id": m["mutation_id"]}))


class TestGeneralization(unittest.TestCase):
    def _evolved_db(self):
        db = scratch_db()
        loop.run_generations(db, ["pick-and-deliver", "multi-room-deliver"],
                             [7, 8], 3)
        return db

    def test_deterministic(self):
        r1 = gen_mod.run_generalization(self._evolved_db(), "maze-deliver", [21, 22])
        r2 = gen_mod.run_generalization(self._evolved_db(), "maze-deliver", [21, 22])
        for key in ("success_rate", "avg_steps", "frozen_version"):
            self.assertEqual(r1[key], r2[key], key)
        self.assertEqual(r1["skill_transfer"], r2["skill_transfer"])

    def test_held_out_succeeds_and_freezes_architecture(self):
        db = self._evolved_db()
        before = len(db.find("mutations", {}, limit=100000))
        report = gen_mod.run_generalization(db, "maze-deliver", [21, 22, 23])
        after = len(db.find("mutations", {}, limit=100000))
        self.assertEqual(before, after)
        self.assertEqual(report["success_rate"], 1.0)
        # Previously learned skills transferred to the unseen task.
        self.assertGreater(report["skill_transfer"]["collision_check_replans"], 0)
        self.assertTrue(report["skill_transfer"]["spatial_memory_active"])


class TestDemoAndViz(unittest.TestCase):
    def test_demo_runs_and_narrates(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            demo.main()
        out = buf.getvalue()
        self.assertIn("FINAL COMPARISON", out)
        self.assertIn("v0", out)
        self.assertIn("v2", out)

    def test_viz_writes_html(self):
        db = db_module.get_db()
        report = benchmark_mod.run_benchmark(
            ["pick-and-deliver"], [7, 8], 2, 1)
        db.save("evaluations", report)
        viz_mod.main()
        self.assertTrue(os.path.exists(viz_mod.OUT))
        with open(viz_mod.OUT) as f:
            html = f.read()
        self.assertIn("Success rate", html)
        self.assertIn("<svg", html)
        os.remove(viz_mod.OUT)


if __name__ == "__main__":
    unittest.main()
