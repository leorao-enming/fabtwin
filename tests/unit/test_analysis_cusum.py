"""run_cusum: CUSUM wired into the simulator -> SPC -> detection path, so
case 1 (I-MR vs EWMA vs CUSUM detection delay) has all three methods
available through the same SPCRunResult / score_detection interface.
"""

from datetime import datetime, timedelta

import pytest

from fabtwin.analysis import run_cusum, run_imr
from fabtwin.config import (
    FaultEvent,
    HierarchyConfig,
    RandomEffectConfig,
    RecipeConfig,
    SimulationConfig,
    ToolChamberConfig,
)
from fabtwin.detection import score_detection
from fabtwin.simulator import simulate

START = datetime(2026, 1, 1)


def _config(fault: FaultEvent | None) -> SimulationConfig:
    return SimulationConfig(
        seed=42,
        start_time=START,
        recipe=RecipeConfig(
            recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
        ),
        tool_chambers=[
            ToolChamberConfig(tool_id="T1", chamber_id="CH-A"),
            ToolChamberConfig(tool_id="T1", chamber_id="CH-B"),
        ],
        hierarchy=HierarchyConfig(
            lot_size_wafers=10, sites_per_wafer=5, n_lots=40, lot_interval_minutes=60
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=0.5, wafer_sigma_nm=0.5, site_noise_sigma_nm=0.5
        ),
        faults=[fault] if fault else [],
    )


def _drift() -> FaultEvent:
    return FaultEvent(
        event_id="DRIFT-1",
        fault_type="linear_drift",
        onset=START + timedelta(hours=10),
        tool_id="T1",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=1.0,
    )


def test_cusum_detects_drift_and_leaves_sibling_quiet():
    config = _config(_drift())
    obs = simulate(config).observations

    drifting = run_cusum(obs, "T1", "CH-A", "etch_depth", phase_i_n_lots=10)
    sibling = run_cusum(obs, "T1", "CH-B", "etch_depth", phase_i_n_lots=10)

    assert drifting.method == "CUSUM"
    assert drifting.any_out_of_control
    assert not sibling.any_out_of_control

    score = score_detection(drifting, config.faults[0])
    assert score.event_detected and score.pre_fault_false_alarms == 0
    assert score.detection_delay is not None and score.detection_delay >= timedelta(0)


def test_cusum_parameters_are_frozen_in_absolute_units_and_recorded():
    obs = simulate(_config(None)).observations
    result = run_cusum(obs, "T1", "CH-A", "etch_depth", 10, k_sigma=0.5, h_sigma=4.0)
    p = result.limits.params
    assert p["h"] / p["k"] == pytest.approx(8.0)
    assert result.limits.method == "CUSUM"
    assert len(result.points) == len(result.phase_ii)


def test_cusum_signed_value_follows_dominant_side():
    drop = FaultEvent(
        event_id="STEP-DOWN",
        fault_type="step_mean_shift",
        onset=START + timedelta(hours=10),
        tool_id="T1",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=-10.0,
    )
    obs = simulate(_config(drop)).observations
    result = run_cusum(obs, "T1", "CH-A", "etch_depth", 10)
    assert result.points[-1].value < 0 and result.points[-1].out_of_control


def test_cusum_is_more_sensitive_than_imr_to_a_small_sustained_shift():
    small = FaultEvent(
        event_id="STEP-SMALL",
        fault_type="step_mean_shift",
        onset=START + timedelta(hours=10),
        tool_id="T1",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=0.8,
    )
    config = _config(small)
    obs = simulate(config).observations
    imr = score_detection(run_imr(obs, "T1", "CH-A", "etch_depth", 10), small)
    cusum = score_detection(run_cusum(obs, "T1", "CH-A", "etch_depth", 10), small)
    assert cusum.event_detected
    if imr.event_detected:
        assert imr.detection_delay is not None and cusum.detection_delay is not None
        assert cusum.detection_delay <= imr.detection_delay
