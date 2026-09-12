"""Known-answer test: CUSUM chart against the NIST Engineering Statistics
Handbook worked example, section 6.3.2.3 (CUSUM Control Charts),
https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm.

Traceable to Overview section 4.6 acceptance bullet: "与手算或独立 fixture
一致：...CUSUM；浮点 tolerance 写入测试。"

The page was fetched a second time requesting the full (i, x_i, S_hi, S_lo)
table (all 20 rows) rather than trusting a first, possibly-summarized
extraction - same discipline as the EWMA fixture. Several points (i=1, 2,
4, 13, 14) were hand-recomputed from the recursion to confirm the table
before it was hardcoded here.
"""

import pytest

from fabtwin.spc.cusum import apply_phase_ii, fit_phase_i

NIST_X = [
    324.925, 324.675, 324.725, 324.350, 325.350, 325.225, 324.125, 324.525, 325.225, 324.600,
    324.625, 325.150, 328.325, 327.250, 327.825, 328.500, 326.675, 327.775, 326.875, 328.350,
]  # fmt: skip

NIST_S_HI = [
    0.00, 0.00, 0.00, 0.00, 0.03, 0.00, 0.00, 0.00, 0.00, 0.00,
    0.00, 0.00, 3.01, 4.94, 7.45, 10.63, 11.99, 14.44, 16.00, 19.04,
]  # fmt: skip

NIST_S_LO = [
    0.00, 0.01, 0.00, 0.33, 0.00, 0.00, 0.56, 0.72, 0.17, 0.25,
    0.31, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00,
]  # fmt: skip

TARGET = 325.0
K = 0.3175
H = 4.1959
TOL = 0.02  # NIST's table itself is rounded to 2 decimals


def test_cusum_s_hi_matches_nist_table():
    limits = fit_phase_i(target=TARGET, k=K, h=H)
    points = apply_phase_ii(NIST_X, limits)
    for point, expected in zip(points, NIST_S_HI, strict=True):
        assert point.s_hi == pytest.approx(expected, abs=TOL)


def test_cusum_s_lo_matches_nist_table():
    limits = fit_phase_i(target=TARGET, k=K, h=H)
    points = apply_phase_ii(NIST_X, limits)
    for point, expected in zip(points, NIST_S_LO, strict=True):
        assert point.s_lo == pytest.approx(expected, abs=TOL)


def test_cusum_signals_out_of_control_starting_at_group_14():
    """NIST: S_hi first exceeds h=4.1959 at group 14 (1-indexed) and stays
    out of control through group 20; S_lo never signals.
    """
    limits = fit_phase_i(target=TARGET, k=K, h=H)
    points = apply_phase_ii(NIST_X, limits)
    ooc_flags = [p.out_of_control for p in points]
    assert ooc_flags[:13] == [False] * 13  # groups 1-13 (0-indexed 0-12) in control
    assert all(ooc_flags[13:])  # groups 14-20 (0-indexed 13-19) out of control
