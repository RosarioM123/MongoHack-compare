"""Architecture versioning: every harness version is a reproducible document.

``apply_mutation`` is pure (no DB writes) so the validator can test child
architectures before they are accepted. ``create_version`` persists.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Dict, Optional

from contracts import ArchitectureVersion

V0_POLICIES = {
    "max_steps": None,  # None -> fall back to the task spec's max_steps
    "retry": {"max_attempts": 3},
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def v0() -> Dict:
    return ArchitectureVersion(
        version_id="v0",
        parent_version=None,
        active_modules=[],
        policies=copy.deepcopy(V0_POLICIES),
        tools=["navigation", "pickup", "delivery"],
        context_strategy="recent-5",
        verification_strategy=[],
        memory_policy={},
        mutation_reason=None,
        created_at=utcnow(),
    ).to_dict()


def ensure_v0(db) -> Dict:
    existing = db.find_one("architectures", {"version_id": "v0"})
    if existing:
        return existing
    doc = v0()
    db.save("architectures", doc)
    return doc


def get_version(db, version_id: str) -> Optional[Dict]:
    return db.find_one("architectures", {"version_id": version_id})


def next_version_id(parent_id: str) -> str:
    return f"v{int(parent_id[1:]) + 1}"


def apply_mutation(parent: Dict, mutation: Dict) -> Dict:
    """Return the child architecture dict without persisting it."""
    child = copy.deepcopy(parent)
    child.pop("_id", None)  # never inherit the parent's row id on save
    child["version_id"] = next_version_id(parent["version_id"])
    child["parent_version"] = parent["version_id"]
    child["mutation_reason"] = mutation.get("reason")
    child["created_at"] = utcnow()

    mtype = mutation["mutation_type"]
    comp = mutation.get("new_component")
    changes = mutation.get("changes", {}) or {}

    # A named strategy expands to its underlying registry skills, each routed
    # to its natural architecture list. A single skill goes to the list named
    # by the mutation type.
    from skills import STRATEGIES, expand_component  # lazy: skills must not import this module
    is_strategy = comp in STRATEGIES if comp else False
    expanded = expand_component(comp) if comp else None

    if mtype == "ADD_VERIFIER":
        targets = expanded["verifiers"] if is_strategy else ([comp] if comp else [])
        for name in targets:
            if name and name not in child["verification_strategy"]:
                child["verification_strategy"].append(name)
    elif mtype == "ADD_MODULE":
        if is_strategy:
            for name in expanded["verifiers"]:
                if name not in child["verification_strategy"]:
                    child["verification_strategy"].append(name)
            for name in expanded["modules"]:
                if name not in child["active_modules"]:
                    child["active_modules"].append(name)
            for name in expanded["tools"]:
                if name not in child["tools"]:
                    child["tools"].append(name)
        elif comp and comp not in child["active_modules"]:
            child["active_modules"].append(comp)
    elif mtype == "REMOVE_MODULE":
        child["active_modules"] = [m for m in child["active_modules"] if m != comp]
    elif mtype == "ADD_TOOL":
        targets = expanded["tools"] if is_strategy else ([comp] if comp else [])
        for name in targets:
            if name and name not in child["tools"]:
                child["tools"].append(name)
    elif mtype == "REMOVE_TOOL":
        child["tools"] = [t for t in child["tools"] if t != comp]
    elif mtype == "MODIFY_POLICY":
        child["policies"].update(changes)
    elif mtype == "MODIFY_RETRY_POLICY":
        child["policies"].setdefault("retry", {}).update(changes)
    elif mtype == "MODIFY_MEMORY_POLICY":
        child["memory_policy"].update(changes)
    elif mtype == "MODIFY_CONTEXT_STRATEGY":
        child["context_strategy"] = changes.get("context_strategy",
                                                child["context_strategy"])
    elif mtype == "MODIFY_PLANNER":
        child["policies"].setdefault("planner", {}).update(changes)
    else:
        raise ValueError(f"unknown mutation type: {mtype}")
    return child


def create_version(db, parent: Dict, mutation: Dict) -> Dict:
    """Apply a mutation, persist the child, and stamp the mutation record."""
    child = apply_mutation(parent, mutation)
    db.save("architectures", child)
    mutation["resulting_version"] = child["version_id"]
    return child
