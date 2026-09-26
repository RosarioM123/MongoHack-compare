"""Architecture Evolver (seed implementation).

Deterministic rules map failure patterns to bounded mutations. Prompt 2 owns
growing this: richer classifier, skill composition, counterfactual lessons.
The interfaces here (classify / find_patterns / propose_mutation / validate)
are the ones the loop programs against.
"""
from evolver.classifier import classify
from evolver.patterns import find_patterns
from evolver.proposer import propose_mutation
from evolver.validator import validate

__all__ = ["classify", "find_patterns", "propose_mutation", "validate"]
