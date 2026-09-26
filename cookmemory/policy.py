"""One bounded adaptive policy change: propose -> held-out validate -> versioned promote.

This is the recursive-harnessing loop in miniature. The only rule template the
harness understands is `strict_order`: completed steps must respect the `requires`
task graph, otherwise an order issue is opened. Proposals are gated on measured
dev errors and promotion requires no regression on held-out recordings.
"""

import json
from pathlib import Path

POLICY_PATH = Path("work/policy.json")
HISTORY_PATH = Path("work/policy-history.jsonl")
ORDER_MISSED_THRESHOLD = 2


def base_policy():
    return {"version": 0, "strict_order": False, "requires": {}}


def load_policy(path=POLICY_PATH):
    path = Path(path)
    if not path.exists():
        return base_policy()
    policy = json.loads(path.read_text())
    if not isinstance(policy, dict):
        raise ValueError("Policy file must contain a JSON object")
    return policy


def propose_change(dev_metrics, current, requires):
    """Propose one bounded change from measured dev errors.

    dev_metrics: evaluator output with an 'order_missed' count.
    requires: {step: [prerequisites]} taken from the recipe task graph.
    Returns (new_policy, rationale) or (None, reason_no_change).
    """
    if current.get("strict_order"):
        return None, "strict_order already active; no further change proposed"
    missed = dev_metrics.get("order_missed", 0)
    if missed < ORDER_MISSED_THRESHOLD:
        return None, f"order_missed={missed} below threshold {ORDER_MISSED_THRESHOLD}; no change warranted"
    new = {
        "version": current.get("version", 0) + 1,
        "strict_order": True,
        "requires": requires,
        "rationale": f"{missed} missed order-tagged errors on dev; requiring prerequisite evidence.",
    }
    return new, new["rationale"]


def validate_change(baseline, candidate, heldout_baseline, heldout_candidate):
    """Candidate must improve-or-hold on dev and never regress on held-out."""
    checks = {
        "dev_missed_no_worse": candidate["missed"] <= baseline["missed"],
        "dev_false_alarms_no_worse": candidate["false_alarms"] <= baseline["false_alarms"],
        "heldout_missed_no_worse": heldout_candidate["missed"] <= heldout_baseline["missed"],
        "heldout_false_alarms_no_worse": heldout_candidate["false_alarms"] <= heldout_baseline["false_alarms"],
        "dev_missed_improved": candidate["missed"] < baseline["missed"],
    }
    return all(checks.values()), checks


def promote(policy, validation_report, path=POLICY_PATH, history=HISTORY_PATH):
    """Versioned promotion. Only call after validate_change returns True."""
    path, history = Path(path), Path(history)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2) + "\n")
    record = {"version": policy["version"], "policy": policy, "validation": validation_report}
    with history.open("a") as target:
        target.write(json.dumps(record) + "\n")
    return path
