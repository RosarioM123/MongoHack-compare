"""Mutation proposer: pattern -> bounded mutation dict.

Every proposal references a skill from the registry by name. No code
generation, no free-form components.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, Optional


def _base(pattern: Dict, arch: Dict) -> Dict:
    return {
        "mutation_id": uuid.uuid4().hex,
        "parent_version": arch["version_id"],
        "resulting_version": "",
        "supporting_trace_ids": pattern.get("trace_ids", []),
        "validation": {},
        "accepted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def propose_mutation(pattern: Dict, arch: Dict) -> Optional[Dict]:
    kind = pattern.get("kind")

    if kind == "repeated_failure" and pattern.get("failure_category") == "verification_error":
        mutation = _base(pattern, arch)
        mutation.update({
            "mutation_type": "ADD_VERIFIER",
            "target": "navigation",
            "reason": (
                f"Repeated verification_error on {pattern['task_id']} "
                f"({pattern['count']} episodes): collisions with no verification"
            ),
            "expected_effect": "Replan around collisions instead of naive retry",
            "new_component": "collision_check",
        })
        return mutation

    if kind == "repeated_relearning":
        mutation = _base(pattern, arch)
        mutation.update({
            "mutation_type": "ADD_MODULE",
            "target": "memory",
            "reason": (
                f"Harness re-learned {pattern['count']} blocked cell(s) across "
                f"episodes instead of remembering them"
            ),
            "expected_effect": "Persist learned blocked cells across episodes; fewer steps",
            "new_component": "spatial_memory",
        })
        return mutation

    return None
