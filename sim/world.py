"""Deterministic grid-world with a stale-map premise.

The planner navigates on the *assumed* map (borders + known interior walls).
The *true* world additionally contains unknown obstacles. Failures therefore
emerge from missing capabilities (no collision verification, no persistent
memory) instead of being scripted.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# N, E, S, W as (dx, dy)
DIRS = [(0, -1), (1, 0), (0, 1), (-1, 0)]

Cell = Tuple[int, int]


@dataclass
class TaskSpec:
    task_id: str
    environment_id: str
    width: int
    height: int
    interior_walls: Set[Cell] = field(default_factory=set)
    # Obstacles present in the true world but missing from the planner's map.
    unknown_obstacles: Set[Cell] = field(default_factory=set)
    objects: Dict[str, Dict] = field(default_factory=dict)  # id -> {"pos", "kind"}
    drop_zones: Dict[str, Cell] = field(default_factory=dict)
    target_kind: str = "box"
    start_candidates: List[Tuple[Cell, int]] = field(default_factory=list)
    max_steps: int = 150


class World:
    def __init__(self, spec: TaskSpec, seed: int):
        self.spec = spec
        self.rng = random.Random(seed)
        self.walls: Set[Cell] = set(spec.interior_walls) | set(spec.unknown_obstacles)
        for x in range(spec.width):
            self.walls.add((x, 0))
            self.walls.add((x, spec.height - 1))
        for y in range(spec.height):
            self.walls.add((0, y))
            self.walls.add((spec.width - 1, y))
        # Planner's stale map: everything except the unknown obstacles.
        self.assumed_walls: Set[Cell] = set(self.walls) - set(spec.unknown_obstacles)

        self.objects: Dict[str, Dict] = {
            oid: {"pos": tuple(o["pos"]), "kind": o["kind"]}
            for oid, o in spec.objects.items()
        }
        self.drop_zones: Dict[str, Cell] = {
            zid: tuple(pos) for zid, pos in spec.drop_zones.items()
        }
        self.target_ids: List[str] = [
            oid for oid, o in self.objects.items() if o["kind"] == spec.target_kind
        ]
        start_pos, start_dir = self.rng.choice(spec.start_candidates)
        self.robot_pos: Cell = tuple(start_pos)
        self.robot_dir: int = start_dir
        self.carrying: Optional[str] = None
        self.carrying_kind: Optional[str] = None
        self.delivered: List[str] = []
        self.bump_last: bool = False

    # ------------------------------------------------------------------ #
    def observe(self) -> Dict:
        """Overhead localization sensor: full object layout, local bump only.

        Kept deliberately simple so the experimental variable is navigation
        under a stale map, not perception.
        """
        fx = self.robot_pos[0] + DIRS[self.robot_dir][0]
        fy = self.robot_pos[1] + DIRS[self.robot_dir][1]
        front = (fx, fy)
        if front in self.walls:
            front_content = "wall"
        else:
            front_content = "empty"
            for oid, o in self.objects.items():
                if o["pos"] == front:
                    front_content = f"object:{oid}"
                    break
        return {
            "pos": self.robot_pos,
            "dir": self.robot_dir,
            "bump": self.bump_last,
            "carrying": self.carrying,
            "carrying_kind": self.carrying_kind,
            "objects": {
                oid: {"pos": o["pos"], "kind": o["kind"]}
                for oid, o in self.objects.items()
            },
            "drop_zones": {zid: pos for zid, pos in self.drop_zones.items()},
            "front": front_content,
        }

    # ------------------------------------------------------------------ #
    def step(self, action: str) -> Dict:
        """Execute one action in the true world. Returns an event dict."""
        self.bump_last = False
        event: Dict = {"bump": False, "picked": None, "dropped": None,
                       "delivered": False}
        if action == "forward":
            nx = self.robot_pos[0] + DIRS[self.robot_dir][0]
            ny = self.robot_pos[1] + DIRS[self.robot_dir][1]
            if (nx, ny) in self.walls:
                self.bump_last = True
                event["bump"] = True
                event["collision_cell"] = (nx, ny)
            else:
                self.robot_pos = (nx, ny)
        elif action == "left":
            self.robot_dir = (self.robot_dir - 1) % 4
        elif action == "right":
            self.robot_dir = (self.robot_dir + 1) % 4
        elif action == "pick":
            if self.carrying is None:
                for oid, o in list(self.objects.items()):
                    if o["pos"] == self.robot_pos:
                        self.carrying = oid
                        self.carrying_kind = o["kind"]
                        del self.objects[oid]
                        event["picked"] = oid
                        event["picked_kind"] = o["kind"]
                        break
        elif action == "drop":
            if self.carrying is not None and self.robot_pos in self.drop_zones.values():
                oid = self.carrying
                self.carrying = None
                self.delivered.append(oid)
                event["dropped"] = oid
                event["delivered"] = True
        elif action == "wait":
            pass
        else:
            raise ValueError(f"unknown action: {action}")
        return event

    # ------------------------------------------------------------------ #
    def task_complete(self) -> bool:
        return bool(self.target_ids) and all(
            oid in self.delivered for oid in self.target_ids
        )
