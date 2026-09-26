"""Mutation validator: parent vs child on a validation task set.

Accept only on no-regression plus strict improvement in at least one metric.
The validator runs episodes through a caller-supplied runner so this module
never imports the loop (no circular import).
"""
from __future__ import annotations

from typing import Callable, Dict, List, Tuple

# (task_id, seed) pairs held fixed for validation.
VAL_TASKS: List[Tuple[str, int]] = [
    ("pick-and-deliver", 101),
    ("pick-and-deliver", 102),
    ("multi-room-deliver", 101),
]


def _summarize(traces: List[Dict]) -> Dict:
    n = len(traces)
    succ = sum(1 for t in traces if t.get("success"))
    steps = sum(t.get("metrics", {}).get("steps", 0) for t in traces)
    return {
        "episodes": n,
        "success_rate": succ / n if n else 0.0,
        "total_steps": steps,
        "avg_steps": steps / n if n else 0.0,
    }


def validate(db, parent: Dict, child: Dict,
             run_episode: Callable) -> Dict:
    """Run parent and child over VAL_TASKS with per-arch shared memory."""
    results = {}
    for arch in (parent, child):
        traces = []
        memory = None
        for task_id, seed in VAL_TASKS:
            trace, memory_out = run_episode(
                db, arch, task_id, seed, memory=memory,
                tag="validation", persist=True,
            )
            # spatial_memory persists across validation episodes too.
            if "spatial_memory" in arch.get("active_modules", []):
                memory = memory_out
            traces.append(trace)
        results[arch["version_id"]] = _summarize(traces)

    p, c = results[parent["version_id"]], results[child["version_id"]]
    no_regression = (
        c["success_rate"] >= p["success_rate"] and c["total_steps"] <= p["total_steps"]
    )
    strict_gain = (
        c["success_rate"] > p["success_rate"] or c["total_steps"] < p["total_steps"]
    )
    passed = bool(no_regression and strict_gain)
    return {"parent": p, "child": c, "passed": passed}
