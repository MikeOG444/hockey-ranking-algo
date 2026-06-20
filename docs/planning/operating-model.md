# Operating Model — how we run the build

How work is sliced, handed off between chats, matched to a model, and (when safe) parallelized.
This project is 100% AI-authored and reviewed in chat (see `CLAUDE.md`); this doc keeps that scalable.

## 1. One task = one chat

We change tasks by opening a **new chat** to preserve context window. That only works if each task is
self-contained. Every task lives as a file in `docs/work/todo/` and moves to `docs/work/done/` when shipped.

**A task file must let a cold chat start with no prior memory.** Required sections (template below):
goal, **read-first references** (exact files + doc sections + the commit to branch from), TDD approach,
acceptance criteria (named tests/invariants), model, parallel-safety, out-of-scope.

> **Self-contained or it didn't happen.** A fresh chat cannot see *any* other chat — not the planning
> chat that created the task, not a sibling task chat running in parallel. Anything that matters must live
> in the task file or in a committed doc/commit it references. **Corollary:** when a task chat turns out to
> be missing context, fix the *task file* (or the doc it points to) — never paper over it with a longer
> kickoff prompt. The prompt is thrown away; the task file is read by the next chat too. A gap patched in
> chat is a gap that reappears.

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
1. Open a new chat; **set the model to the task file's `Model:` field.** 2. Send the kickoff prompt below.
3. It reads the references, branches from the named commit. 4. TDD red→green→refactor. 5. `pytest` + `ruff`
green. 6. Run `invariant-auditor`/`spec-keeper` if the task says so. 7. Commit in house style. 8. Move the
task file to `docs/work/done/`, update `README.md` status.

### Kickoff prompt (fill in the filename)
```
Execute docs/work/todo/TASK-NN-<name>.md.

Follow it exactly: read the "Read first" references, branch from the named commit,
and work strictly TDD (write each test, watch it fail, then implement — no production
code before a failing test). Keep going until the Definition of done is fully met:
all named tests + full pytest green, ruff clean, the required invariant-auditor /
spec-keeper runs done, committed in the house style, task file moved to
docs/work/done/, and README status updated.

Stay inside the task's scope. If you hit a genuine design decision the task doesn't
resolve, stop and ask rather than guessing.
```
For a parallel-safe task, add: *"Touch only this task's own files; do not edit `models/bespoke.py` or `core/`."*
To review before it codes (good for opus/critical-path tasks): *"First give me a short plan + the first
failing test, and wait for my go."*
