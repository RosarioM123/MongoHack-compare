"""Held-out generalization test.

Runs the frozen best architecture (no evolution, no mutation proposals) on a
task that was never used to trigger any mutation. Reports success rate, avg
steps, and which previously-learned skills transferred:
collision_check (replans after collisions) and spatial_memory (learned
blocked cells reused).
"""
from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone
from typing import Dict, List

import architectures
import db as db_module
import loop


def _best_architecture(db) -> Dict:
    archs = db.find("architectures", {}, limit=100)
    if not archs:
        raise RuntimeError("no architectures in db; run the loop first")
    return max(archs, key=lambda a: a.get("created_at", ""))


def run_generalization(db, held_out_task: str, seeds: List[int],
                       version: str = "") -> Dict:
    arch = architectures.get_version(db, version) if version else _best_architecture(db)
    traces = []
    for seed in seeds:
        trace, _memory = loop.run_episode(
            db, arch, held_out_task, seed, tag="generalization", persist=True)
        traces.append(trace)

    n = len(traces)
    report = {
        "eval_id": uuid.uuid4().hex,
        "kind": "generalization",
        "held_out_task": held_out_task,
        "frozen_version": arch["version_id"],
        "seeds": seeds,
        "episodes": n,
        "success_rate": round(sum(1 for t in traces if t["success"]) / n, 3) if n else 0.0,
        "avg_steps": round(sum(t["metrics"]["steps"] for t in traces) / n, 1) if n else 0.0,
        "trace_ids": [t["trace_id"] for t in traces],
        "skill_transfer": {
            # collision_check transferred if the frozen arch replanned around
            # collisions on the unseen task.
            "collision_check_replans": sum(t["metrics"].get("replans", 0) for t in traces),
            # spatial_memory transferred if learned cells were reused or new
            # ones learned and persisted for the new environment.
            "spatial_memory_learned": sum(
                len(t["metrics"].get("learned_blocked", [])) for t in traces),
            "spatial_memory_active": "spatial_memory" in arch.get("active_modules", []),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Held-out generalization test")
    parser.add_argument("--held-out-task", default="maze-deliver")
    parser.add_argument("--seeds", default="21,22,23")
    parser.add_argument("--version", default="",
                        help="architecture version to freeze (default: latest)")
    args = parser.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    db = db_module.get_db()
    mutations_before = len(db.find("mutations", {}, limit=100000))
    report = run_generalization(db, args.held_out_task, seeds, args.version)
    db.save("evaluations", report)
    mutations_after = len(db.find("mutations", {}, limit=100000))

    print(f"[generalization] frozen {report['frozen_version']} on "
          f"{report['held_out_task']}: success {report['success_rate']:.2f}, "
          f"avg {report['avg_steps']} steps")
    st = report["skill_transfer"]
    print(f"  skill transfer: collision_check replans={st['collision_check_replans']}, "
          f"spatial_memory active={st['spatial_memory_active']}, "
          f"cells learned={st['spatial_memory_learned']}")
    print(f"  mutations before={mutations_before} after={mutations_after} "
          f"(frozen: must be equal)")
    print(f"[generalization] report saved to evaluations (eval_id={report['eval_id']})")


if __name__ == "__main__":
    main()
