"""Unit tests for src/fabtwin/effects.py.

These are directional/reproducibility checks on the synthetic fixed-effect
formula and the random-effect draws - not known-answer NIST-style tests
(those land at Gate T2 for the SPC layer, per tests/validation/README.md).
"""

import numpy as np

from fabtwin.config import RecipeConfig, ToolChamberConfig
from fabtwin.effects import (
    draw_lot_effect,
    draw_tool_chamber_offsets,
    draw_wafer_effect,
    fixed_effect_cd_bias_nm,
    fixed_effect_etch_depth_nm,
    measurement_noise,
)


def _recipe(**overrides) -> RecipeConfig:
    base = dict(recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60)
    base.update(overrides)
    return RecipeConfig(**base)


def test_higher_rf_power_increases_etch_depth():
    low = fixed_effect_etch_depth_nm(_recipe(rf_power_w=150))
    high = fixed_effect_etch_depth_nm(_recipe(rf_power_w=250))
    assert high > low


def test_higher_pressure_decreases_etch_depth():
    low_pressure = fixed_effect_etch_depth_nm(_recipe(pressure_mtorr=30))
    high_pressure = fixed_effect_etch_depth_nm(_recipe(pressure_mtorr=80))
    assert low_pressure > high_pressure


def test_longer_etch_time_increases_etch_depth():
    short = fixed_effect_etch_depth_nm(_recipe(etch_time_s=30))
    long_ = fixed_effect_etch_depth_nm(_recipe(etch_time_s=90))
    assert long_ > short


def test_fixed_effect_is_deterministic():
    r = _recipe()
    assert fixed_effect_etch_depth_nm(r) == fixed_effect_etch_depth_nm(r)
    assert fixed_effect_cd_bias_nm(r) == fixed_effect_cd_bias_nm(r)


def test_tool_chamber_offsets_reproducible_with_same_seed():
    tool_chambers = [
        ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-A"),
        ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-B"),
    ]
    offsets_a = draw_tool_chamber_offsets(tool_chambers, np.random.default_rng(42))
    offsets_b = draw_tool_chamber_offsets(tool_chambers, np.random.default_rng(42))
    assert offsets_a == offsets_b
    # different chambers get different draws (not a shared constant)
    assert offsets_a[("TOOL-01", "CH-A")] != offsets_a[("TOOL-01", "CH-B")]


def test_zero_sigma_draws_are_exactly_zero():
    rng = np.random.default_rng(1)
    assert draw_lot_effect(rng, 0.0) == 0.0
    assert draw_wafer_effect(rng, 0.0) == 0.0
    assert measurement_noise(rng, 0.0) == 0.0


def test_positive_sigma_draws_vary_across_calls():
    rng = np.random.default_rng(1)
    draws = {draw_lot_effect(rng, 5.0) for _ in range(20)}
    assert len(draws) > 1
