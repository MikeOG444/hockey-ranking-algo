# harness/

Where the tests live — **written before the models** ("let the tests define the model").

- **Invariant checks I1–I13** (brief §4) as executable pytest assertions every candidate runs against.
  Mechanism map: `docs/analysis/decision-memo.md` §10.
- **Truth-scoring:** rank recovery (Spearman/Kendall), centered RMSE/MAE on ratings, tier-boundary accuracy.
- **Calibration** (only if a model emits win probabilities): reliability curve, Brier/log-loss.

> Stage B (walk-forward prediction backtest) is **out of scope** for this spike.
