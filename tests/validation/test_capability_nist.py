"""Known-answer test: process capability indices against the NIST
Engineering Statistics Handbook worked example, section 6.1.6 (Process
Capability Indices),
https://www.itl.nist.gov/div898/handbook/pmc/section1/pmc16.htm.

Traceable to Overview section 4.6 acceptance bullet: "与手算或独立 fixture
一致：...Cp/Cpk/Pp/Ppk；浮点 tolerance 写入测试。"

NIST's worked example: USL=20, LSL=8, xbar=16, s=2 -> Cp=1.0, Cpk=0.6667,
Cpu=0.6667, Cpl=1.3333. NIST does not distinguish within- vs overall-sigma
in this particular example (a single s is given); this test exercises the
shared _capability_from_sigma() math core via cp_cpk(), since that is the
function the fixture's numbers were designed against.
"""

import pytest

from fabtwin.spc.capability import cp_cpk

USL, LSL, MEAN, SIGMA = 20.0, 8.0, 16.0, 2.0
TOL = 1e-3


def test_cp_matches_nist():
    result = cp_cpk(mean=MEAN, sigma_within=SIGMA, usl=USL, lsl=LSL)
    assert result.cp_or_pp == pytest.approx(1.0, abs=TOL)


def test_cpk_matches_nist():
    result = cp_cpk(mean=MEAN, sigma_within=SIGMA, usl=USL, lsl=LSL)
    assert result.cpk_or_ppk == pytest.approx(0.6667, abs=TOL)


def test_cpu_and_cpl_match_nist():
    result = cp_cpk(mean=MEAN, sigma_within=SIGMA, usl=USL, lsl=LSL)
    assert result.upper_index == pytest.approx(0.6667, abs=TOL)
    assert result.lower_index == pytest.approx(1.3333, abs=TOL)


def test_cpk_is_the_minimum_of_cpu_and_cpl():
    result = cp_cpk(mean=MEAN, sigma_within=SIGMA, usl=USL, lsl=LSL)
    assert result.cpk_or_ppk == min(result.upper_index, result.lower_index)


def test_nist_conclusion_process_not_good_enough():
    # NIST: "we would like to have Cpk at least 1.0, so this is not a good process."
    result = cp_cpk(mean=MEAN, sigma_within=SIGMA, usl=USL, lsl=LSL)
    assert result.cpk_or_ppk < 1.0
