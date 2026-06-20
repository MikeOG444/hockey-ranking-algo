# CLAUDE.md — Hockey Rating Model Spike

Read this first every session. Detail lives in the docs; this file is the operating contract.

## What this is
A research spike to **identify the correct youth-hockey rating model** (transparent, explainable,
deterministic, fair) against synthetic ground truth. Then it becomes a hosted demo about AI building
beautiful, accurate data projects. Orientation:
- **[README.md](README.md)** — repo map + status.
- **[docs/planning/PLAN.md](docs/planning/PLAN.md)** — the 7-phase plan and what's in/out of scope.
- **[docs/analysis/decision-memo.md](docs/analysis/decision-memo.md)** — the model math; §10 invariant map; §11 resolved decisions. **The source of truth for the design.**
- **[docs/knowledge-bank/rating-model-test-brief.md](docs/knowledge-bank/rating-model-test-brief.md)** — the original brief.

## Prime directive: 100% AI-authored, reviewed in chat
The human writes **no code and no comments** — ever. All code and comments are AI-authored; the human
reviews **only through chat**. Therefore:
- **Explain every change in plain English a reviewer who will not open the file can follow.** Lead with
  *why* and *what behavior changed*, not a line-by-line diff. Reference **invariants and principles**
  (e.g. "preserves I1 because base is untouched"), not line numbers.
- **Tests are the proof, not prose.** A claim that something works means a test ran and passed — show the
  output. See `superpowers:verification-before-completion`. Never assert "done/fixed/passing" without evidence.
- Code must be readable by a non-author later: clear names, comments that explain *why*, no cleverness for
  its own sake. The codebase is a teaching artifact for the demo.

## Method (non-negotiable)
1. **Tests first — let the tests define the model.** Write the failing invariant/harness check before the
   implementation. Use `superpowers:test-driven-development`. Build bottom-up: data contract → generator →
   invariants-as-tests → models → run.
2. **Determinism is sacred (I8/I9).** No RNG in the rater, no order-dependence, stable sort on team id,
   fixed convergence tolerance. Generators are seeded; same input → byte-identical output. Any
   nondeterminism is a bug, not a quirk.
3. **Observed vs derived is a hard wall (brief §5).** Models consume **Level-0 rows only**
   (`week,date,time,team,opponent,goalsTeam,goalsOpponent`). Never feed a derived value (rating/tier/aggregate)
   back in as a primary input. **Always compute aggregates from the game log; never trust a stored summary.**
4. **The fairness floor is structural, not tuned.** `base(result)` is a floor nothing may override; tier/
   margin/momentum modulate the *bonus/penalty* only. If a change lets margin or schedule touch `base`,
   it's wrong. The two opponent-strength channels (`scheduleTerm`, tier-table) must stay orthogonal —
   don't pay for opponent strength twice.
5. **Every tuning pick is a falsifiable assumption** with a named confirming scenario (memo §11). The test,
   not the pick, has the final word.

## The gate
The bespoke model must pass **all** invariants I1–I13 (memo §10) on the §7 scenarios and beat the MHR
replica on rank-recovery. Benchmarks are *allowed* to fail invariants — that's the comparative story.

## Stack & commands
- Python (numpy/scipy/pandas), `pytest` for the harness. Use a project venv at `.venv`.
- Conventional setup (filled in when Phase 1 scaffolds `pyproject.toml`):
  - `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
  - `pytest` — run the full invariant + scoring harness.
  - `pytest harness/ -k I6` — run a single invariant's checks.
- Stage B (real-data backtest) is **out of scope** this spike — don't build walk-forward/log-loss yet.

## Skills & agents we lean on
- **`superpowers:test-driven-development`** — every feature/fix starts here.
- **`superpowers:systematic-debugging`** — when a solver/test misbehaves, before proposing a fix.
- **`superpowers:verification-before-completion`** — evidence before any "it works" claim.
- **`superpowers:brainstorming`** — before new design work (model variants, scenario design).
- **Context7** — fetch current numpy/scipy/pandas docs instead of guessing APIs.
- **`invariant-auditor`** (project agent) — adversarially verify a model against I1–I13.
- **`spec-keeper`** (project agent) — review changes for drift from the brief/memo principles.

## How we run the build (operating model v2)
**[docs/planning/operating-model.md](docs/planning/operating-model.md)** is the full policy. The essentials:
- **Trunk + PR.** `main` (on GitHub) is the single source of truth. Each task = a short-lived branch off
  `main` → TDD to green → **PR** → chat-reviewed → merge → delete branch. Never leave work on a stale branch.
- **State lives in [docs/work/BOARD.md](docs/work/BOARD.md)** — done / in-flight / **ready to pick up next**.
  Task files are in `docs/work/tasks/`. One task = one fresh chat, **self-contained** (a missing-context chat
  means fix the *task file*, not the prompt).
- **Start a task with `/task <id>`** (no hand-written prompt); `/board` shows the ready queue; `/task-new`
  scaffolds one.
- **Model matching:** `models/bespoke.py` floor/solve + the final decision → **opus**; benchmarks, generator,
  harness, metrics, scenarios → **sonnet**; mechanical/templated → **haiku**. When unsure, step up.
- **Parallelize only** tasks with **disjoint Owns(files)** — via the orchestrator (worktree-isolated
  subagents), never two chats on one working dir. `models/bespoke.py` work is **always sequential**. Run
  `invariant-auditor`/`spec-keeper` after model changes.

## Documentation hygiene
Keep the docs taxonomy alive as we build: design decisions → `docs/analysis/`, build/interface notes →
`docs/implementation/`, plans → `docs/planning/`, reference facts → `docs/knowledge-bank/`, task files →
`docs/work/tasks/`. **Task status lives only in `docs/work/BOARD.md`** — update the board row, not README prose.
