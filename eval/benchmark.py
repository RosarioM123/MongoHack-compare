"""Reproducible benchmark for the recursive harness.

Runs the full evolution loop ``--trials`` times, each trial on a scratch
database (a temp SQLite file, or a scratch database on the same Atlas
cluster when MONGODB_URI is set) so trials are independent. The benchmark
report is written to the configured database's ``evaluations`` collection
and a human-readable summary is printed.

Every reported number traces to stored evidence: per-generation entries
carry their trace ids, and mutations carry their mutation ids.
"""
from __future__ import annotations

import argparse
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Dict, List

import db as db_module
import loop


def _trial_db(trial: int):
    uri = os.environ.get("MONGODB_URI")
    if uri:
        base = os.environ.get("MONGODB_DATABASE", "cookmemory")
        return db_module.MongoBackend(uri, f"{base}_benchmark_trial{trial}")
    path = os.path.join(tempfile.mkdtemp(), f"benchmark_trial{trial}.sqlite")
    return db_module.SQLiteBackend(path)


def run_benchmark(tasks: List[str], seeds: List[int], generations: int,
                  trials: int) -> Dict:
    trial_reports = []
    for i in range(trials):
        tdb = _trial_db(i)
        history = loop.run_generations(tdb, tasks, seeds, generations)
        trial_reports.append({"trial": i, "generations": history})
    return {
        "eval_id": uuid.uuid4().hex,
        "kind": "benchmark",
        "tasks": tasks,
        "seeds": seeds,
        "generations": generations,
        "trials": trials,
        "trial_reports": trial_reports,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _aggregate(report: Dict) -> List[Dict]:
    n_gen = report["generations"]
    agg = []
    for g in range(n_gen):
        gens = [t["generations"][g] for t in report["trial_reports"]]
        agg.append({
            "generation": g,
            "version": gens[0]["version"],
            "mean_success_rate": round(sum(x["success_rate"] for x in gens) / len(gens), 3),
            "mean_avg_steps": round(sum(x["avg_steps"] for x in gens) / len(gens), 1),
            "mean_collisions": round(sum(x["collisions"] for x in gens) / len(gens), 1),
            "mean_replans": round(sum(x["replans"] for x in gens) / len(gens), 1),
        })
    return agg


def print_summary(report: Dict) -> None:
    print(f"\n=== benchmark {report['eval_id'][:8]} "
          f"({report['trials']} trials, tasks={report['tasks']}, seeds={report['seeds']}) ===")
    for t in report["trial_reports"]:
        print(f"-- trial {t['trial']} --")
        for g in t["generations"]:
            m = g["mutation"]
            mut = "none" if not m else (
                f"{m['mutation_type']}+{m['new_component']}->{m['resulting_version']} "
                f"(accepted={m['accepted']}, lessons={m['lessons_validated']})")
            print(f"   gen {g['generation']} {g['version']}: "
                  f"{g['success_rate']:.2f} success, avg {g['avg_steps']} steps, "
                  f"{g['collisions']} collisions, {g['replans']} replans | {mut}")
    print("-- aggregate across trials --")
    for a in _aggregate(report):
        print(f"   gen {a['generation']} {a['version']}: "
              f"mean success {a['mean_success_rate']:.2f}, "
              f"mean steps {a['mean_avg_steps']}, "
              f"mean collisions {a['mean_collisions']}, "
              f"mean replans {a['mean_replans']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproducible harness benchmark")
    parser.add_argument("--tasks", default="pick-and-deliver,multi-room-deliver")
    parser.add_argument("--seeds", default="7,8")
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()

    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    report = run_benchmark(tasks, seeds, args.generations, args.trials)

    db = db_module.get_db()
    db.save("evaluations", report)
    print(f"[benchmark] report saved to evaluations (eval_id={report['eval_id']})")
    print_summary(report)


if __name__ == "__main__":
    main()
