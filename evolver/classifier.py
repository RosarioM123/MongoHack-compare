"""Failure classifier: failed trace -> one of the 9 failure categories.

Deterministic rules over the trace and the architecture that ran it.
"""
from __future__ import annotations

from typing import Dict, Optional


def classify(trace: Dict, arch: Dict) -> Optional[str]:
    if trace.get("success"):
        return None
    metrics = trace.get("metrics", {})
    actions = trace.get("actions", [])

    # Picked an object that is not the task target.
    if metrics.get("picked_wrong_kind"):
        return "perception_error"

    # Collisions happened but the harness has no collision verification.
    if metrics.get("bumps", 0) > 0 and "collision_check" not in arch.get(
        "verification_strategy", []
    ):
        return "verification_error"

    # Ran out of steps without collisions: the plan itself never converged.
    if len(actions) >= metrics.get("max_steps", 10**9):
        return "planning_error"

    return "execution_error"
