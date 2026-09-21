"""Distribution/variance-decomposition validation - the third and last of
Gate T1's three deliverables per Overview section 2 ("可复现的 hierarchical
simulator、数据字典、分布/方差分解验证"). The other two (a reproducible
simulator, the data dictionary) were already validated by
tests/unit/test_simulator.py and docs/data-dictionary.md; this file closes
the gap.

Overview section 4.1 requires the simulator to "显式分开 fixed recipe
effect、tool/chamber random effect、lot/wafer effect...与 measurement
noise" - each an independent, config-controlled random layer. This module
tests that requirement directly, not just that the code runs: isolate each
layer (zero out the others), draw a large sample through the real
simulate() pipeline, and check the empirical variance matches the
configured sigma. Then combine all layers and check that pooled variance
decomposes additively - Var(total) = sigma_lot^2 + sigma_wafer^2 +
sigma_site^2 for independent nested normal random effects, standard nested
variance-components theory (equivalent to a one-way/nested random-effects
ANOVA decomposition).

Tolerances here are Monte Carlo sampling error, not floating-point error -
picked generously (25% relative) against the sample sizes used so the
tests are stable, not flaky, while still being sensitive enough to catch a
real implementation bug (e.g. a layer silently not applied, or two layers
swapped).
"""

from datetime import datetime

import numpy as np
import pytest

from fabtwin.config import (
    HierarchyConfig,
    RandomEffectConfig,
    RecipeConfig,
    SimulationConfig,
    ToolChamberConfig,
)
from fabtwin.simulator import simulate

RECIPE = RecipeConfig(
    recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
)
REL_TOL = 0.25


def _etch_depth_values(config: SimulationConfig) -> np.ndarray:
    obs = simulate(config).observations
    return obs[obs["metric"] == "etch_depth"]["value"].to_numpy()


def test_lot_effect_variance_matches_config_sigma_when_isolated():
    lot_sigma = 10.0
    config = SimulationConfig(
        seed=1,
        start_time=datetime(2026, 1, 1),
        recipe=RECIPE,
        tool_chambers=[ToolChamberConfig(tool_id="T1", chamber_id="A", depth_offset_sigma_nm=0.0)],
        hierarchy=HierarchyConfig(
            lot_size_wafers=1, sites_per_wafer=1, n_lots=800, lot_interval_minutes=10
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=lot_sigma, wafer_sigma_nm=0.0, site_noise_sigma_nm=0.0
        ),
    )
    values = _etch_depth_values(config)
    empirical_var = float(np.var(values, ddof=1))
    assert empirical_var == pytest.approx(lot_sigma**2, rel=REL_TOL)


def test_wafer_effect_variance_matches_config_sigma_when_isolated():
    wafer_sigma = 8.0
    config = SimulationConfig(
        seed=2,
        start_time=datetime(2026, 1, 1),
        recipe=RECIPE,
        tool_chambers=[ToolChamberConfig(tool_id="T1", chamber_id="A", depth_offset_sigma_nm=0.0)],
        hierarchy=HierarchyConfig(
            lot_size_wafers=40, sites_per_wafer=1, n_lots=20, lot_interval_minutes=10
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=0.0, wafer_sigma_nm=wafer_sigma, site_noise_sigma_nm=0.0
        ),
    )
    values = _etch_depth_values(config)
    empirical_var = float(np.var(values, ddof=1))
    assert empirical_var == pytest.approx(wafer_sigma**2, rel=REL_TOL)


def test_site_noise_variance_matches_config_sigma_when_isolated():
    site_sigma = 5.0
    config = SimulationConfig(
        seed=3,
        start_time=datetime(2026, 1, 1),
        recipe=RECIPE,
        tool_chambers=[ToolChamberConfig(tool_id="T1", chamber_id="A", depth_offset_sigma_nm=0.0)],
        hierarchy=HierarchyConfig(
            lot_size_wafers=5, sites_per_wafer=5, n_lots=40, lot_interval_minutes=10
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=0.0, wafer_sigma_nm=0.0, site_noise_sigma_nm=site_sigma
        ),
    )
    values = _etch_depth_values(config)
    empirical_var = float(np.var(values, ddof=1))
    assert empirical_var == pytest.approx(site_sigma**2, rel=REL_TOL)


def test_tool_chamber_offset_variance_matches_config_sigma():
    """Not a within-run variance (a single chamber's offset is one fixed
    draw per run - see effects.py) but the across-chamber spread: many
    chambers on one tool, each getting its own offset draw, per Overview
    4.1's "tool/chamber random effect" - checked by drawing many chambers'
    worth of offsets through the real simulate() pipeline (one lot/wafer/
    site each, other layers zeroed) and looking at the spread of their
    per-chamber means.
    """
    offset_sigma = 12.0
    n_chambers = 300
    config = SimulationConfig(
        seed=4,
        start_time=datetime(2026, 1, 1),
        recipe=RECIPE,
        tool_chambers=[
            ToolChamberConfig(
                tool_id="T1", chamber_id=f"CH-{i:04d}", depth_offset_sigma_nm=offset_sigma
            )
            for i in range(n_chambers)
        ],
        hierarchy=HierarchyConfig(
            lot_size_wafers=1, sites_per_wafer=1, n_lots=1, lot_interval_minutes=10
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=0.0, wafer_sigma_nm=0.0, site_noise_sigma_nm=0.0
        ),
    )
    values = _etch_depth_values(config)
    assert len(values) == n_chambers
    empirical_var = float(np.var(values, ddof=1))
    assert empirical_var == pytest.approx(offset_sigma**2, rel=REL_TOL)


def test_combined_variance_decomposes_additively_across_layers():
    """The key "distribution/variance-decomposition" claim: with lot,
    wafer, and site-noise all active simultaneously, the pooled variance
    of every site-level etch_depth observation equals the sum of the three
    layers' variances - not, e.g., their max, their product, or a
    silently-dropped subset.
    """
    lot_sigma, wafer_sigma, site_sigma = 10.0, 6.0, 4.0
    config = SimulationConfig(
        seed=5,
        start_time=datetime(2026, 1, 1),
        recipe=RECIPE,
        tool_chambers=[ToolChamberConfig(tool_id="T1", chamber_id="A", depth_offset_sigma_nm=0.0)],
        hierarchy=HierarchyConfig(
            lot_size_wafers=8, sites_per_wafer=5, n_lots=150, lot_interval_minutes=10
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=lot_sigma, wafer_sigma_nm=wafer_sigma, site_noise_sigma_nm=site_sigma
        ),
    )
    values = _etch_depth_values(config)
    empirical_var = float(np.var(values, ddof=1))
    expected_var = lot_sigma**2 + wafer_sigma**2 + site_sigma**2
    assert empirical_var == pytest.approx(expected_var, rel=REL_TOL)


def test_variance_direction_tracks_config_sigma_monotonically():
    """Overview 4.6's own wording: "健康数据的方差分解方向与 config 一致" -
    the *direction*, not just a point estimate. Doubling a configured
    sigma must (with high probability, same seed for both to remove
    independent-draw noise as a confound) roughly quadruple that layer's
    variance contribution, not leave it unchanged or invert it.
    """

    def make_config(site_sigma: float) -> SimulationConfig:
        return SimulationConfig(
            seed=6,
            start_time=datetime(2026, 1, 1),
            recipe=RECIPE,
            tool_chambers=[
                ToolChamberConfig(tool_id="T1", chamber_id="A", depth_offset_sigma_nm=0.0)
            ],
            hierarchy=HierarchyConfig(
                lot_size_wafers=5, sites_per_wafer=5, n_lots=60, lot_interval_minutes=10
            ),
            random_effects=RandomEffectConfig(
                lot_sigma_nm=0.0, wafer_sigma_nm=0.0, site_noise_sigma_nm=site_sigma
            ),
        )

    small_var = float(np.var(_etch_depth_values(make_config(3.0)), ddof=1))
    large_var = float(np.var(_etch_depth_values(make_config(6.0)), ddof=1))
    assert large_var > small_var * 2  # should roughly quadruple; well above noise if it doesn't
