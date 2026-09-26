"""Counterfactual learning: what should the harness have done differently?

For each failed trace, generate a structured lesson: a summary of what went
wrong, the counterfactual (what alternative harness behavior would have
succeeded), the inferred lesson, a qualitative confidence, and whether the
lesson was later validated by a real architectural change plus improved
episodes. Lessons live in the ``lessons`` collection; validated ones are
consulted by future episodes and cited as supporting evidence by the
proposer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def analyze_failure(trace: Dict, arch: Dict) -> Optional[Dict]:
    """Build a lesson from a failed trace. Deterministic rules only."""
    if trace.get("success"):
        return None
    category = trace.get("failure_category")
    task_id = trace.get("task_id")
    metrics = trace.get("metrics", {})
    verifiers = arch.get("verification_strategy", [])
    modules = arch.get("active_modules", [])

    recommended: Optional[str] = None
    if category == "verification_error":
        bumps = metrics.get("bumps", 0)
        failed_summary = (
            f"{bumps} collisions on {task_id} with no verification: the robot "
            f"retried blocked moves instead of replanning."
        )
        counterfactual = (
            "If the harness had marked the first collision cell as blocked and "
            "replanned immediately, it would have routed around the obstacle."
        )
        inferred = "On collision, mark the cell blocked and replan; never blind-retry."
        if "collision_check" not in verifiers:
            recommended = "collision_check"
        confidence = "high" if bumps >= 3 else "medium"
    elif category == "memory_error":
        failed_summary = (
            f"Re-learned already-known blocked cells on {task_id}: knowledge "
            f"did not survive between episodes."
        )
        counterfactual = (
            "If learned blocked cells had persisted across episodes, the robot "
            "would have avoided them from the first step."
        )
        inferred = "Persist learned map corrections across episodes."
        if "spatial_memory" not in modules:
            recommended = "spatial_memory"
        confidence = "high"
    elif category == "planning_error":
        failed_summary = (
            f"Ran out of steps on {task_id} ({metrics.get('steps')} steps): the "
            f"plan never converged."
        )
        counterfactual = (
            "With a larger step budget the planner might have converged; with "
            "better exploration it might have converged sooner."
        )
        inferred = "When the planner times out without collisions, widen the horizon."
        confidence = "low"
    elif category == "perception_error":
        failed_summary = f"Picked a non-target object on {task_id}."
        counterfactual = (
            "If the pick action had verified the object kind first, the wrong "
            "pick would have been skipped."
        )
        inferred = "Verify object kind before picking."
        confidence = "medium"
    elif category == "tool_selection_error":
        failed_summary = f"Chose the pick tool with no object present on {task_id}."
        counterfactual = (
            "If tool selection had checked preconditions, the wasted pick "
            "would not have happened."
        )
        inferred = "Check tool preconditions before acting."
        confidence = "medium"
    else:
        failed_summary = f"Failed on {task_id} ({category})."
        counterfactual = "No specific alternative identified."
        inferred = "Collect more episodes before drawing conclusions."
        confidence = "low"

    return {
        "lesson_id": uuid.uuid4().hex,
        "trace_id": trace.get("trace_id"),
        "task_id": task_id,
        "failure_category": category,
        "failed_summary": failed_summary,
        "counterfactual": counterfactual,
        "inferred_lesson": inferred,
        "recommended_component": recommended,
        "confidence": confidence,  # qualitative by design, never a fake probability
        "status": "proposed",
        "created_at": utcnow(),
    }


def get_validated_lessons(db, task_id: str) -> List[str]:
    docs = db.find("lessons", {"task_id": task_id, "status": "validated"}, limit=50)
    return [d["inferred_lesson"] for d in docs]


def mark_lessons_validated(db, mutation: Dict) -> int:
    """Validate lessons whose recommended component was just adopted.

    A lesson graduates from proposed to validated only when the architecture
    actually adopts its recommendation. The validator separately confirms the
    adoption improved measured metrics.
    """
    component = mutation.get("new_component")
    if not component:
        return 0
    # Expand strategies so lessons recommending a composed strategy match too.
    try:
        from skills import expand_component
        accepted = set(expand_component(component)["verifiers"]
                       + expand_component(component)["modules"]
                       + expand_component(component)["tools"])
    except Exception:  # noqa: BLE001 - fall back to the raw name
        accepted = {component}
    n = 0
    for trace_id in mutation.get("supporting_trace_ids", []):
        for lesson in db.find("lessons", {"trace_id": trace_id, "status": "proposed"}):
            if lesson.get("recommended_component") in accepted:
                lesson["status"] = "validated"
                lesson["validated_by"] = mutation.get("mutation_id")
                db.save("lessons", lesson)
                n += 1
    return n
