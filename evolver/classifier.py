"""Failure classifier: failed trace -> one of the 9 failure categories.

Deterministic rules over the trace, the architecture that ran it, and
optionally recent history. Categories with no observable signal in the
current sim (localization_error, context_error, task_decomposition_error)
are reserved: the rules that would trigger them are documented in
RESERVED_RULES instead of being faked.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# Documented trigger conditions for categories the current sim cannot
# produce (its overhead sensor localizes perfectly by design). If the sim
# gains partial observability, implement these here.
RESERVED_RULES = {
    "localization_error": "estimated pose diverges from true pose by > 1 cell "
                          "for 3+ consecutive steps",
    "context_error": "planner receives observations older than the context "
                     "window allow",
    "task_decomposition_error": "subgoal sequence violates the task's "
                                "prerequisite order (e.g. deliver before pick)",
}


def _relearned_cells(trace: Dict, history: List[Dict]) -> List[list]:
    now = {tuple(c) for c in trace.get("metrics", {}).get("learned_blocked", [])}
    if not now:
        return []
    before = set()
    for h in history or []:
        if h.get("task_id") == trace.get("task_id") and h.get("trace_id") != trace.get("trace_id"):
            before |= {tuple(c) for c in h.get("metrics", {}).get("learned_blocked", [])}
    return [list(c) for c in now & before]


def classify(trace: Dict, arch: Dict, history: Optional[List[Dict]] = None) -> Optional[str]:
    if trace.get("success"):
        return None
    metrics = trace.get("metrics", {})
    actions = trace.get("actions", [])

    # Picked an object that is not the task target.
    if metrics.get("picked_wrong_kind"):
        return "perception_error"

    # Chose the pick tool with no object present.
    if metrics.get("failed_picks", 0) > 0:
        return "tool_selection_error"

    # Collisions happened but the harness has no collision verification.
    if metrics.get("bumps", 0) > 0 and "collision_check" not in arch.get(
        "verification_strategy", []
    ):
        return "verification_error"

    # Re-learned cells it already knew in a previous episode: the harness
    # forgot between episodes.
    if history and _relearned_cells(trace, history):
        return "memory_error"

    # Ran out of steps: the plan never converged.
    if len(actions) >= metrics.get("max_steps", 10**9):
        return "planning_error"

    return "execution_error"
