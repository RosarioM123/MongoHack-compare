"""Skill library: registry, composition, and real success metrics.

Skills are data, not code. The evolver references them by name; the robot
activates the ones listed in its architecture version. Success/failure counts
are updated from real episodes by the loop.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

# kind: "tool" | "module" | "verifier" -> which architecture list it belongs to.
SKILLS: Dict[str, Dict] = {
    "navigation": {
        "description": "BFS path planning on the assumed map",
        "prerequisites": [],
        "kind": "tool",
        "version": "1.0",
    },
    "object_detection": {
        "description": "Locate objects from the overhead sensor",
        "prerequisites": [],
        "kind": "tool",
        "version": "1.0",
    },
    "object_search": {
        "description": "Frontier exploration of unvisited cells",
        "prerequisites": ["navigation"],
        "kind": "tool",
        "version": "1.0",
    },
    "pickup": {
        "description": "Pick up the object on the current cell",
        "prerequisites": ["object_detection"],
        "kind": "tool",
        "version": "1.0",
    },
    "delivery": {
        "description": "Drop the carried object on a drop zone",
        "prerequisites": ["pickup", "navigation"],
        "kind": "tool",
        "version": "1.0",
    },
    "spatial_memory": {
        "description": "Persist learned blocked cells across episodes",
        "prerequisites": [],
        "kind": "module",
        "version": "1.0",
    },
    "collision_check": {
        "description": "On collision, mark the cell blocked and replan",
        "prerequisites": ["navigation"],
        "kind": "verifier",
        "version": "1.0",
    },
    "task_decomposition": {
        "description": "Split a task into ordered subgoals",
        "prerequisites": [],
        "kind": "module",
        "version": "1.0",
    },
    "verification": {
        "description": "Generic pre-action verification hook",
        "prerequisites": [],
        "kind": "verifier",
        "version": "1.0",
    },
}

# Named compositions of existing skills. Expanding a strategy activates each
# underlying skill in its natural architecture list.
STRATEGIES: Dict[str, List[str]] = {
    "careful-navigation": ["navigation", "collision_check", "spatial_memory"],
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_skill(name: str) -> Dict:
    if name not in SKILLS:
        raise ValueError(f"unknown skill: {name}")
    return dict(SKILLS[name], name=name)


def list_skills() -> List[str]:
    return sorted(SKILLS)


def compose(skill_names: List[str], strategy_name: str) -> Dict:
    """Compose existing skills into a named strategy (data, not code)."""
    unknown = [s for s in skill_names if s not in SKILLS]
    if unknown:
        raise ValueError(f"unknown skills: {unknown}")
    for s in skill_names:
        missing = [p for p in SKILLS[s]["prerequisites"] if p not in skill_names]
        if missing:
            raise ValueError(f"skill {s} requires missing prerequisites: {missing}")
    return {
        "strategy_name": strategy_name,
        "skills": list(skill_names),
        "created_at": utcnow(),
    }


def expand_component(name: str) -> Dict[str, List[str]]:
    """Expand a skill or strategy name into architecture-list buckets."""
    names = STRATEGIES.get(name, [name])
    out = {"verifiers": [], "modules": [], "tools": []}
    for n in names:
        skill = get_skill(n)  # raises on unknown
        bucket = {"verifier": "verifiers", "module": "modules", "tool": "tools"}[
            skill["kind"]
        ]
        out[bucket].append(n)
    return out


# ---------------------------------------------------------------------- #
# Persistence helpers (success metrics are real episode outcomes).
def ensure_seed_skills(db) -> None:
    for name, skill in SKILLS.items():
        if not db.find_one("skills", {"name": name, "type": "skill"}):
            db.save("skills", {
                "_id": f"skill:{name}",
                "type": "skill",
                "name": name,
                **skill,
                "success_count": 0,
                "failure_count": 0,
                "provenance": "seed",
            })


def record_result(db, name: str, success: bool) -> None:
    doc = db.find_one("skills", {"name": name, "type": "skill"})
    if not doc:
        return
    key = "success_count" if success else "failure_count"
    doc[key] = doc.get(key, 0) + 1
    db.save("skills", doc)
