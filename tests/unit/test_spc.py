"""Unit tests for src/fabtwin/spc/ - behavior not pinned to a NIST fixture.

The NIST known-answer checks live in tests/validation/test_*_nist.py; this
file covers Phase I/II immutability, error handling, small-sample warnings,
and the control-limit/spec-limit separation the Overview requires.
"""

import dataclasses

import pytest

from fabtwin.spc.capability import cp_cpk, pp_ppk, sigma_overall, sigma_within
from fabtwin.spc.ewma import apply_phase_ii as ewma_apply_phase_ii
from fabtwin.spc.ewma import fit_phase_i as ewma_fit_phase_i
from fabtwin.spc.imr import apply_phase_ii as imr_apply_phase_ii
from fabtwin.spc.imr import fit_phase_i as imr_fit_phase_i
from fabtwin.spc.phase import FrozenLimits


def test_frozen_limits_is_immutable():
    limits = imr_fit_phase_i([10.0, 11.0, 9.0, 10.5])
    with pytest.raises(dataclasses.FrozenInstanceError):
        limits.ucl = 999.0  # type: ignore[misc]


def test_imr_requires_at_least_two_observations():
    with pytest.raises(ValueError, match="at least 2"):
        imr_fit_phase_i([10.0])


def test_imr_detects_an_obvious_out_of_control_point():
    healthy = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0, 10.1, 9.9, 10.2, 9.8]
    limits = imr_fit_phase_i(healthy)
    phase_ii_data = healthy + [50.0]  # blatant spike, far beyond any plausible 3-sigma limit
    points = imr_apply_phase_ii(phase_ii_data, limits)
    assert points[-1].out_of_control is True
    assert not any(p.out_of_control for p in points[:-1])


def test_ewma_rejects_lambda_out_of_range():
    with pytest.raises(ValueError, match="lambda"):
        ewma_fit_phase_i(target=50.0, sigma=2.0, lam=0.0)
    with pytest.raises(ValueError, match="lambda"):
        ewma_fit_phase_i(target=50.0, sigma=2.0, lam=1.5)


def test_ewma_phase_ii_length_matches_input_not_seed_inclusive():
    limits = ewma_fit_phase_i(target=50.0, sigma=2.0, lam=0.3)
    points = ewma_apply_phase_ii([51.0, 49.0, 50.5], limits)
    assert len(points) == 3  # not 4 - the EWMA_0 seed must not appear as a Phase II point


def test_capability_and_control_limits_are_unrelated_types():
    """Overview 4.2: "control limits 与 specification limits...永久分开." A
    capability result must never be constructible from a FrozenLimits, and
    vice versa - this test would fail to even type-check/run coherently if
    someone accidentally merged the two concepts.
    """
    limits = imr_fit_phase_i([10.0, 11.0, 9.0, 10.5])
    result = cp_cpk(mean=10.0, sigma_within=0.5, usl=12.0, lsl=8.0)
    assert not hasattr(result, "ucl")
    assert not hasattr(limits, "usl")
    assert isinstance(limits, FrozenLimits)


def test_capability_warns_on_small_sample():
    result = cp_cpk(mean=10.0, sigma_within=0.5, usl=12.0, lsl=8.0, n=10)
    assert any("sample size" in w for w in result.warnings)


def test_capability_no_warning_at_or_above_min_sample():
    result = cp_cpk(mean=10.0, sigma_within=0.5, usl=12.0, lsl=8.0, n=30)
    assert result.warnings == []


def test_capability_handles_nonpositive_sigma_without_crashing():
    result = cp_cpk(mean=10.0, sigma_within=0.0, usl=12.0, lsl=8.0)
    assert result.cp_or_pp != result.cp_or_pp  # NaN
    assert any("sigma is zero or negative" in w for w in result.warnings)


def test_pp_ppk_uses_overall_sigma_kind_cp_cpk_uses_within():
    within_result = cp_cpk(mean=10.0, sigma_within=0.5, usl=12.0, lsl=8.0)
    overall_result = pp_ppk(mean=10.0, sigma_overall=0.5, usl=12.0, lsl=8.0)
    assert within_result.sigma_kind == "within"
    assert overall_result.sigma_kind == "overall"


def test_sigma_within_matches_imr_sigma_hat():
    data = [49.6, 47.6, 49.9, 51.3, 47.8, 51.2, 52.6, 52.4, 53.6, 52.1]
    limits = imr_fit_phase_i(data)
    assert sigma_within(data) == pytest.approx(limits.params["sigma_hat"])


def test_sigma_overall_uses_sample_stdev_not_moving_range():
    data = [10.0, 12.0, 9.0, 11.0, 10.0]
    import statistics

    assert sigma_overall(data) == pytest.approx(statistics.stdev(data))
    assert sigma_overall(data) != pytest.approx(sigma_within(data), abs=1e-9)
