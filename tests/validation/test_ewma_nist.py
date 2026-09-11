"""Known-answer test: EWMA chart against the NIST Engineering Statistics
Handbook worked example, section 6.3.2.4 (EWMA Control Charts),
https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm.

Traceable to Overview section 4.6 acceptance bullet: "与手算或独立 fixture
一致：...EWMA...；浮点 tolerance 写入测试。"

IMPORTANT PROVENANCE NOTE: an earlier fetch of this NIST page produced an
ambiguous 20-value EWMA list whose indexing was unclear (was EWMA_1
target-only, or already incorporating X_1?). Before hardcoding it as a
fixture, the page was re-fetched with an explicit request for the raw
(observation, X, EWMA) triples and the exact recursive formula. That
second fetch gives the unambiguous table below (EWMA_0 = target, EWMA_t
computed from X_t for t=1..20) and every value was independently
hand-verified by recomputing the recursion forward from EWMA_0 - see the
worked arithmetic in the PR/commit description. Do not replace this
fixture from a future fetch without the same hand-verification.
"""

import pytest

from fabtwin.spc.ewma import apply_phase_ii, ewma_series, fit_phase_i

NIST_X = [
    52.0, 47.0, 53.0, 49.3, 50.1, 47.0, 51.0, 50.1, 51.2, 50.5,
    49.6, 47.6, 49.9, 51.3, 47.8, 51.2, 52.6, 52.4, 53.6, 52.1,
]  # fmt: skip

# EWMA_0 (target) through EWMA_20, 21 values, per the re-verified NIST table.
NIST_EWMA_0_THROUGH_20 = [
    50.00, 50.60, 49.52, 50.56, 50.18, 50.16, 49.21, 49.75, 49.85, 50.26,
    50.33, 50.11, 49.36, 49.52, 50.05, 49.38, 49.92, 50.73, 51.23, 51.94, 51.99,
]  # fmt: skip

NIST_TARGET = 50.0
NIST_SIGMA = 2.0539
NIST_LAMBDA = 0.3
NIST_L = 3.0
NIST_UCL = 52.5884
NIST_LCL = 47.4115
TOL = 1e-2


def test_ewma_series_matches_nist_table_pointwise():
    series = ewma_series(NIST_X, target=NIST_TARGET, lam=NIST_LAMBDA)
    assert len(series) == len(NIST_EWMA_0_THROUGH_20)
    for computed, expected in zip(series, NIST_EWMA_0_THROUGH_20, strict=True):
        assert computed == pytest.approx(expected, abs=TOL)


def test_ewma_control_limits_match_nist():
    limits = fit_phase_i(target=NIST_TARGET, sigma=NIST_SIGMA, lam=NIST_LAMBDA, l_factor=NIST_L)
    assert limits.center_line == pytest.approx(NIST_TARGET, abs=TOL)
    assert limits.ucl == pytest.approx(NIST_UCL, abs=TOL)
    assert limits.lcl == pytest.approx(NIST_LCL, abs=TOL)


def test_ewma_process_is_in_control_per_nist_conclusion():
    limits = fit_phase_i(target=NIST_TARGET, sigma=NIST_SIGMA, lam=NIST_LAMBDA, l_factor=NIST_L)
    points = apply_phase_ii(NIST_X, limits)
    assert len(points) == len(NIST_X)
    assert not any(p.out_of_control for p in points)
