"""Three-minute demo: the robot that rewrites its own harness.

Runs a fresh, fully deterministic evolution (v0 -> v1 -> v2) on a scratch
database, then narrates what happened with the measured numbers. Same seeds
give the same output every run.
"""
from __future__ import annotations

import os
import tempfile

import db as db_module
import loop


def _narrate(history) -> None:
    g0, g1, g2 = history[0], history[1], history[2]
    m0, m1 = g0["mutation"], g1["mutation"]

    print("\n" + "=" * 70)
    print("THE SETUP")
    print("=" * 70)
    print("A robot in a grid warehouse. Its map is stale: it believes a corridor")
    print("is open, but the real world has an obstacle there. The robot, v0, has")
    print("no collision verification and no memory. Watch what happens.\n")

    print("=" * 70)
    print("GENERATION 0: v0 fails the same way twice")
    print("=" * 70)
    print(f"v0 solved {g0['successes']}/{g0['episodes']} episodes "
          f"(avg {g0['avg_steps']} steps, {g0['collisions']} collisions).")
    print("The classifier labels the failures verification_error: collisions with")
    print("no verification. The counterfactual lesson: mark the cell blocked and")
    print("replan instead of blind-retrying. The proposer suggests ADD_VERIFIER")
    print("+collision_check. The validator checks it on held-out seeds:")
    print(f"  parent v0: {m0['validation_parent']['success_rate']:.2f} success, "
          f"{m0['validation_parent']['total_steps']} total steps")
    print(f"  child v1:  {m0['validation_child']['success_rate']:.2f} success, "
          f"{m0['validation_child']['total_steps']} total steps")
    print(f"  -> accepted. {m0['lessons_validated']} counterfactual lesson(s) "
          f"validated by the adoption.")
    print("")

    print("=" * 70)
    print("GENERATION 1: v1 routes around trouble")
    print("=" * 70)
    print(f"v1 solved {g1['successes']}/{g1['episodes']} episodes "
          f"(avg {g1['avg_steps']} steps).")
    print("But the pattern detector notices something: v1 relearns the same")
    print("blocked cells every episode. Knowledge dies between episodes. So the")
    print("harness adopts ADD_MODULE +spatial_memory and becomes v2.\n")

    print("=" * 70)
    print("GENERATION 2: v2 is stable")
    print("=" * 70)
    print(f"v2 solved {g2['successes']}/{g2['episodes']} episodes "
          f"(avg {g2['avg_steps']} steps).")
    print("No recurring failure patterns. The architecture stops changing on its")
    print("own. That restraint is the point: it only mutates on evidence.\n")

    print("=" * 70)
    print("FINAL COMPARISON (measured, stored in the database)")
    print("=" * 70)
    for g in history:
        print(f"  {g['version']}: success {g['success_rate']:.2f}, "
              f"avg {g['avg_steps']} steps, {g['collisions']} collisions, "
              f"{g['replans']} replans")
    print()
    print("Every number above traces to stored traces, mutations, and lessons.")
    print("Nothing was hardcoded to succeed: the mutations emerged from the")
    print("failures the robot actually produced.")


def main() -> None:
    path = os.path.join(tempfile.mkdtemp(), "demo.sqlite")
    db = db_module.SQLiteBackend(path)
    db.backend_name = "sqlite:scratch (demo)"
    print("[demo] fresh database, fixed seeds: the run below is deterministic.")
    history = loop.run_generations(
        db, ["pick-and-deliver", "multi-room-deliver"], [7, 8], 3)
    _narrate(history)


if __name__ == "__main__":
    main()
