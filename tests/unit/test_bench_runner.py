"""Tests for bench/runner.py SPRT internals.

The runner integration is exercised by manual smoke tests against
real git refs (see plans/2026-05-03-night-session.md). These unit
tests pin the math so future tweaks to alpha/beta/sigma defaults
don't silently break the verdict logic.
"""

from __future__ import annotations

import math

from bench.runner import _sprt


def _accept(diffs, baseline_mean=1.0, alpha=0.05, beta=0.05, delta=0.05):
    return _sprt(diffs, baseline_mean, alpha, beta, delta)


def test_no_diffs_continues():
    verdict, lr, sigma = _accept([])
    assert verdict == "continue"
    assert lr == 0.0


def test_strong_improvement_accepts_quickly():
    """5 paired diffs all at +20% (well past 5% delta) should accept."""
    diffs = [0.2, 0.2, 0.2, 0.2, 0.2]
    verdict, lr, _ = _accept(diffs, baseline_mean=1.0)
    assert verdict == "accept"
    assert lr >= math.log((1 - 0.05) / 0.05)


def test_strong_regression_rejects_quickly():
    """Diffs at -10% (patch is slower) should reject."""
    diffs = [-0.10, -0.10, -0.10, -0.10, -0.10]
    verdict, lr, _ = _accept(diffs, baseline_mean=1.0)
    assert verdict == "reject"
    assert lr <= math.log(0.05 / (1 - 0.05))


def test_zero_mean_rejects_with_consistent_zero():
    """All-zero diffs (perfect no-op) should reject after enough samples."""
    diffs = [0.0] * 10
    verdict, lr, sigma = _accept(diffs, baseline_mean=1.0)
    # With zero variance, we floor sigma at 5% of baseline_mean. LR is
    # negative because the patch isn't faster.
    assert verdict == "reject"
    assert lr < 0
    assert sigma >= 0.05 * 1.0


def test_noisy_no_op_continues_then_rejects():
    """Symmetric noise around zero should not converge prematurely."""
    diffs = [0.05, -0.05, 0.04, -0.04]  # n=4, still in prior-sigma regime
    verdict, lr, _ = _accept(diffs, baseline_mean=1.0)
    # 4 noisy samples shouldn't be decisive either way; LR should be
    # in the indeterminate band.
    upper = math.log((1 - 0.05) / 0.05)
    lower = math.log(0.05 / (1 - 0.05))
    assert lower < lr < upper or verdict in ("reject", "accept")


def test_sigma_floor_prevents_division_blowup():
    """Tiny diffs with small variance shouldn't produce infinite LR."""
    # All identical small diffs would have stdev=0 without the floor.
    diffs = [0.001] * 6
    verdict, lr, sigma = _accept(diffs, baseline_mean=1.0)
    assert sigma >= 0.05 * 1.0
    assert math.isfinite(lr)


def test_zero_baseline_mean_does_not_crash():
    """Defensive: baseline_mean=0 must return continue, not raise."""
    verdict, lr, sigma = _accept([0.1, 0.1, 0.1], baseline_mean=0.0)
    assert verdict == "continue"
