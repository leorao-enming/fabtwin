"""Unit tests for src/fabtwin/simulator.py - the orchestrator.

Case-1-style scenario (chamber drift, Overview section 4.4) is used as the
integration check: a linear_drift fault on one chamber must show up in that
chamber's etch_depth and must NOT leak into the sibling chamber.
"""

from datetime import datetime

import pytest

from fabtwin.config import (
    FaultEvent,
    HierarchyConfig,
    RandomEffectConfig,
    RecipeConfig,
    SimulationConfig,
    ToolChamberConfig,
)
from fabtwin.simulator import OBSERVATION_COLUMNS, simulate


def _base_config(**overrides) -> SimulationConfig:
    base = dict(
        seed=42,
        start_time=datetime(2026, 1, 1),
        recipe=RecipeConfig(
            recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
        ),
        tool_chambers=[
            ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-A"),
            ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-B"),
        ],
        hierarchy=HierarchyConfig(
            lot_size_wafers=5, sites_per_wafer=5, n_lots=6, lot_interval_minutes=30
        ),
        random_effects=RandomEffectConfig(),
    )
    base.update(overrides)
    return SimulationConfig(**base)


def test_same_seed_is_fully_reproducible():
    config = _base_config()
    result_a = simulate(config)
    result_b = simulate(config)
    assert result_a.observations.equals(result_b.observations)


def test_different_seed_produces_different_values():
    result_a = simulate(_base_config(seed=1))
    result_b = simulate(_base_config(seed=2))
    assert not result_a.observations["value"].equals(result_b.observations["value"])


def test_observation_table_has_exactly_the_locked_columns():
    result = simulate(_base_config())
    assert list(result.observations.columns) == list(OBSERVATION_COLUMNS)


def test_hidden_truth_not_present_in_observation_columns():
    result = simulate(_base_config())
    forbidden = {"fault_type", "onset", "magnitude", "depth_offset_sigma_nm", "random_seed"}
    assert forbidden.isdisjoint(result.observations.columns)


def test_wafer_level_metrics_have_null_site_id_site_level_do_not():
    obs = simulate(_base_config()).observations
    wafer_level = obs[obs["metric"].isin(["wiwnu", "defect_count"])]
    site_level = obs[obs["metric"].isin(["etch_depth", "etch_rate", "cd_bias"])]
    assert wafer_level["site_id"].isna().all()
    assert site_level["site_id"].notna().all()


def test_row_counts_match_hierarchy_config():
    hierarchy = HierarchyConfig(
        lot_size_wafers=3, sites_per_wafer=5, n_lots=2, lot_interval_minutes=10
    )
    config = _base_config(hierarchy=hierarchy)
    obs = simulate(config).observations
    n_chambers = len(config.tool_chambers)
    n_wafers = hierarchy.n_lots * hierarchy.lot_size_wafers * n_chambers
    expected_site_rows = n_wafers * hierarchy.sites_per_wafer * 3  # etch_depth, etch_rate, cd_bias
    expected_wafer_rows = n_wafers * 2  # wiwnu, defect_count
    assert len(obs) == expected_site_rows + expected_wafer_rows


def test_etch_rate_is_consistent_with_stored_etch_depth():
    config = _base_config()
    obs = simulate(config).observations
    depth = obs[obs["metric"] == "etch_depth"].set_index(["wafer_id", "site_id"])["value"]
    rate = obs[obs["metric"] == "etch_rate"].set_index(["wafer_id", "site_id"])["value"]
    recomputed = depth / config.recipe.etch_time_s * 60.0
    assert recomputed.sort_index().equals(rate.sort_index())


def test_chamber_drift_shifts_only_the_faulted_chamber():
    onset = datetime(2026, 1, 1)
    config = _base_config(
        start_time=onset,
        hierarchy=HierarchyConfig(
            lot_size_wafers=10, sites_per_wafer=5, n_lots=20, lot_interval_minutes=60
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=0.5, wafer_sigma_nm=0.5, site_noise_sigma_nm=0.5
        ),
        faults=[
            FaultEvent(
                event_id="DRIFT-1",
                fault_type="linear_drift",
                onset=onset,
                tool_id="TOOL-01",
                chamber_id="CH-A",
                metric="etch_depth",
                magnitude=5.0,  # nm/hour
            )
        ],
    )
    obs = simulate(config).observations
    depth = obs[obs["metric"] == "etch_depth"]

    ch_a_first = depth[(depth["chamber_id"] == "CH-A") & (depth["lot_id"].str.endswith("-0000"))][
        "value"
    ].mean()
    ch_a_last = depth[(depth["chamber_id"] == "CH-A") & (depth["lot_id"].str.endswith("-0019"))][
        "value"
    ].mean()
    ch_b_first = depth[(depth["chamber_id"] == "CH-B") & (depth["lot_id"].str.endswith("-0000"))][
        "value"
    ].mean()
    ch_b_last = depth[(depth["chamber_id"] == "CH-B") & (depth["lot_id"].str.endswith("-0019"))][
        "value"
    ].mean()

    assert ch_a_last - ch_a_first > 50  # ~19 hours * 5 nm/hour, well above noise
    assert abs(ch_b_last - ch_b_first) < 10  # sibling chamber stays flat


def test_rejects_sites_per_wafer_beyond_v1_site_pattern():
    with pytest.raises(ValueError, match="site pattern"):
        simulate(_base_config(hierarchy=HierarchyConfig(sites_per_wafer=9)))
