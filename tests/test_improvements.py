import json
import tempfile
import unittest
from pathlib import Path

from cookmemory.evaluate import compare, markdown_table, score
from cookmemory.harness import advance
from cookmemory.policy import base_policy, promote, propose_change, validate_change
from cookmemory.render import render
from cookmemory.verify_atlas import summarize


def event(n, **extra):
    return {"event_id": str(n), "recording_id": "r", "timestamp": n,
            "observation": "Observed action", **extra}


def decisions_fixture():
    state = None
    decisions = []
    events = [
        event(1, issue={"id": "u", "description": "Unverified"}),
        event(2),
        event(3),
        event(4, resolves=["u"]),
    ]
    for e in events:
        state, d = advance(state, e)
        decisions.append(d)
    return decisions


class EvaluateTests(unittest.TestCase):
    def test_score_memory_catches_and_survives(self):
        labels = [
            {"recording_id": "r", "start_time": 1.5, "end_time": 3.5,
             "errors": [{"tag": "order"}], "evaluation_only": True},
            {"recording_id": "r", "start_time": 2.0, "end_time": 2.5,
             "errors": [], "evaluation_only": True},
        ]
        metrics = score(decisions_fixture(), labels)
        self.assertEqual(metrics["caught"], 1)
        self.assertEqual(metrics["missed"], 0)
        self.assertEqual(metrics["false_alarms"], 1)
        self.assertAlmostEqual(metrics["issue_survival"], 1.0)

    def test_score_stateless_misses(self):
        state, decisions = None, []
        for e in [event(1, issue={"id": "u", "description": "Unverified"}), event(2), event(3)]:
            state, d = advance(state, e, "stateless")
            decisions.append(d)
        labels = [{"recording_id": "r", "start_time": 1.5, "end_time": 3.5,
                   "errors": [{"tag": "order"}], "evaluation_only": True}]
        metrics = score(decisions, labels)
        self.assertEqual(metrics["missed"], 1)
        self.assertIsNone(metrics["issue_survival"])

    def test_compare_returns_both_modes(self):
        events = [event(1, issue={"id": "u", "description": "Unverified"}), event(2)]
        results = compare(events, [])
        self.assertIn("memory", results)
        self.assertIn("stateless", results)
        table = markdown_table("memory", results["memory"]["metrics"],
                               "stateless", results["stateless"]["metrics"])
        self.assertIn("| metric | memory | stateless |", table)


class PolicyTests(unittest.TestCase):
    def test_strict_order_opens_issue(self):
        policy = {"version": 1, "strict_order": True, "requires": {"step-b": ["step-a"]}}
        state, decision = advance(None, event(1, completed_steps=["step-b"]), policy=policy)
        self.assertIn("order:step-b", decision["open_issues"])
        self.assertEqual(decision["action"], "request_verification")

    def test_no_policy_no_issue(self):
        state, decision = advance(None, event(1, completed_steps=["step-b"]))
        self.assertEqual(decision["open_issues"], {})
        self.assertEqual(decision["action"], "continue_observing")

    def test_prerequisite_satisfied_no_issue(self):
        policy = {"version": 1, "strict_order": True, "requires": {"step-b": ["step-a"]}}
        state, _ = advance(None, event(1, completed_steps=["step-a"]), policy=policy)
        _, decision = advance(state, event(2, completed_steps=["step-b"]), policy=policy)
        self.assertNotIn("order:step-b", decision["open_issues"])

    def test_propose_gated_on_threshold(self):
        new_policy, _ = propose_change({"order_missed": 1}, base_policy(), {"b": ["a"]})
        self.assertIsNone(new_policy)
        new_policy, rationale = propose_change({"order_missed": 2}, base_policy(), {"b": ["a"]})
        self.assertEqual(new_policy["version"], 1)
        self.assertTrue(new_policy["strict_order"])
        self.assertIn("2 missed", rationale)

    def test_no_double_propose(self):
        current = {"version": 1, "strict_order": True, "requires": {}}
        new_policy, _ = propose_change({"order_missed": 5}, current, {})
        self.assertIsNone(new_policy)

    def test_validate_requires_improvement_and_no_heldout_regression(self):
        base = {"missed": 1, "false_alarms": 0}
        cand = {"missed": 0, "false_alarms": 0}
        ok, _ = validate_change(base, cand, base, cand)
        self.assertTrue(ok)
        regressed = {"missed": 0, "false_alarms": 1}
        ok, checks = validate_change(base, cand, base, regressed)
        self.assertFalse(ok)
        self.assertFalse(checks["heldout_false_alarms_no_worse"])

    def test_promote_writes_versioned_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            history = Path(directory) / "history.jsonl"
            policy = {"version": 1, "strict_order": True, "requires": {"b": ["a"]}}
            promote(policy, {"dev_missed_improved": True}, path, history)
            self.assertEqual(json.loads(path.read_text())["version"], 1)
            self.assertEqual(json.loads(history.read_text().splitlines()[0])["version"], 1)


class RenderTests(unittest.TestCase):
    def test_render_writes_self_contained_page(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            events_path = directory / "events.jsonl"
            events_path.write_text(json.dumps(event(1, issue={"id": "u", "description": "Unverified"})) + "\n")
            memory_path = directory / "memory.jsonl"
            memory_path.write_text(json.dumps(
                {"event_id": "1", "timestamp": 1, "action": "request_verification",
                 "open_issues": {"u": {"description": "Unverified"}}, "completed_steps": []}) + "\n")
            out = render(events_path, memory_path, out_path=directory / "demo.html")
            page = out.read_text()
            self.assertIn("request_verification", page)
            self.assertNotIn("http", page.replace("http-equiv", ""))


class VerifyAtlasTests(unittest.TestCase):
    def test_summarize_counts_skips(self):
        first = [{"event_id": "1", "action": "request_verification"}]
        second = [{"event_id": "1", "status": "already_processed"},
                  {"event_id": "2", "action": "continue_observing"}]
        summary = summarize(first, second)
        self.assertEqual(summary["skipped_as_processed"], 1)
        self.assertEqual(summary["new_decisions"], 1)


if __name__ == "__main__":
    unittest.main()
