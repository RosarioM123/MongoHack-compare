"""Architecture Evolver.

Deterministic rules map failure patterns to bounded mutations; counterfactual
analysis turns failures into lessons that graduate to validated only when an
adopted mutation proves them out. The interfaces here (classify /
find_patterns / propose_mutation / validate / analyze_failure) are the ones
the loop programs against.
"""
from evolver.classifier import RESERVED_RULES, classify
from evolver.counterfactual import (
    analyze_failure,
    get_validated_lessons,
    mark_lessons_validated,
)
from evolver.patterns import find_patterns
from evolver.proposer import propose_mutation
from evolver.validator import validate

__all__ = [
    "RESERVED_RULES",
    "analyze_failure",
    "classify",
    "find_patterns",
    "get_validated_lessons",
    "mark_lessons_validated",
    "propose_mutation",
    "validate",
]
