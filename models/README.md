# models/

Candidate raters, all behind one interface (see `docs/analysis/decision-memo.md` §8):

```python
rate(games, config) -> {ratings, tiers, perGameAttribution, trend}
```

This spike's minimum set to decide:
- `bespoke` — primary candidate. 3-term additive credit (base floor + marginAdj + scheduleTerm),
  damped batch solve, frozen-tier window. Design: `docs/analysis/decision-memo.md`.
- `mhr_replica` — incumbent to beat (AGD capped ±7 + mean-opponent SCHED, iterative).
- `ridge_massey` — transparent least-squares benchmark.

Deferred unless the decision is close: `margin_elo`, `dixon_coles` (as a rater).
