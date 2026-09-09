"""Unit tests for src/fabtwin/metrics.py."""

import numpy as np
import pytest

from fabtwin.metrics import (
    defect_count_for_wafer,
    etch_rate_from_depth,
    wiwnu_from_site_depths,
)


def test_etch_rate_formula():
    # 120 nm over 60s => 120 nm/min, per data-dictionary.md section 3.
    assert etch_rate_from_depth(120.0, 60.0) == pytest.approx(120.0)
    assert etch_rate_from_depth(60.0, 30.0) == pytest.approx(120.0)


def test_wiwnu_known_value():
    # SEMI-style: (max-min)/(2*mean)*100
    depths = [100.0, 100.0, 90.0, 110.0, 100.0]
    mean = sum(depths) / len(depths)  # 100
    expected = (110.0 - 90.0) / (2 * mean) * 100.0  # 10.0
    assert wiwnu_from_site_depths(depths) == pytest.approx(expected)
    assert wiwnu_from_site_depths(depths) == pytest.approx(10.0)


def test_wiwnu_zero_for_uniform_wafer():
    assert wiwnu_from_site_depths([100.0] * 5) == pytest.approx(0.0)


def test_wiwnu_empty_is_zero_not_error():
    assert wiwnu_from_site_depths([]) == 0.0


def test_defect_count_is_nonnegative_integer():
    rng = np.random.default_rng(0)
    for _ in range(50):
        count = defect_count_for_wafer(rng, base_rate=2.0)
        assert isinstance(count, int)
        assert count >= 0


def test_defect_count_mean_tracks_base_rate_over_many_draws():
    rng = np.random.default_rng(0)
    draws = [defect_count_for_wafer(rng, base_rate=5.0) for _ in range(5000)]
    assert 4.5 < np.mean(draws) < 5.5


def test_defect_count_fault_delta_shifts_mean_up():
    rng_base = np.random.default_rng(0)
    rng_shifted = np.random.default_rng(0)
    base_draws = [defect_count_for_wafer(rng_base, base_rate=2.0) for _ in range(3000)]
    shifted_draws = [
        defect_count_for_wafer(rng_shifted, base_rate=2.0, fault_delta=10.0) for _ in range(3000)
    ]
    assert np.mean(shifted_draws) > np.mean(base_draws) + 5


def test_defect_count_variance_inflation_increases_spread_at_same_mean():
    rng_a = np.random.default_rng(0)
    rng_b = np.random.default_rng(0)
    normal_draws = [defect_count_for_wafer(rng_a, base_rate=5.0) for _ in range(5000)]
    inflated_draws = [
        defect_count_for_wafer(rng_b, base_rate=5.0, variance_multiplier=4.0) for _ in range(5000)
    ]
    assert np.var(inflated_draws) > np.var(normal_draws) * 1.5


def test_defect_count_sensor_bias_shifts_reported_count_floored_at_zero():
    rng = np.random.default_rng(0)
    biased = defect_count_for_wafer(rng, base_rate=0.0, sensor_bias=-100.0)
    assert biased == 0
