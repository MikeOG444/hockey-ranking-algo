"""Tier detection and the frozen-tier window (memo §4, §5; brief §1.8, §2).

Two pure, deterministic pieces (no RNG → I8):

- ``detect_tiers`` turns a converged rating vector into 1-indexed bands by *natural gaps*, never
  hardcoded ranks (brief §2). Tier 1 is the top. The number of bands is an output, not a constant:
  ``"auto"`` lets the gap rule pick it; an integer pins it.
- ``TierWindow`` is the anti-whipsaw machinery (I13, memo §5). Within a week the tiers used to
  credit games are *frozen* from prior finalized weeks; this class accumulates those finalized
  tier dicts and answers two questions about an opponent:
    * ``frozen_tier`` — a recency-weighted read of where it has sat over the last ≤4 weeks, so a
      one-week blip barely moves it (the credit it confers stays bounded → I13);
    * ``consistency`` — how steady that tier has been (a team that bounces reads low, which the
      model uses to confer credit at lower confidence).

Both ignore RNG and any stored summary; tiers come only from the rating vector handed in.
"""

from math import exp
from statistics import median


def detect_tiers(
    ratings: dict[str, float],
    tier_count: int | str = "auto",
    *,
    gap_c: float = 2.0,
) -> dict[str, int]:
    """Assign each team a 1-indexed tier (1 = top) from natural gaps in ``ratings``.

    Sort teams by descending rating (ties broken by team id for determinism, I8), look at the gaps
    between consecutive ratings, and cut the sorted list into bands:

    - ``"auto"``: cut at every gap that exceeds ``gap_c * median_gap`` — the gap/break-detection of
      brief §2 (largest-gap splits). With no qualifying gap everyone lands in tier 1 ("the field").
    - integer ``N``: place exactly ``N-1`` cuts at the ``N-1`` largest gaps. Raises if there are
      fewer than ``N`` distinct ratings (you cannot carve N bands out of fewer values).

    Returns ``{team_id: tier_int}``.
    """
    if not ratings:
        return {}

    # Descending rating, team id as the deterministic tie-break (I8: no order dependence).
    ordered = sorted(ratings, key=lambda t: (-ratings[t], t))
    gaps = [ratings[ordered[i]] - ratings[ordered[i + 1]] for i in range(len(ordered) - 1)]

    if isinstance(tier_count, int):
        distinct = len(set(ratings.values()))
        if distinct < tier_count:
            raise ValueError(
                f"tier_count={tier_count} needs {tier_count} distinct ratings, found {distinct}"
            )
        if tier_count <= 1 or not gaps:
            cut_after = set()
        else:
            # The N-1 largest gaps become boundaries. Tie-break on the earlier (higher-rating)
            # split so the choice is deterministic (I8).
            ranked = sorted(range(len(gaps)), key=lambda i: (-gaps[i], i))
            cut_after = set(ranked[: tier_count - 1])
    else:  # "auto" (or any non-int): gap-detection picks the number of bands
        if not gaps:
            cut_after = set()
        else:
            threshold = gap_c * median(gaps)
            cut_after = {i for i, g in enumerate(gaps) if g > threshold}

    tiers: dict[str, int] = {}
    tier = 1
    for i, team in enumerate(ordered):
        tiers[team] = tier
        if i in cut_after:  # a boundary sits *after* position i
            tier += 1
    return tiers


class TierWindow:
    """A sliding ≤``max_weeks`` window of finalized per-week tier assignments (memo §5).

    Feed it each finalized week's tier dict with :meth:`add_week`; it keeps only the most recent
    ``max_weeks`` weeks. :meth:`frozen_tier` and :meth:`consistency` then read an opponent's history
    to drive the anti-whipsaw guarantee (I13).
    """

    def __init__(self, max_weeks: int = 4) -> None:
        self.max_weeks = max_weeks
        # week number -> {team_id: tier}. A plain dict keyed by week; we prune to the last
        # max_weeks by week number so the read is a true sliding window.
        self._weeks: dict[int, dict[str, int]] = {}

    def __len__(self) -> int:
        """How many finalized weeks are currently stored (drives cold-start: memo §5)."""
        return len(self._weeks)

    def add_week(self, week: int, tiers: dict[str, int]) -> None:
        """Record a finalized week's tier assignments, evicting weeks beyond the window."""
        self._weeks[week] = dict(tiers)
        if len(self._weeks) > self.max_weeks:
            for stale in sorted(self._weeks)[: len(self._weeks) - self.max_weeks]:
                del self._weeks[stale]

    def _history(self, team_id: str) -> list[tuple[int, int]]:
        """(week, tier) pairs for ``team_id`` across the stored window, ascending by week."""
        return [(w, self._weeks[w][team_id]) for w in sorted(self._weeks) if team_id in self._weeks[w]]

    def frozen_tier(self, team_id: str, rho: float = 1.0) -> float | None:
        """Recency-weighted mean of ``team_id``'s tier over the stored weeks.

        Weight of week ``w`` is ``exp(-rho * (latest_week - w))`` so recent weeks dominate and a
        single-week blip is averaged down (I13). Returns ``None`` when there is no history yet —
        the cold-start signal: the caller then credits tier-agnostically (m = p = 1).
        """
        history = self._history(team_id)
        if not history:
            return None
        latest = max(w for w, _ in history)
        num = 0.0
        den = 0.0
        for w, tier in history:
            weight = exp(-rho * (latest - w))
            num += weight * tier
            den += weight
        return num / den

    def consistency(self, team_id: str) -> float:
        """How steady ``team_id``'s tier has been over the window, in ``[0, 1]``.

        ``1 - std(tier) / max_possible_std``, where ``max_possible_std`` is the largest standard
        deviation achievable across the team's own observed tier range, ``(max - min) / 2``
        (Popoviciu's bound). A team seen in a single tier → 1.0; one alternating between the
        extremes of its range → 0.0. Uniform weighting across the window: recency-decaying the
        consistency read is a Stage-B knob (memo §5), out of scope here.
        """
        history = self._history(team_id)
        if not history:
            return 1.0  # no evidence of bouncing → treat as fully consistent
        values = [tier for _, tier in history]
        lo, hi = min(values), max(values)
        if hi == lo:
            return 1.0  # never moved tier
        mean = sum(values) / len(values)
        std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
        max_possible_std = (hi - lo) / 2
        return 1.0 - std / max_possible_std
