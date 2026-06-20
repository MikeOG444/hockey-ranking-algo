# Operating Model — how we run the build

How work is sliced, handed off between chats, matched to a model, and (when safe) parallelized.
This project is 100% AI-authored and reviewed in chat (see `CLAUDE.md`); this doc keeps that scalable.

## 1. One task = one chat

We change tasks by opening a **new chat** to preserve context window. That only works if each task is
self-contained. Every task lives as a file in `docs/work/todo/` and moves to `docs/work/done/` when shipped.

**A task file must let a cold chat start with no prior memory.** Required sections (template below):
goal, **read-first references** (exact files + doc sections + the commit to branch from), TDD approach,
acceptance criteria (named tests/invariants), model, parallel-safety, out-of-scope.

```markdown
# TASK-NN: <title>
**Status:** todo | in-progress | done
**Model:** haiku | sonnet | opus — <one-line why>
**Parallel-safe:** yes | no — <what files it touches; why>
**Depends on:** <task ids / commit / "none">
**Branch from:** <commit sha or "main HEAD">

## Goal
<2-3 sentences: what done looks like>

## Read first (context for a cold chat)
- `CLAUDE.md` (operating contract) and this task file
- <decision-memo §X, brief §Y, specific source files with paths>

## Approach (TDD — tests first, watch them fail)
<the red→green steps; which invariants/behaviors to pin>

## Acceptance / Definition of done
- [ ] <named tests pass> ; full `pytest` green ; `ruff check .` clean
- [ ] <invariants satisfied> ; <attribution/score thresholds if any>
- [ ] commit in the house style (see git log)

## Out of scope
<what NOT to touch — keeps the slice clean>
```

## 2. Model matching

Match the model to the task's **ambiguity × cost-of-error**, not its size.

| Task shape | Model | Why |
|---|---|---|
| Design/math, the **fairness floor**, convergence, any **invariant-critical** model change, synthesis & the final decision, planning | **opus** | High ambiguity, correctness-critical; a subtle error here is expensive and hard to spot. |
| Standard implementation from a clear spec — **benchmark models** (MHR replica, ridge Massey), generator features (DC correction, trajectories, JSON), metrics, harness wiring, most TDD cycles | **sonnet** | Good judgment, cost-effective for well-scoped code with tests as guardrails. |
| Mechanical / low-ambiguity — scenario config from a template, doc formatting, running tests & reporting results, boilerplate | **haiku** | Fast and cheap; the spec leaves little room for error. |

Rule of thumb: **anything that touches `models/bespoke.py`'s credit floor or the solve is opus.** Benchmarks
and generators are sonnet. If a task can be written as "fill in this exact shape," it's haiku.
When unsure, step up one tier — the tests catch mistakes, but not design drift.

## 3. Subagents & parallelization — when it's safe

Parallelism is in the **dev process**, never in the product: the rating model stays deterministic (I8).

**Parallelize when ALL hold:**
- ≥2 tasks that are genuinely **independent** — no shared files, no "B needs A's output."
- Each writes to its **own file** (or its own `isolation: worktree`). Good fits: the 3 benchmark models,
  generator features, per-scenario authoring — each lands in a distinct module.
- Every agent's work is **gated by `pytest` + `ruff` before merge**; nothing merges red.

**Do NOT parallelize:**
- Edits to the **same file** — especially `models/bespoke.py`. Coupled invariants (I6/I7/I10 interact) go
  sequentially, in one chat with the model's context.
- Sequential chains (tiers depend on the solve; the comparison report depends on all models).
- "Because we can." This codebase is small and determinism-sensitive; coordination cost can exceed the
  benefit for tightly-coupled work. Fan out for breadth (many independent models/scenarios), not for depth.

**Verification agents (use liberally, even on sequential work):**
- `invariant-auditor` — adversarially re-checks I1–I13 on any model change. **Always run after a
  fairness-critical edit**, and after any model written by sonnet/haiku.
- `spec-keeper` — flags drift from the brief/memo (floor breaches, double-counting, nondeterminism,
  derived-data-as-input). Run before merging model or generator work.

**Safety floor:** all work is local code + tests; no outward/irreversible actions; commit only at green
checkpoints; preserve determinism. A parallel agent that can't prove green doesn't merge.

## 4. The loop, per task
1. Open a new chat; point it at the task file. 2. It reads the references, branches from the named commit.
3. TDD red→green→refactor. 4. `pytest` + `ruff` green. 5. Run `invariant-auditor`/`spec-keeper` if the task
says so. 6. Commit in house style. 7. Move the task file to `docs/work/done/`, update `README.md` status.
