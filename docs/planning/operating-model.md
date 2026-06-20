# Operating Model v2 — how we run the build

How work is sliced, tracked, run on trunk, handed to fresh chats, matched to a model, and (when safe)
parallelized. This project is 100% AI-authored and reviewed in chat (see `CLAUDE.md`); this doc keeps that
scalable **without the integration tangle that v1 produced** (see Postmortem at the end).

## 0. The spine in one paragraph
`main` (on GitHub) is the **single source of truth**. Each task is a **short-lived branch off `main`**,
taken to green with TDD, opened as a **PR**, reviewed in chat, then merged and the branch deleted. Task
state lives in one place — **[`docs/work/BOARD.md`](../work/BOARD.md)** — which tells you what's done,
in-flight, and **ready to pick up next**. You start a task with **`/task <id>`** (no hand-written prompt).
Default execution is **sequential**; parallelism is opt-in, isolated in worktrees, and only for tasks whose
file sets don't overlap.

## 1. Trunk + PR integration (the rule that was missing in v1)
- **`main` is trunk and the only source of truth.** It always builds green. Status and the task queue live
  on `main`, never on a feature branch.
- **One task = one short-lived branch off latest `main`.** Name `task/NN-<slug>`. Take it to green, open a
  PR, get chat approval, **merge, delete the branch.** Don't let branches linger or diverge.
- **One writer per file.** Each task declares the files it **Owns** (board column). A file is owned by at
  most one in-flight task. `models/bespoke.py` (the model core) is owned by one task at a time → those tasks
  **serialize, always**.
- **"Stop before merge" = the PR.** The executing chat stops at PR-open; a human approves; merge follows.
  This is the review gate (we review in chat, per `CLAUDE.md`).

## 2. The board — single source of truth (`docs/work/BOARD.md`)
The only place state lives. Columns: `ID | Title | State | Model | Owns (files) | Parallel | Deps`.
- **Lifecycle:** `backlog` → `refined` (task file complete) → `ready` (refined + deps `done`) →
  `in-progress` → `in-review` (PR open) → `done`. `blocked` if a dep regresses.
- A **"▶ Ready now"** section is the pick-up-next queue.
- **Parallel rule:** two tasks may run at once only if their **Owns** sets are disjoint. The board makes
  overlaps visible *before* you fan out.
- Task files live in `docs/work/tasks/` (one folder; the board is the state, not the folder).

## 3. Tasks — one chat, self-contained
We change tasks by opening a **new chat** to preserve context. That only works if the task file is complete.

> **Self-contained or it didn't happen.** A fresh chat sees *no* other chat. Everything it needs lives in
> the task file or a committed doc/commit it references. **When a chat is missing context, fix the task file
> — never the prompt.** The prompt is thrown away; the task file is read by the next chat too.

Template (use `/task-new` to scaffold):
```markdown
# TASK-NN: <title>
**Status / Model / Owns (files) / Parallel-safe / Deps / Branch from:** <…>
## Goal — 2-3 sentences
## Read first — CLAUDE.md + exact files/doc-sections + the commit to branch from
## Approach (TDD — tests first, watch them fail)
## Acceptance / Definition of done — named tests green, ruff clean, agents run, PR opened
## Out of scope
```

### Model matching (ambiguity × cost-of-error, not size)
| Task shape | Model |
|---|---|
| Model **core** (`models/bespoke.py` floor/solve), convergence, the final decision, planning | **opus** |
| Benchmark models, generator features, harness, metrics, scenarios — clear spec + tests as guardrails | **sonnet** |
| Mechanical/templated — scenario config from a template, formatting, running tests, JSON boilerplate | **haiku** |
Anything touching `models/bespoke.py`'s floor/solve is **opus**. When unsure, step up a tier.

## 4. Commands (`.claude/commands/`) — no hand-written prompts
- **`/task <id>`** — full loop, stop before merge: load the task, branch from `main`, TDD to green,
  `pytest`+`ruff`, run `invariant-auditor`/`spec-keeper` if required, flip the board row, **open a PR and
  STOP** for approval.
- **`/board`** — print the "Ready now" queue + in-flight rows (cross-checked against branches/PRs).
- **`/task-new <desc>`** — scaffold a refined task file from the template + add a board row.

## 5. Parallel vs sequential
- **Default: sequential on trunk.** One task, one fresh chat, `/task <id>`. Zero collisions (one writer).
  Fast enough for a solo spike. **Model-core work is always here.**
- **Batch parallelism: an orchestrator** (the chosen model). When ≥2 **ready, parallel-safe, disjoint-file**
  tasks exist, one orchestrator chat fans out **worktree-isolated subagents** (Agent `isolation:"worktree"`),
  each running a task to green on its own branch and opening a PR (still stop-before-merge). The **harness
  owns the worktree lifecycle**, so the v1 manual-worktree tangle can't recur. Use the Workflow tool for
  larger fans. (An optional `/batch <ids>` command can wrap this later.)
- **Never** parallelize tasks that share a file. Check the board's **Owns** column first.

### Verification agents (run even on sequential work)
- **`invariant-auditor`** — adversarially re-checks I1–I13 on any model change. Required after any
  fairness-critical edit and after any model written by sonnet/haiku.
- **`spec-keeper`** — flags drift from brief/memo (floor breach, double-counting, nondeterminism,
  derived-data-as-input). Run before opening a model/generator PR.

## 6. De-contention (so parallel merges stay clean)
- `pyproject.toml` uses **setuptools auto-discovery** — adding a module needs no shared edit.
- Status lives in **`BOARD.md`** (single-writer rows), not in README prose. README links to the board.
- The integration (merge) step flips a row to `done`; the task loop flips it to `in-progress`/`in-review`.

## 7. The loop, per task
1. Fresh chat; set the model to the task's `Model`. 2. `/task <id>`. 3. It branches from `main`, runs TDD to
green, runs the required agents, opens a PR, **stops**. 4. You review the PR summary in chat. 5. Approve →
merge → delete branch → board row `done`.

## Postmortem — why v2 exists (v1 failure, kept as a guardrail)
v1 said "parallel-safe = separate files" and stopped there. Running parallel chats then produced: two
worktrees editing `models/bespoke.py` at once; a `master` left stale because nothing merged back; the task
queue stranded on a feature branch so state was unknowable; and a hand-crafted prompt every time. The fix
wasn't "more worktree rules" — it was a **clean trunk + an enforced integration step (PR→merge)**, a **single
board** for state, **auto-isolated** parallelism via the orchestrator, and **`/task`** to kill prompt
friction. Guardrail: if you ever can't answer "what's the state?" from one file, or two chats touch one file,
stop — that's the v1 failure returning.
