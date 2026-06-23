"""Scenario 3 — Schedule inflation 'Dallas' (I6, I10).

T_PADDED beats 5 bottom-tier opponents; T_GAUNTLET beats 5 top-tier opponents. Identical record
(5 wins), same number of games. The model must credit T_GAUNTLET higher because its wins came
against stronger opposition — the schedule_term channel carries this signal (I6, I10).

Invariants stressed: I6 (tier-crossed margin), I10 (floating opponent strength).
"""

from models.bespoke import rate_weekly
from scenarios.builders import build_s03_schedule_inflation


def test_s03_gauntlet_rates_above_padded():
    dataset, meta = build_s03_schedule_inflation()
    result = rate_weekly(dataset.games)
    r = result.ratings

    padded = r["T_PADDED"]
    gauntlet = r["T_GAUNTLET"]
    assert gauntlet > padded, (
        f"Expected T_GAUNTLET > T_PADDED but got {gauntlet:.4f} <= {padded:.4f}. "
        f"Full ratings: {r}"
    )
