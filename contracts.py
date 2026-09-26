"""Frozen contracts for the recursive harness.

Field names are frozen. All three build streams program against these shapes.
Prompts 2 and 3: do not invent new field names; extend via the documented
``metrics`` / ``policies`` / ``changes`` free-form dicts instead.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

FAILURE_CATEGORIES = (
    "perception_error",
    "localization_error",
    "planning_error",
    "memory_error",
    "context_error",
    "tool_selection_error",
    "execution_error",
    "verification_error",
    "task_decomposition_error",
)

MUTATION_TYPES = (
    "ADD_MODULE",
    "REMOVE_MODULE",
    "MODIFY_POLICY",
    "MODIFY_CONTEXT_STRATEGY",
    "ADD_TOOL",
    "REMOVE_TOOL",
    "ADD_VERIFIER",
    "MODIFY_PLANNER",
    "MODIFY_MEMORY_POLICY",
    "MODIFY_RETRY_POLICY",
)

# Seed skill registry. Mutations may only reference skills by name from here
# (plus skills added later through ADD_TOOL with a registry entry).
SEED_SKILLS = (
    "navigation",
    "object_detection",
    "object_search",
    "pickup",
    "delivery",
    "spatial_memory",
    "collision_check",
    "task_decomposition",
    "verification",
)

COLLECTIONS = (
    "experiences",
    "trajectories",
    "tasks",
    "skills",
    "failures",
    "lessons",
    "policies",
    "architectures",
    "mutations",
    "evaluations",
    "environments",
)


@dataclass
class Trace:
    """One robot execution, stored in ``trajectories``."""

    trace_id: str
    task_id: str
    environment_id: str
    harness_version: str
    seed: int
    observations: List[Dict[str, Any]] = field(default_factory=list)
    selected_tools: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    plan: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    outcome: Dict[str, Any] = field(default_factory=dict)
    success: bool = False
    failure_category: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    adaptation_proposed: Optional[Dict[str, Any]] = None
    adaptation_accepted: bool = False
    resulting_harness_version: str = ""
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Mutation:
    """One proposed architecture change, stored in ``mutations``."""

    mutation_id: str
    mutation_type: str  # one of MUTATION_TYPES
    target: str
    reason: str
    expected_effect: str
    new_component: Optional[str]  # skill name from the registry, never code
    parent_version: str
    resulting_version: str = ""
    supporting_trace_ids: List[str] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)
    accepted: bool = False
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArchitectureVersion:
    """A full, reproducible harness configuration, stored in ``architectures``."""

    version_id: str  # "v0", "v1", ...
    parent_version: Optional[str]
    active_modules: List[str] = field(default_factory=list)
    policies: Dict[str, Any] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    context_strategy: str = "recent-5"
    verification_strategy: List[str] = field(default_factory=list)
    memory_policy: Dict[str, Any] = field(default_factory=dict)
    mutation_reason: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
