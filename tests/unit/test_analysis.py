"""Integration tests: simulator (T1) output -> SPC/capability layer (T2).

Every test here calls simulate() for real and feeds the resulting
observation table through analysis.py - unlike tests/unit/test_spc.py
(hand-built lists) and tests/validation/test_*_nist.py (static NIST data),
this file is where the two halves of the pipeline actually meet.
"""

from datetime import datetime, timedelta

import pytest

from fabtwin.analysis import (
    extract_lot_series,
    run_capability,
    run_ewma,
    run_imr,
    split_phase_i_ii,
)
from fabtwin.config import (
    FaultEvent,
    HierarchyConfig,
    RandomEffectConfig,
    RecipeConfig,
    SimulationConfig,
    ToolChamberConfig,
)
from fabtwin.simulator import simulate


def _recipe() -> RecipeConfig:
    return RecipeConfig(
        recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
    )


def test_extract_lot_series_shape_and_order():
    config = SimulationConfig(
        seed=1,
        start_time=datetime(2026, 1, 1),
        recipe=_recipe(),
        tool_chambers=[ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-A")],
        hierarchy=HierarchyConfig(
            lot_size_wafers=3, sites_per_wafer=5, n_lots=5, lot_interval_minutes=10
        ),
    )
    obs = simulate(config).observations
    series = extract_lot_series(obs, "TOOL-01", "CH-A", "etch_depth")
    assert list(series.columns) == ["lot_id", "timestamp", "value"]
    assert len(series) == 5
    assert list(series["timestamp"]) == sorted(series["timestamp"])


def test_extract_lot_series_raises_for_unknown_combo():
    config = SimulationConfig(
        seed=1,
        start_time=datetime(2026, 1, 1),
        recipe=_recipe(),
        tool_chambers=[ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-A")],
        hierarchy=HierarchyConfig(
            lot_size_wafers=3, sites_per_wafer=5, n_lots=3, lot_interval_minutes=10
        ),
    )
    obs = simulate(config).observations
    with pytest.raises(ValueError, match="no observations"):
        extract_lot_series(obs, "TOOL-01", "CH-DOES-NOT-EXIST", "etch_depth")


def test_split_phase_i_ii_rejects_too_small_phase_i():
    config = SimulationConfig(
        seed=1,
        start_time=datetime(2026, 1, 1),
        recipe=_recipe(),
        tool_chambers=[ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-A")],
        hierarchy=HierarchyConfig(
            lot_size_wafers=3, sites_per_wafer=5, n_lots=5, lot_interval_minutes=10
        ),
    )
    series = extract_lot_series(simulate(config).observations, "TOOL-01", "CH-A", "etch_depth")
    with pytest.raises(ValueError, match="at least 2"):
        split_phase_i_ii(series, phase_i_n_lots=1)


def test_split_phase_i_ii_rejects_phase_i_consuming_everything():
    config = SimulationConfig(
        seed=1,
        start_time=datetime(2026, 1, 1),
        recipe=_recipe(),
        tool_chambers=[ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-A")],
        hierarchy=HierarchyConfig(
            lot_size_wafers=3, sites_per_wafer=5, n_lots=5, lot_interval_minutes=10
        ),
    )
    series = extract_lot_series(simulate(config).observations, "TOOL-01", "CH-A", "etch_depth")
    with pytest.raises(ValueError, match="leaves no Phase II data"):
        split_phase_i_ii(series, phase_i_n_lots=5)


def _chamber_drift_config(onset: datetime) -> SimulationConfig:
    return SimulationConfig(
        seed=42,
        start_time=onset,
        recipe=_recipe(),
        tool_chambers=[
            ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-A"),
            ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-B"),
        ],
        hierarchy=HierarchyConfig(
            lot_size_wafers=10, sites_per_wafer=5, n_lots=30, lot_interval_minutes=60
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=0.5, wafer_sigma_nm=0.5, site_noise_sigma_nm=0.5
        ),
        faults=[
            FaultEvent(
                event_id="DRIFT-1",
                fault_type="linear_drift",
                onset=onset + timedelta(hours=10),  # starts after Phase I window
                tool_id="TOOL-01",
                chamber_id="CH-A",
                metric="etch_depth",
                magnitude=5.0,  # nm/hour
            )
        ],
    )


def test_run_imr_end_to_end_flags_drifting_chamber_not_sibling():
    onset = datetime(2026, 1, 1)
    obs = simulate(_chamber_drift_config(onset)).observations

    # first 10 lots (10 hours) are pre-fault -> valid Phase I window for CH-A too.
    drifting = run_imr(obs, "TOOL-01", "CH-A", "etch_depth", phase_i_n_lots=10)
    healthy = run_imr(obs, "TOOL-01", "CH-B", "etch_depth", phase_i_n_lots=10)

    assert drifting.any_out_of_control is True
    assert healthy.any_out_of_control is False
    assert drifting.first_alarm_index is not None


def test_run_ewma_end_to_end_flags_drifting_chamber_not_sibling():
    onset = datetime(2026, 1, 1)
    obs = simulate(_chamber_drift_config(onset)).observations

    drifting = run_ewma(obs, "TOOL-01", "CH-A", "etch_depth", phase_i_n_lots=10)
    healthy = run_ewma(obs, "TOOL-01", "CH-B", "etch_depth", phase_i_n_lots=10)

    assert drifting.any_out_of_control is True
    assert healthy.any_out_of_control is False


def test_run_imr_alarm_fires_before_end_of_run():
    """A basic detection-delay sanity check (full T3 scoring comes later):
    the alarm should fire well before the drift has had 20 hours to
    accumulate, not just barely at the last lot.
    """
    onset = datetime(2026, 1, 1)
    obs = simulate(_chamber_drift_config(onset)).observations
    result = run_imr(obs, "TOOL-01", "CH-A", "etch_depth", phase_i_n_lots=10)
    assert result.first_alarm_index < len(result.points) - 1


def _variance_comparison_config() -> SimulationConfig:
    """Case-2-shaped scenario (Overview section 4.4): two chambers with
    similar means but different variance, via an always-on
    variance_inflation fault on one chamber rather than a config-schema
    change - see docs/case-studies.md's noted implementation decision.
    """
    start = datetime(2026, 1, 1)
    return SimulationConfig(
        seed=7,
        start_time=start,
        recipe=_recipe(),
        tool_chambers=[
            ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-CALM", depth_offset_sigma_nm=0.0),
            ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-NOISY", depth_offset_sigma_nm=0.0),
        ],
        hierarchy=HierarchyConfig(
            lot_size_wafers=10, sites_per_wafer=5, n_lots=40, lot_interval_minutes=30
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=1.0, wafer_sigma_nm=1.0, site_noise_sigma_nm=1.0
        ),
        faults=[
            FaultEvent(
                event_id="STEADY-VARIANCE",
                fault_type="variance_inflation",
                onset=start,
                tool_id="TOOL-01",
                chamber_id="CH-NOISY",
                metric="etch_depth",
                magnitude=6.0,
            )
        ],
    )


def test_run_capability_shows_lower_cpk_for_higher_variance_chamber():
    obs = simulate(_variance_comparison_config()).observations
    calm_series = extract_lot_series(obs, "TOOL-01", "CH-CALM", "etch_depth")
    center = calm_series["value"].mean()
    # spec window wide enough that both chambers are broadly "fine on average",
    # narrow enough that the noisier chamber's larger sigma visibly hurts Cpk.
    usl, lsl = center + 15, center - 15

    calm = run_capability(
        obs, "TOOL-01", "CH-CALM", "etch_depth", phase_i_n_lots=35, usl=usl, lsl=lsl
    )
    noisy = run_capability(
        obs, "TOOL-01", "CH-NOISY", "etch_depth", phase_i_n_lots=35, usl=usl, lsl=lsl
    )

    assert noisy.sigma > calm.sigma
    assert noisy.cpk_or_ppk < calm.cpk_or_ppk
    # the Overview's own framing: "平均值正常" 不等于 "过程健康" - means alone
    # would not obviously distinguish these two chambers.
    assert abs(calm.mean - noisy.mean) < 0.25 * abs(calm.sigma - noisy.sigma)
