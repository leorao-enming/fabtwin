"""Known-answer test: Xbar-R chart, using NIST's own published A2/D3/D4
constants (section 6.3.2.1, https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc321.htm)
applied to a small hand-computed, hand-verified fixture.

PROVENANCE: this is NOT a NIST worked example - NIST's handbook does not
publish one for Xbar-R (confirmed 2026-09-12 by fetching both the formula
page and the chart-overview page). It IS built from NIST's real published
constants table for n=5 (A2=0.577, D3=0, D4=2.115), which is the part of
"与手算或独立 fixture 一致" (Overview section 4.6) this test satisfies: the
constants are externally sourced, the arithmetic is hand-verified, and the
distinction from a true NIST worked example (like test_imr_nist.py,
test_ewma_nist.py, test_cusum_nist.py) is recorded here rather than implied.

Fixture: 5 subgroups of n=5, each subgroup summing to 50 (mean=10 exactly,
by construction, so Xbar-bar is trivial to verify by hand) with varying
ranges to give a non-trivial Rbar.
"""

import pytest

from fabtwin.spc.xbar_r import fit_phase_i, subgroup_constants

SUBGROUPS = [
    [8, 10, 12, 10, 10],   # range 4
    [9, 11, 10, 10, 10],   # range 2
    [10, 10, 10, 10, 10],  # range 0
    [7, 13, 10, 10, 10],   # range 6
    [11, 9, 10, 10, 10],   # range 2
]  # fmt: skip

# Hand computation:
# every subgroup sums to 50 -> every subgroup mean = 10 -> Xbar-bar = 10
# ranges = [4, 2, 0, 6, 2] -> Rbar = 14/5 = 2.8
# A2(n=5)=0.577, D3(n=5)=0.0, D4(n=5)=2.115 (NIST table, verbatim)
EXPECTED_XBAR_BAR = 10.0
EXPECTED_R_BAR = 2.8
A2, D3, D4 = 0.577, 0.0, 2.115
TOL = 1e-9  # exact by construction - no rounding anywhere in the hand computation


def test_nist_constants_for_n5_match_published_table():
    assert subgroup_constants(5) == (0.577, 0.0, 2.115)


def test_xbar_bar_and_r_bar_match_hand_computation():
    limits = fit_phase_i(SUBGROUPS)
    assert limits.xbar_limits.center_line == pytest.approx(EXPECTED_XBAR_BAR, abs=TOL)
    assert limits.r_limits.center_line == pytest.approx(EXPECTED_R_BAR, abs=TOL)


def test_xbar_control_limits_match_hand_computation():
    limits = fit_phase_i(SUBGROUPS)
    expected_ucl = EXPECTED_XBAR_BAR + A2 * EXPECTED_R_BAR  # 10 + 0.577*2.8 = 11.6156
    expected_lcl = EXPECTED_XBAR_BAR - A2 * EXPECTED_R_BAR  # 8.3844
    assert limits.xbar_limits.ucl == pytest.approx(expected_ucl, abs=1e-9)
    assert limits.xbar_limits.lcl == pytest.approx(expected_lcl, abs=1e-9)


def test_r_control_limits_match_hand_computation():
    limits = fit_phase_i(SUBGROUPS)
    expected_ucl = D4 * EXPECTED_R_BAR  # 2.115*2.8 = 5.922
    expected_lcl = D3 * EXPECTED_R_BAR  # 0.0
    assert limits.r_limits.ucl == pytest.approx(expected_ucl, abs=1e-9)
    assert limits.r_limits.lcl == pytest.approx(expected_lcl, abs=1e-9)
