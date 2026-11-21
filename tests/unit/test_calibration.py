"""Calibrated control-limit multipliers (spc/calibration.py, ADR 0003).

The key check is independent of how the multiplier was computed: fresh data with an
arbitrary mean and sigma, a different random seed, and the real chart code
(imr / ewma / cusum fit + apply) must give a family-wise false-alarm rate near the target.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from fabtwin.spc import cusum, ewma, imr
from fabtwin.spc.calibration import univariate_multiplier
from fabtwin.spc.capability import sigma_within

N, H, TARGET = 10, 20, 0.05


def _any_alarm_rate(method: str, multiplier: float, reps: int = 4000) -> float:
    rng = np.random.default_rng(12345)  # not the calibration seed
    alarms = 0
    for _ in range(reps):
        x = 80.0 + 2.3 * rng.standard_normal(N + H)  # arbitrary location and scale
        p1, p2 = x[:N].tolist(), x[N:].tolist()
        if method == "I-MR":
            pts = imr.apply_phase_ii(p2, imr.fit_phase_i(p1, k=multiplier))
            hit = any(p.out_of_control for p in pts)
        elif method == "EWMA":
            lim = ewma.fit_phase_i(sum(p1) / N, sigma_within(p1), 0.3, multiplier)
            hit = any(p.out_of_control for p in ewma.apply_phase_ii(p2, lim))
        else:
            s = sigma_within(p1)
            lim = cusum.fit_phase_i(sum(p1) / N, 0.5 * s, multiplier * s)
            hit = any(p.out_of_control for p in cusum.apply_phase_ii(p2, lim))
        alarms += hit
    return alarms / reps


@pytest.mark.parametrize("method", ["I-MR", "EWMA", "CUSUM"])
def test_calibrated_limits_hit_the_target_on_independent_data(method):
    cal = univariate_multiplier(method, N, H, TARGET)
    rate = _any_alarm_rate(method, cal.multiplier)
    assert rate == pytest.approx(TARGET, abs=0.015)  # ~4.5 standard errors at 4000 reps


def test_classical_limits_overshoot_the_target_with_a_short_phase_i():
    """The problem being fixed: k = 3 with a 10-point Phase I, 20-point horizon."""
    assert _any_alarm_rate("I-MR", 3.0) > 0.15


def test_long_phase_i_recovers_the_known_parameter_limit():
    # known parameters: 1 - (1 - 2(1 - Phi(L)))^20 = 0.05  =>  L ~ 3.017
    known = stats.norm.ppf(1 - (1 - 0.95 ** (1 / 20)) / 2)
    cal = univariate_multiplier("I-MR", 400, 20, 0.05)
    assert cal.multiplier == pytest.approx(known, abs=0.1)


def test_shorter_phase_i_needs_wider_limits():
    m = [univariate_multiplier("I-MR", n, 20, 0.05).multiplier for n in (5, 10, 30, 100)]
    assert m == sorted(m, reverse=True)


def test_deterministic_and_recorded():
    a = univariate_multiplier("EWMA", 10, 20, 0.05)
    b = univariate_multiplier("EWMA", 10, 20, 0.05)
    assert a == b
    p = a.as_params()
    assert {"multiplier", "target_false_alarm", "n_phase_i", "horizon", "seed"} <= p.keys()


@pytest.mark.parametrize(
    "kwargs", [{"n_phase_i": 1}, {"horizon": 0}, {"target": 0.0}, {"target": 1.0}]
)
def test_rejects_bad_inputs(kwargs):
    args = {"n_phase_i": 10, "horizon": 20, "target": 0.05, **kwargs}
    with pytest.raises(ValueError):
        univariate_multiplier("I-MR", **args)


def test_default_analysis_limits_are_unchanged():
    lim = imr.fit_phase_i([1.0, 2.0, 1.5, 1.8])
    assert lim.params["k"] == 3.0
