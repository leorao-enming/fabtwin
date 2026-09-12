"""Unit tests for src/fabtwin/spc/xbar_r.py - error handling, not the NIST-
constant fixture (that lives in tests/validation/test_xbar_r_nist_constants.py).
"""

import pytest

from fabtwin.spc.xbar_r import apply_phase_ii, fit_phase_i, subgroup_constants


def test_subgroup_constants_rejects_unsupported_n():
    with pytest.raises(ValueError, match="published range is 2..10"):
        subgroup_constants(15)


def test_fit_phase_i_rejects_unequal_subgroup_sizes():
    with pytest.raises(ValueError, match="same size"):
        fit_phase_i([[1, 2, 3, 4, 5], [1, 2, 3, 4]])


def test_fit_phase_i_rejects_subgroup_size_one():
    with pytest.raises(ValueError, match="must be >= 2"):
        fit_phase_i([[1], [2], [3]])


def test_fit_phase_i_rejects_fewer_than_two_subgroups():
    with pytest.raises(ValueError, match="at least 2 subgroups"):
        fit_phase_i([[1, 2, 3, 4, 5]])


def test_apply_phase_ii_rejects_mismatched_subgroup_size():
    limits = fit_phase_i([[1, 2, 3, 4, 5], [2, 3, 4, 5, 6], [1, 3, 5, 7, 9]])
    with pytest.raises(ValueError, match="must all have size n=5"):
        apply_phase_ii([[1, 2, 3, 4]], limits)


def test_apply_phase_ii_detects_out_of_control_subgroup():
    healthy = [[9, 10, 11, 10, 10]] * 10
    limits = fit_phase_i(healthy)
    spiked = healthy + [[50, 51, 49, 50, 50]]  # blatant mean shift
    xbar_points, _ = apply_phase_ii(spiked, limits)
    assert xbar_points[-1].out_of_control is True
    assert not any(p.out_of_control for p in xbar_points[:-1])
