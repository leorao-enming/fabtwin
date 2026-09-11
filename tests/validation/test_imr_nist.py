"""Known-answer test: I-MR chart against the NIST Engineering Statistics
Handbook worked example, section 6.3.2.2 (Individuals Control Charts),
https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm.

Traceable to Overview section 4.6 acceptance bullet: "与手算或独立 fixture
一致：I-MR、Xbar-R、Xbar-S、EWMA、CUSUM；浮点 tolerance 写入测试。"

NIST's worked example: 10 flowrate batches, MRbar computed from consecutive
absolute differences, d2=1.128 for n=2, limits = xbar +/- 3*(MRbar/d2).
NIST states the process is in control (no point outside the limits).
"""

import pytest

from fabtwin.spc.imr import apply_phase_ii, fit_phase_i

# NIST worked example raw data, verbatim.
NIST_DATA = [49.6, 47.6, 49.9, 51.3, 47.8, 51.2, 52.6, 52.4, 53.6, 52.1]

# NIST-stated results, to float tolerance.
NIST_XBAR = 50.81
NIST_MR_BAR = 1.8778
NIST_UCL = 55.8041
NIST_LCL = 45.8159
TOL = 1e-3


def test_imr_center_line_matches_nist():
    limits = fit_phase_i(NIST_DATA)
    assert limits.center_line == pytest.approx(NIST_XBAR, abs=TOL)


def test_imr_mr_bar_matches_nist():
    limits = fit_phase_i(NIST_DATA)
    assert limits.params["mr_bar"] == pytest.approx(NIST_MR_BAR, abs=TOL)


def test_imr_control_limits_match_nist():
    limits = fit_phase_i(NIST_DATA)
    assert limits.ucl == pytest.approx(NIST_UCL, abs=TOL)
    assert limits.lcl == pytest.approx(NIST_LCL, abs=TOL)


def test_imr_process_is_in_control_per_nist_conclusion():
    """NIST: "the process is in control, since none of the plotted points
    fall outside either the UCL or LCL." Phase II here is scored against
    the same data used to fit Phase I, matching NIST's own worked example
    (which does not separate a distinct Phase II window) - production case
    studies must use a distinct Phase II window per Overview section 4.2.
    """
    limits = fit_phase_i(NIST_DATA)
    points = apply_phase_ii(NIST_DATA, limits)
    assert not any(p.out_of_control for p in points)
