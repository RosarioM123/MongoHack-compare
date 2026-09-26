"""Tests for the brain: classifier, skills, counterfactual lessons (Prompt 2)."""
import os
import tempfile
import unittest

os.environ["DEV_DB"] = os.path.join(tempfile.mkdtemp(), "test_brain.sqlite")

import architectures  # noqa: E402
import db as db_module  # noqa: E402
import loop  # noqa: E402
from evolver import (  # noqa: E402
    analyze_failure,
    classify,
    get_validated_lessons,
    propose_mutation,
)
from evolver.patterns import find_patterns  # noqa: E402
from skills import (  # noqa: E402
    compose,
    ensure_seed_skills,
    expand_component,
    get_skill,
    list_skills,
)


def fresh_db():
    return db_module.get_db()


def failed_trace(**over):
    base = {
        "trace_id": "t1", "task_id": "pick-and-deliver", "success": False,
        "actions": ["forward"] * 10,
        "metrics": {"bumps": 0, "max_steps": 140, "steps": 10,
                    "learned_blocked": []},
    }
    base["metrics"].update(over.pop("metrics", {}))
    base.update(over)
    return base


class TestClassifier(unittest.TestCase):
    def setUp(self):
        self.arch = architectures.v0()

    def test_success_is_none(self):
        t = failed_trace(success=True)
        self.assertIsNone(classify(t, self.arch))

    def test_perception_error(self):
        t = failed_trace(metrics={"picked_wrong_kind": True})
        self.assertEqual(classify(t, self.arch), "perception_error")

    def test_tool_selection_error(self):
        t = failed_trace(metrics={"failed_picks": 2})
        self.assertEqual(classify(t, self.arch), "tool_selection_error")

    def test_verification_error(self):
        t = failed_trace(metrics={"bumps": 5})
        self.assertEqual(classify(t, self.arch), "verification_error")

    def test_no_verification_error_when_verifier_present(self):
        arch = dict(self.arch, verification_strategy=["collision_check"])
        t = failed_trace(metrics={"bumps": 5})
        self.assertNotEqual(classify(t, arch), "verification_error")

    def test_planning_error_on_timeout(self):
        t = failed_trace(actions=["wait"] * 140,
                         metrics={"bumps": 0, "max_steps": 140, "steps": 140})
        self.assertEqual(classify(t, self.arch), "planning_error")

    def test_memory_error_on_relearning(self):
        prev = failed_trace(trace_id="t0",
                            metrics={"learned_blocked": [[4, 3]]})
        now = failed_trace(trace_id="t1",
                           metrics={"learned_blocked": [[4, 3]]})
        self.assertEqual(classify(now, self.arch, history=[prev]), "memory_error")

    def test_execution_error_fallback(self):
        arch = dict(self.arch, verification_strategy=["collision_check"])
        t = failed_trace(metrics={"bumps": 2})  # verifier present, no timeout
        self.assertEqual(classify(t, arch), "execution_error")


class TestSkills(unittest.TestCase):
    def test_get_skill(self):
        s = get_skill("collision_check")
        self.assertEqual(s["kind"], "verifier")
        self.assertIn("navigation", s["prerequisites"])

    def test_unknown_skill_raises(self):
        with self.assertRaises(ValueError):
            get_skill("teleport")

    def test_list_skills(self):
        self.assertIn("spatial_memory", list_skills())

    def test_compose_ok(self):
        s = compose(["navigation", "collision_check", "spatial_memory"],
                    "careful-navigation")
        self.assertEqual(s["strategy_name"], "careful-navigation")

    def test_compose_missing_prerequisite_raises(self):
        with self.assertRaises(ValueError):
            compose(["collision_check"], "bad")  # needs navigation

    def test_expand_strategy(self):
        out = expand_component("careful-navigation")
        self.assertIn("collision_check", out["verifiers"])
        self.assertIn("spatial_memory", out["modules"])
        self.assertIn("navigation", out["tools"])

    def test_strategy_expands_in_mutation(self):
        parent = architectures.v0()
        child = architectures.apply_mutation(parent, {
            "mutation_type": "ADD_MODULE",
            "target": "navigation",
            "reason": "test",
            "expected_effect": "test",
            "new_component": "careful-navigation",
            "parent_version": "v0",
        })
        self.assertIn("spatial_memory", child["active_modules"])
        self.assertIn("collision_check", child["verification_strategy"])


class TestCounterfactual(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()
        self.arch = architectures.v0()

    def test_lesson_recommends_missing_verifier(self):
        t = failed_trace(metrics={"bumps": 5})
        t["failure_category"] = "verification_error"
        lesson = analyze_failure(t, self.arch)
        self.assertEqual(lesson["recommended_component"], "collision_check")
        self.assertEqual(lesson["confidence"], "high")
        self.assertEqual(lesson["status"], "proposed")
        self.assertIn("counterfactual", lesson)

    def test_no_lesson_on_success(self):
        t = failed_trace(success=True)
        self.assertIsNone(analyze_failure(t, self.arch))

    def test_lesson_validated_when_mutation_adopted(self):
        loop.run_generations(self.db, ["pick-and-deliver"], [7, 8], 1)
        validated = self.db.find("lessons", {"task_id": "pick-and-deliver",
                                             "status": "validated"})
        self.assertGreater(len(validated), 0)
        self.assertTrue(all(l["recommended_component"] == "collision_check"
                            for l in validated))

    def test_validated_lessons_consulted(self):
        if not self.db.find("lessons", {"status": "validated"}):
            loop.run_generations(self.db, ["pick-and-deliver"], [7, 8], 1)
        arch = architectures.get_version(self.db, "v1") or architectures.v0()
        trace, _ = loop.run_episode(self.db, arch, "pick-and-deliver", 7,
                                    persist=True)
        consulted = trace["context"]["lessons_consulted"]
        self.assertGreater(len(consulted), 0)
        self.assertIn("replan", consulted[0].lower())

    def test_skill_metrics_recorded(self):
        ensure_seed_skills(self.db)
        loop.run_episode(self.db, architectures.v0(), "pick-and-deliver", 7,
                         persist=True)
        nav = self.db.find_one("skills", {"name": "navigation", "type": "skill"})
        self.assertGreater(nav["success_count"] + nav["failure_count"], 0)


class TestProposerGuards(unittest.TestCase):
    def test_no_duplicate_verifier_proposal(self):
        db = fresh_db()
        arch = architectures.v0()
        arch["verification_strategy"] = ["collision_check"]
        pattern = {"kind": "repeated_failure", "failure_category": "verification_error",
                   "task_id": "pick-and-deliver", "trace_ids": ["a", "b"], "count": 2}
        self.assertIsNone(propose_mutation(pattern, arch))

    def test_planning_timeout_proposes_policy_change(self):
        arch = architectures.v0()
        t = failed_trace(trace_id="a", actions=["wait"] * 140,
                         metrics={"bumps": 0, "max_steps": 140, "steps": 140})
        t["failure_category"] = "planning_error"
        pattern = {"kind": "repeated_failure", "failure_category": "planning_error",
                   "task_id": "t", "trace_ids": ["a"], "count": 2}
        m = propose_mutation(pattern, arch, traces=[t])
        self.assertEqual(m["mutation_type"], "MODIFY_POLICY")
        self.assertGreater(m["changes"]["max_steps"], 140)

    def test_get_validated_lessons_empty_initially(self):
        db = fresh_db()
        self.assertEqual(get_validated_lessons(db, "nope"), [])


if __name__ == "__main__":
    unittest.main()
