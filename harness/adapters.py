"""Thin model adapters for the invariant harness (TASK-07).

Each adapter wraps a model's public API as a callable with the signature:
    (list[GameRow]) -> RateResult

This keeps harness/invariants.py free of model-specific import paths and parameter choices —
the adapter is the single place where defaults and entry-points are pinned.

`ModelFn` is the shared callable type used throughout harness/invariants.py and
harness/test_harness.py.  The two bespoke variants exist because I11 and I13 require
the per-week solve (rate_weekly) while I1–I10 / I12 use the flat solve (rate).
"""

from collections.abc import Callable

from core.game import GameRow
from models.bespoke import RateResult
import models.bespoke as bespoke
import models.mhr_replica as mhr_replica
import models.ridge_massey as ridge_massey

# The common signature every model adapter must match.
ModelFn = Callable[[list[GameRow]], RateResult]


def bespoke_flat(games: list[GameRow]) -> RateResult:
    """Bespoke flat solve — tier-agnostic, single-pass (I1–I10, I12)."""
    return bespoke.rate(games)


def bespoke_weekly(games: list[GameRow]) -> RateResult:
    """Bespoke per-week tier-aware solve (I11, I13)."""
    return bespoke.rate_weekly(games)


def mhr(games: list[GameRow]) -> RateResult:
    """MHR replica benchmark."""
    return mhr_replica.rate(games)


def ridge(games: list[GameRow]) -> RateResult:
    """Ridge Massey benchmark."""
    return ridge_massey.rate(games)
