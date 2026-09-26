"""Benchmark task specifications.

Two environments; the second is harder (longer horizon, distractor objects,
more unknown obstacles). A third held-out task for the generalization
experiment is Prompt 3's deliverable.
"""
from __future__ import annotations

from typing import Dict

from sim.world import TaskSpec

TASKS: Dict[str, TaskSpec] = {}


def _register(spec: TaskSpec) -> TaskSpec:
    TASKS[spec.task_id] = spec
    return spec


# ---------------------------------------------------------------------- #
# Task A: pick-and-deliver in a single room split by a wall with a gap.
# The naive shortest path routes through (4, 3), which is blocked in the
# true world. v0 (no verifier) cannot get through; v1 (+collision_check)
# replans around it.
_register(TaskSpec(
    task_id="pick-and-deliver",
    environment_id="debris-room",
    width=9,
    height=9,
    interior_walls={(4, y) for y in range(1, 8)} - {(4, 3), (4, 4)},
    unknown_obstacles={(4, 3)},
    objects={
        "box-1": {"pos": (7, 7), "kind": "box"},
        "crate-1": {"pos": (2, 6), "kind": "crate"},
    },
    drop_zones={"zone-a": (7, 1)},
    target_kind="box",
    start_candidates=[((1, 1), 1), ((1, 2), 1), ((2, 1), 2)],
    max_steps=140,
))

# ---------------------------------------------------------------------- #
# Task B: two rooms joined by a doorway; longer horizon, distractor objects
# in both rooms, two unknown obstacles forcing detours in room 2.
_register(TaskSpec(
    task_id="multi-room-deliver",
    environment_id="two-room",
    width=13,
    height=9,
    interior_walls={(6, y) for y in range(1, 8)} - {(6, 4)},
    unknown_obstacles={(9, 3), (10, 5)},
    objects={
        "box-1": {"pos": (11, 7), "kind": "box"},
        "crate-1": {"pos": (2, 6), "kind": "crate"},
        "crate-2": {"pos": (9, 6), "kind": "crate"},
    },
    drop_zones={"zone-a": (1, 7)},
    target_kind="box",
    start_candidates=[((1, 1), 1), ((2, 1), 1), ((1, 2), 2)],
    max_steps=260,
))


def get_task(task_id: str) -> TaskSpec:
    return TASKS[task_id]


def list_tasks() -> list:
    return sorted(TASKS)
