"""Unit tests for src/fabtwin/spc/cusum.py - behavior not pinned to the
NIST fixture (that lives in tests/validation/test_cusum_nist.py).
"""

from fabtwin.spc.cusum import apply_phase_ii, fit_phase_i


def test_s_hi_and_s_lo_floor_at_zero():
    # target=10, k=1: a value far below target should NOT drive s_hi negative,
    # it must floor at 0 per the max(0, ...) recursion.
    limits = fit_phase_i(target=10.0, k=1.0, h=5.0)
    points = apply_phase_ii([0.0, 0.0, 0.0], limits)
    assert all(p.s_hi == 0.0 for p in points)


def test_cusum_flags_persistent_upward_shift():
    limits = fit_phase_i(target=10.0, k=0.5, h=4.0)
    # Small persistent shift above target+k accumulates in s_hi over time.
    points = apply_phase_ii([12.0] * 10, limits)
    assert points[0].out_of_control is False
    assert points[-1].out_of_control is True
    assert points[-1].s_hi > points[0].s_hi


def test_cusum_flags_persistent_downward_shift_via_s_lo():
    limits = fit_phase_i(target=10.0, k=0.5, h=4.0)
    points = apply_phase_ii([8.0] * 10, limits)
    assert points[-1].out_of_control is True
    assert points[-1].s_lo > 0
    assert points[-1].s_hi == 0.0


def test_cusum_params_recorded_in_frozen_limits():
    limits = fit_phase_i(target=10.0, k=0.5, h=4.0)
    assert limits.params == {"target": 10.0, "k": 0.5, "h": 4.0}
