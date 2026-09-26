"""Tests for the recursive harness foundation (Prompt 1)."""
import os
import tempfile
import unittest

os.environ["DEV_DB"] = os.path.join(tempfile.mkdtemp(), "test.sqlite")

import architectures  # noqa: E402
import db as db_module  # noqa: E402
import loop  # noqa: E402
from contracts import (  # noqa: E402
    COLLECTIONS,
    FAILURE_CATEGORIES,
    MUTATION_TYPES,
    Mutation,
    Trace,
)
from evolver import (  # noqa: E402
    classify,
    find_patterns,
    propose_mutation,
    validate,
)


def fresh_db():
    return db_module.get_db()


class TestContracts(unittest.TestCase):
    def test_trace_has_required_fields(self):
        t = Trace(trace_id="x", task_id="t", environment_id="e",
                  harness_version="v0", seed=1)
        d = t.to_dict()
        for f in ("observations", "selected_tools", "context", "plan", "actions",
                  "outcome", "success", "failure_category", "metrics",
                  "adaptation_proposed", "adaptation_accepted",
                  "resulting_harness_version"):
            self.assertIn(f, d)

    def test_mutation_types_and_categories_sane(self):
        self.assertIn("ADD_VERIFIER", MUTATION_TYPES)
        self.assertIn("verification_error", FAILURE_CATEGORIES)
        m = Mutation(mutation_id="m", mutation_type="ADD_VERIFIER", target="navigation",
                     reason="r", expected_effect="e", new_component="collision_check",
                     parent_version="v0")
        self.assertEqual(m.to_dict()["mutation_type"], "ADD_VERIFIER")

    def test_collections_cover_developmental_state(self):
        for c in ("experiences", "trajectories", "mutations", "architectures",
                  "evaluations", "failures"):
            self.assertIn(c, COLLECTIONS)


class TestSim(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()
        self.arch = architectures.v0()

    def _episode(self, task="pick-and-deliver", seed=7, arch=None):
        trace, _mem = loop.run_episode(self.db, arch or self.arch, task, seed,
                                       persist=False)
        return trace

    def test_deterministic(self):
        a = self._episode(seed=7)["actions"]
        b = self._episode(seed=7)["actions"]
        self.assertEqual(a, b)
        self.assertGreater(len(a), 10)

    def test_v0_fails_pick_and_deliver_with_verification_error(self):
        trace = self._episode(seed=7)
        self.assertFalse(trace["success"])
        self.assertEqual(trace["failure_category"], "verification_error")
        self.assertGreater(trace["metrics"]["bumps"], 0)

    def test_failure_emerges_not_scripted(self):
        # Same seed, different start position: still fails (capability gap,
        # not a scripted event).
        trace = self._episode(seed=8)
        self.assertFalse(trace["success"])


class TestEvolution(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()
        self.arch = architectures.ensure_v0(self.db)

    def test_pattern_to_mutation(self):
        traces = [loop.run_episode(self.db, self.arch, "pick-and-deliver", s,
                                   persist=False)[0] for s in (7, 8)]
        patterns = find_patterns(traces)
        kinds = [p["kind"] for p in patterns]
        self.assertIn("repeated_failure", kinds)
        mutation = propose_mutation(patterns[0], self.arch)
        self.assertEqual(mutation["mutation_type"], "ADD_VERIFIER")
        self.assertEqual(mutation["new_component"], "collision_check")

    def test_validator_accepts_real_improvement(self):
        traces = [loop.run_episode(self.db, self.arch, "pick-and-deliver", s,
                                   persist=False)[0] for s in (7, 8)]
        pattern = find_patterns(traces)[0]
        mutation = propose_mutation(pattern, self.arch)
        child = architectures.apply_mutation(self.arch, mutation)
        result = validate(self.db, self.arch, child, loop.run_episode)
        self.assertTrue(result["passed"], result)
        self.assertGreater(result["child"]["success_rate"],
                           result["parent"]["success_rate"])

    def test_two_generations_improve(self):
        history = loop.run_generations(self.db, ["pick-and-deliver"], [7, 8], 2)
        self.assertEqual(len(history), 2)
        self.assertLessEqual(history[0]["success_rate"], history[1]["success_rate"])
        versions = [d["version_id"] for d in
                    self.db.find("architectures", limit=50)]
        self.assertIn("v1", versions)
        v1 = architectures.get_version(self.db, "v1")
        self.assertIn("collision_check", v1["verification_strategy"])

    def test_architecture_reproducible(self):
        v1 = architectures.get_version(self.db, "v1")
        if v1 is None:  # ensure v1 exists via a quick evolution
            loop.run_generations(self.db, ["pick-and-deliver"], [7, 8], 1)
            v1 = architectures.get_version(self.db, "v1")
        t1, _ = loop.run_episode(self.db, v1, "pick-and-deliver", 7, persist=False)
        v1_reloaded = architectures.get_version(self.db, "v1")
        t2, _ = loop.run_episode(self.db, v1_reloaded, "pick-and-deliver", 7,
                                 persist=False)
        self.assertEqual(t1["actions"], t2["actions"])
        self.assertTrue(t2["success"])


if __name__ == "__main__":
    unittest.main()
