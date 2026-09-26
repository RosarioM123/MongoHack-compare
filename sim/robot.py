"""Robot planner whose behavior depends on the active harness modules.

- Baseline (no modules): BFS on the stale assumed map; on collision it
  naively retries the same action, then replans on the unchanged map.
- ``collision_check`` verifier: on collision, mark the cell blocked and
  replan immediately.
- ``spatial_memory`` module: learned blocked cells persist across episodes
  (the loop loads/saves them); without it every episode starts from the
  stale map and relearns the same obstacles.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from sim.world import DIRS, Cell, World

Action = str


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class Robot:
    def __init__(self, world: World, arch: Dict, memory: Optional[Dict] = None):
        self.world = world
        self.arch = arch
        if memory is None:
            memory = {"blocked": set(), "visited": set()}
        memory.setdefault("blocked", set())
        memory.setdefault("visited", set())
        self.memory: Dict[str, Set[Cell]] = memory
        self.last_action: Optional[Action] = None
        self.retry_count = 0
        self.replans = 0
        self.max_attempts = (
            arch.get("policies", {}).get("retry", {}).get("max_attempts", 3)
        )

    # ------------------------------------------------------------------ #
    def _blocked(self) -> Set[Cell]:
        return self.world.assumed_walls | self.memory["blocked"]

    def _in_bounds(self, cell: Cell) -> bool:
        spec = self.world.spec
        return 0 <= cell[0] < spec.width and 0 <= cell[1] < spec.height

    def _bfs(self, start: Cell, goal: Cell) -> Optional[List[Cell]]:
        """Shortest path on the assumed map; cells after start, goal inclusive."""
        if start == goal:
            return []
        blocked = self._blocked()
        queue: deque = deque([start])
        prev: Dict[Cell, Optional[Cell]] = {start: None}
        while queue:
            cur = queue.popleft()
            for dx, dy in DIRS:
                nxt = (cur[0] + dx, cur[1] + dy)
                if not self._in_bounds(nxt) or nxt in blocked or nxt in prev:
                    continue
                prev[nxt] = cur
                if nxt == goal:
                    path = [nxt]
                    while prev[path[-1]] is not None:
                        path.append(prev[path[-1]])  # type: ignore[arg-type]
                    path.reverse()
                    return path[1:]  # exclude start; caller steps from path[0]
                queue.append(nxt)
        return None

    def _nearest_unvisited(self, start: Cell) -> Optional[Cell]:
        blocked = self._blocked()
        queue: deque = deque([start])
        seen = {start}
        while queue:
            cur = queue.popleft()
            if cur != start and cur not in self.memory["visited"]:
                return cur
            for dx, dy in DIRS:
                nxt = (cur[0] + dx, cur[1] + dy)
                if not self._in_bounds(nxt) or nxt in blocked or nxt in seen:
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return None

    def _action_along(self, pos: Cell, direction: int, path: List[Cell]) -> Action:
        nxt = path[0]
        desired = DIRS.index((nxt[0] - pos[0], nxt[1] - pos[1]))
        if direction == desired:
            return "forward"
        if (direction + 1) % 4 == desired:
            return "right"
        return "left"  # left turn; opposite headings resolve over two steps

    # ------------------------------------------------------------------ #
    def decide(self, obs: Dict) -> Action:
        action = self._decide(obs)
        self.last_action = action
        return action

    def _decide(self, obs: Dict) -> Action:
        pos: Cell = obs["pos"]
        self.memory["visited"].add(pos)

        # Collision handling: the experimental variable.
        if obs["bump"] and self.last_action == "forward":
            if "collision_check" in self.arch.get("verification_strategy", []):
                front = (pos[0] + DIRS[obs["dir"]][0], pos[1] + DIRS[obs["dir"]][1])
                self.memory["blocked"].add(front)
                self.replans += 1
                self.retry_count = 0
            else:
                self.retry_count += 1
                if self.retry_count <= self.max_attempts:
                    return self.last_action  # naive retry into the wall
                self.retry_count = 0  # replan on the unchanged stale map
        else:
            self.retry_count = 0

        spec = self.world.spec
        goal: Optional[Cell] = None
        intent = ""
        if self.world.carrying is not None:
            if pos in self.world.drop_zones.values():
                return "drop"
            goal = min(self.world.drop_zones.values(), key=lambda c: manhattan(pos, c))
            intent = f"deliver to {goal}"
        else:
            targets = [o["pos"] for o in obs["objects"].values()
                       if o["kind"] == spec.target_kind]
            if pos in targets:
                return "pick"
            if targets:
                goal = min(targets, key=lambda c: manhattan(pos, c))
                intent = f"fetch target at {goal}"

        if goal is not None:
            path = self._bfs(pos, goal)
            if path is not None:
                return self._action_along(pos, obs["dir"], path)

        # No route to a known goal: frontier exploration.
        goal = self._nearest_unvisited(pos)
        if goal is None:
            return "wait"
        path = self._bfs(pos, goal)
        if path is None:
            return "wait"
        return self._action_along(pos, obs["dir"], path)
