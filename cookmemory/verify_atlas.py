"""Guided Atlas Sandbox restart-recovery demo.

Run with the hackathon Sandbox credentials exported:

    export MONGODB_URI='mongodb+srv://...'
    export MONGODB_DATABASE=cookmemory   # optional
    python -m cookmemory.verify_atlas examples/observations.jsonl

Pass 1 replays the first events into Atlas. You then kill the process (or press
Enter) to simulate a crash. Pass 2 reconnects, resumes, and verifies that
already-processed events are skipped idempotently.
"""

import json
import os
import sys
import time

from .harness import replay
from .store import AtlasStore


def read_events(path):
    with open(path) as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def summarize(first, second):
    skipped = sum(1 for d in second if d.get("status") == "already_processed")
    new = [d for d in second if d.get("status") != "already_processed"]
    return {
        "pass1_decisions": len(first),
        "pass2_total": len(second),
        "skipped_as_processed": skipped,
        "new_decisions": len(new),
    }


def main(events_path="examples/observations.jsonl", limit=2):
    if not os.environ.get("MONGODB_URI"):
        sys.exit("Export MONGODB_URI with your hackathon Atlas Sandbox credentials first.")
    session = f"atlas-demo-{int(time.time())}"

    store = AtlasStore()
    try:
        print(f"--- pass 1: replaying first {limit} events into Atlas session '{session}'")
        first = list(replay(store, session, read_events(events_path), "memory", limit))
        for decision in first:
            print(json.dumps(decision))
        doc = store.collection.find_one({"_id": session})
        print("--- raw Atlas checkpoint document (truncated):")
        print(json.dumps(doc, default=str)[:600])
        input("--- Kill this process now (Ctrl+C) to simulate a crash, or press Enter to simulate a restart: ")
    finally:
        store.close()

    store = AtlasStore()
    try:
        print("--- pass 2: reconnected; resuming full replay")
        second = list(replay(store, session, read_events(events_path), "memory"))
        summary = summarize(first, second)
        print(json.dumps(summary, indent=2))
        ok = (summary["skipped_as_processed"] == len(first)
              and summary["new_decisions"] == len(second) - len(first) > 0)
        print("ATLAS RESTART CHECK:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2] or ["examples/observations.jsonl"])))
