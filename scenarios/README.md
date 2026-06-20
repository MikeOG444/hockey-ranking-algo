# scenarios/

The §7 edge-case test set — each a seeded generator config + expected assertions/invariants.

Wire these three end-to-end first (brief §10 build order):
1. Disconnected clusters · 3. Schedule inflation ("Dallas") · 6. Win-but-should-drop.

Then the rest: stale-opponent/float (4), giant-killer (5), close-vs-tier (7), tie handling (8),
sparse-vs-dense (9), transitivity trap (10), momentum (11), blowout incentive (12),
tier-instability/freeze-window sweep 1→4 (13).

Each maps to the invariants it stresses — see the brief §7 and `docs/analysis/decision-memo.md` §10.
