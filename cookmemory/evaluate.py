"""Evaluator-only scoring. Labels never enter perception or agent context."""

import tempfile
import time
from pathlib import Path

from .harness import replay
from .store import SQLiteStore


def _timed(decisions):
    return [d for d in decisions if d.get("status") != "already_processed"]


def score(decisions, labels):
    """Score one replayed session against evaluator-only label records."""
    timed = sorted(_timed(decisions), key=lambda d: d["timestamp"])
    records = [r for r in (labels or [])
               if r.get("start_time") is not None and r.get("end_time") is not None]
    error_windows = [r for r in records if r.get("errors")]
    clean_windows = [r for r in records if not r.get("errors")]

    def alerted(record):
        return any(record["start_time"] <= d["timestamp"] <= record["end_time"]
                   and (d["action"] == "request_verification" or d["open_issues"])
                   for d in timed)

    caught = sum(1 for r in error_windows if alerted(r))
    false_alarms = sum(1 for r in clean_windows if alerted(r))

    # Issue survival: for each issue, fraction of events strictly between its
    # first appearance and its resolution during which it stayed open.
    first_seen = {}
    for i, d in enumerate(timed):
        for issue_id in d["open_issues"]:
            first_seen.setdefault(issue_id, i)
    survivals = []
    for issue_id, first in first_seen.items():
        window = []
        for j in range(first + 1, len(timed)):
            if issue_id not in timed[j]["open_issues"]:
                break
            window.append(j)
        if window:
            survivals.append(sum(1 for j in window) / len(window))

    return {
        "events": len(timed),
        "verification_requests": sum(1 for d in timed if d["action"] == "request_verification"),
        "error_windows": len(error_windows),
        "caught": caught,
        "missed": len(error_windows) - caught,
        "clean_windows": len(clean_windows),
        "false_alarms": false_alarms,
        "issue_survival": (sum(survivals) / len(survivals)) if survivals else None,
        "unresolved_at_end": len(timed[-1]["open_issues"]) if timed else 0,
    }


def _fmt(key, value):
    if value is None:
        return "n/a"
    if key == "avg_latency_ms":
        return f"{value:.2f}"
    if isinstance(value, float):
        return f"{value:.0%}"
    return str(value)


def markdown_table(name_a, metrics_a, name_b, metrics_b):
    rows = [
        ("events", "events"),
        ("verification_requests", "verification requests"),
        ("error_windows", "error windows"),
        ("caught", "caught"),
        ("missed", "missed"),
        ("clean_windows", "clean windows"),
        ("false_alarms", "false alarms"),
        ("issue_survival", "issue survival"),
        ("unresolved_at_end", "unresolved at end"),
        ("avg_latency_ms", "avg latency (ms)"),
    ]
    lines = [f"| metric | {name_a} | {name_b} |", "| --- | --- | --- |"]
    for key, label in rows:
        lines.append(f"| {label} | {_fmt(key, metrics_a.get(key))} | {_fmt(key, metrics_b.get(key))} |")
    return "\n".join(lines)


def compare(events, labels, policy=None):
    """Replay the same events in memory and stateless modes; return metrics for both."""
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        for mode in ("memory", "stateless"):
            store = SQLiteStore(str(Path(directory) / f"{mode}.sqlite"))
            started = time.perf_counter()
            decisions = list(replay(store, f"compare-{mode}", events, mode=mode, policy=policy))
            elapsed_ms = (time.perf_counter() - started) * 1000
            store.close()
            metrics = score(decisions, labels)
            metrics["avg_latency_ms"] = round(elapsed_ms / max(len(decisions), 1), 2)
            results[mode] = {"decisions": decisions, "metrics": metrics}
    return results
