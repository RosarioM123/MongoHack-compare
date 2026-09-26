"""Pattern detection over recent traces.

Two pattern kinds:
- repeated_failure: >=2 failures sharing (failure_category, task_id).
- repeated_relearning: the same blocked cells learned in >=2 episodes, which
  means the harness keeps re-discovering obstacles it already hit before.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List

REPEAT_THRESHOLD = 2


def find_patterns(traces: List[Dict]) -> List[Dict]:
    patterns: List[Dict] = []

    fails = [t for t in traces if not t.get("success")]
    by_key: Dict[tuple, List[str]] = {}
    for t in fails:
        key = (t.get("failure_category"), t.get("task_id"))
        by_key.setdefault(key, []).append(t["trace_id"])
    for (category, task_id), ids in by_key.items():
        if len(ids) >= REPEAT_THRESHOLD:
            patterns.append({
                "kind": "repeated_failure",
                "failure_category": category,
                "task_id": task_id,
                "trace_ids": ids,
                "count": len(ids),
            })

    # Cells learned as blocked in more than one episode.
    learned_counter: Counter = Counter()
    per_trace: Dict[str, List[str]] = {}
    for t in traces:
        cells = [tuple(c) for c in t.get("metrics", {}).get("learned_blocked", [])]
        per_trace[t["trace_id"]] = cells
        for c in set(cells):
            learned_counter[c] += 1
    relearned = sorted([c for c, n in learned_counter.items() if n >= REPEAT_THRESHOLD])
    if relearned:
        patterns.append({
            "kind": "repeated_relearning",
            "cells": [list(c) for c in relearned],
            "trace_ids": [t["trace_id"] for t in traces
                          if any(tuple(c) in relearned
                                 for c in t.get("metrics", {}).get("learned_blocked", []))],
            "count": len(relearned),
        })
    return patterns
