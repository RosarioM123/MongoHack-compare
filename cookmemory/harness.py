"""Deterministic memory plumbing. Replace perception upstream, not with labels."""

import hashlib
import json
import math

FIELDS = {"event_id", "recording_id", "timestamp", "observation", "completed_steps", "issue", "resolves"}


def validate(event):
    unknown = set(event) - FIELDS
    if unknown:
        raise ValueError(f"Unsupported observation fields (possible label leakage): {sorted(unknown)}")
    for key in ("event_id", "recording_id", "observation"):
        if not isinstance(event.get(key), str) or not event[key]:
            raise ValueError(f"{key} must be a nonempty string")
    timestamp = event.get("timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (float, int)) or not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("timestamp must be a finite nonnegative number")
    for key in ("completed_steps", "resolves"):
        values = event.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
            raise ValueError(f"{key} must be a list of nonempty strings")
    issue = event.get("issue")
    if issue is not None:
        if not isinstance(issue, dict) or set(issue) != {"id", "description"}:
            raise ValueError("issue must contain exactly id and description")
        if any(not isinstance(v, str) or not v for v in issue.values()):
            raise ValueError("issue values must be nonempty strings")


def _policy_issues(event, policy, prior_completed):
    """Bounded adaptive rules. Returns [(issue_id, description)] to open."""
    opened = []
    if not policy or not policy.get("strict_order"):
        return opened
    requires = policy.get("requires", {})
    for step in event.get("completed_steps", []):
        for prereq in requires.get(step, []):
            if prereq not in prior_completed:
                opened.append((
                    f"order:{step}",
                    f"Step '{step}' completed before prerequisite '{prereq}'; need explicit evidence.",
                ))
    return opened


def advance(state, event, mode="memory", policy=None):
    validate(event)
    if mode not in ("memory", "stateless"):
        raise ValueError("Unknown mode")
    if state is None:
        state = {"recording_id": event["recording_id"], "mode": mode, "last_timestamp": -1,
                 "processed": {}, "completed_steps": [], "open_issues": {}, "recent": [],
                 "policy_version": (policy or {}).get("version", 0)}
    if state["recording_id"] != event["recording_id"] or state["mode"] != mode:
        raise ValueError("Use a different session for each recording and mode")
    digest = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
    previous = state["processed"].get(event["event_id"])
    if previous:
        if previous != digest:
            raise ValueError("An existing event_id was reused with different content")
        return state, {"event_id": event["event_id"], "status": "already_processed"}
    if event["timestamp"] < state["last_timestamp"]:
        raise ValueError("New events must arrive in chronological order")
    state = json.loads(json.dumps(state))
    if mode == "stateless":
        state["completed_steps"], state["open_issues"], state["recent"] = [], {}, []
    for issue_id in event.get("resolves", []):
        state["open_issues"].pop(issue_id, None)
    issue = event.get("issue")
    if issue:
        state["open_issues"][issue["id"]] = {"description": issue["description"],
                                            "evidence_event_id": event["event_id"]}
    prior_completed = set(state["completed_steps"])
    state["completed_steps"] = sorted(prior_completed | set(event.get("completed_steps", [])))
    for issue_id, description in _policy_issues(event, policy, prior_completed):
        state["open_issues"].setdefault(issue_id, {"description": description,
                                                  "evidence_event_id": event["event_id"],
                                                  "policy": True})
    state["recent"] = (state["recent"] + [{"event_id": event["event_id"], "observation": event["observation"]}])[-5:]
    state["processed"][event["event_id"]] = digest
    state["last_timestamp"] = event["timestamp"]
    # No claim of success: absence of an issue is not proof a task was completed.
    decision = {"event_id": event["event_id"], "timestamp": event["timestamp"],
                "action": "request_verification" if state["open_issues"] else "continue_observing",
                "open_issues": state["open_issues"], "completed_steps": state["completed_steps"]}
    return state, decision


def replay(store, session, events, mode="memory", limit=None, policy=None):
    state = store.load(session)
    count = 0
    for event in events:
        if limit is not None and count >= limit:
            break
        state, decision = advance(state, event, mode, policy)
        if decision.get("status") != "already_processed":
            # Event receipt and its memory effects are persisted together.
            store.save(session, state)
        count += 1
        yield decision
