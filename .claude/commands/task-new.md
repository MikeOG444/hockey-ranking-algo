---
description: Scaffold + refine a new task file from a description, and add it to the board
argument-hint: <id and/or short description>
---

Create a refined, handoff-ready task from: **$ARGUMENTS**

1. Pick the next free `TASK-NN` id (or use the one given). Read `docs/planning/operating-model.md` for the
   task template and `docs/work/BOARD.md` for context/deps.
2. Investigate enough to write it **self-contained** (the "self-contained or it didn't happen" rule): a cold
   chat must be able to execute it with no other context. Fill every template section — goal, exact
   **Read first** references (files + doc sections + the commit/branch to start from), TDD approach,
   acceptance/DoD, **Model**, **Owns (files)**, parallel-safety, deps, out-of-scope.
3. Write it to `docs/work/tasks/TASK-NN-<slug>.md`.
4. Add/flip its row in `docs/work/BOARD.md` to **refined** (or **ready** if its deps are already `done`),
   with the correct Owns/Parallel/Deps. If it became ready, add it to the "▶ Ready now" list.
5. Commit the new task file + board update in the house style. Report the id, where it landed, and whether
   it's ready to pick up.

Do not start implementing the task — this only creates and queues it.
