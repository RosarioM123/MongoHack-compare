"""Mutation proposer: pattern -> bounded mutation dict.

Every proposal references a skill from the registry by name (or a named
strategy, which expands to registry skills). No code generation, no
free-form components. A proposal is skipped when its component is already
active.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


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


def _already_active(arch: Dict, component: str) -> bool:
    try:
        from skills import expand_component
        expanded = expand_component(component)
        active = set(arch.get("verification_strategy", [])) | set(
            arch.get("active_modules", [])) | set(arch.get("tools", []))
        names = set(expanded["verifiers"] + expanded["modules"] + expanded["tools"])
        return bool(names & active)
    except Exception:  # noqa: BLE001 - unknown component, let it through to fail loudly
        return False


def propose_mutation(pattern: Dict, arch: Dict,
                     traces: Optional[List[Dict]] = None) -> Optional[Dict]:
    kind = pattern.get("kind")

    if kind == "repeated_failure" and pattern.get("failure_category") == "verification_error":
        if _already_active(arch, "collision_check"):
            return None
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
        if _already_active(arch, "spatial_memory"):
            return None
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

    if kind == "repeated_failure" and pattern.get("failure_category") == "planning_error":
        # Timeouts with no collision signal: the planner needs more horizon.
        max_steps = None
        for t in traces or []:
            if t["trace_id"] in pattern.get("trace_ids", []):
                max_steps = t.get("metrics", {}).get("max_steps")
                break
        if not max_steps:
            return None
        new_budget = min(int(max_steps * 1.5), 600)
        if new_budget <= max_steps:
            return None
        mutation = _base(pattern, arch)
        mutation.update({
            "mutation_type": "MODIFY_POLICY",
            "target": "planning",
            "reason": (
                f"Repeated planning_error timeouts on {pattern['task_id']} "
                f"({pattern['count']} episodes) with no collision signal"
            ),
            "expected_effect": "Give the planner a wider horizon to converge",
            "new_component": None,
            "changes": {"max_steps": new_budget},
        })
        return mutation

    return None
