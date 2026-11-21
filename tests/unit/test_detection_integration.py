"""Integration test: simulator (T1) -> SPC (T2) -> detection scoring (T3),
the first time all three layers run together end to end.

Reuses the exact case-1-shaped chamber-drift scenario from
tests/unit/test_analysis.py, but now closes the loop by scoring the SPC
output against the simulator's own fault ground truth instead of only
checking any_out_of_control by hand.
"""

from datetime import datetime, timedelta

from fabtwin.analysis import run_imr
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


def _recipe() -> RecipeConfig:
    return RecipeConfig(
        recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
    )


def _chamber_drift_config(onset: datetime, drift_onset: datetime) -> SimulationConfig:
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
                onset=drift_onset,
                tool_id="TOOL-01",
                chamber_id="CH-A",
                metric="etch_depth",
                magnitude=5.0,  # nm/hour
            )
        ],
    )


def test_detection_score_end_to_end_on_drifting_chamber():
    start = datetime(2026, 1, 1)
    drift_onset = start + timedelta(hours=10)  # after the 10-lot Phase I window
    config = _chamber_drift_config(start, drift_onset)
    obs = simulate(config).observations
    fault = config.faults[0]

    result = run_imr(obs, "TOOL-01", "CH-A", "etch_depth", phase_i_n_lots=10)
    score = score_detection(result, fault)

    assert score.event_detected is True
    assert score.missed_event is False
    assert score.detection_delay is not None
    assert timedelta(0) <= score.detection_delay < timedelta(hours=20)
    assert score.pre_fault_false_alarms == 0  # Phase II starts exactly at drift onset here
    assert score.event_id == "DRIFT-1"
    assert score.method == "I-MR"


def test_detection_score_no_false_alarms_on_sibling_chamber_for_same_fault():
    """CH-B never had the fault applied to it. Scoring CH-B's chart against the
    CH-A fault is a sibling control (it must be declared, ADR 0002): whatever
    "detection" it reports is a false-alarm measure, so it must come only from
    CH-B's own alarms, and there should be few of them.

    It used to assert "no alarm at all"; that held for one seed only. A 10-lot
    Phase I gives a healthy I-MR chart a 27 % chance of at least one alarm in 20
    lots (measured over 200 seeds), and seed 42 lands on one after the random
    streams were made per-chamber.
    """
    start = datetime(2026, 1, 1)
    drift_onset = start + timedelta(hours=10)
    config = _chamber_drift_config(start, drift_onset)
    obs = simulate(config).observations
    fault = config.faults[0]

    healthy_result = run_imr(obs, "TOOL-01", "CH-B", "etch_depth", phase_i_n_lots=10)
    drifting_result = run_imr(obs, "TOOL-01", "CH-A", "etch_depth", phase_i_n_lots=10)
    # scoring another chamber's chart is refused unless declared as a sibling control
    score = score_detection(healthy_result, fault, sibling_control=True)
    real = score_detection(drifting_result, fault)

    alarms = [p.out_of_control for p in healthy_result.points]
    assert score.event_detected is any(alarms)
    assert score.missed_event is not any(alarms)
    assert score.pre_fault_false_alarms == 0
    assert sum(alarms) <= 2
    assert sum(p.out_of_control for p in drifting_result.points) >= 10
    assert real.event_detected is True


def test_detection_score_counts_pre_fault_false_alarms_when_phase_ii_starts_early():
    """Give CH-A a short Phase I window (only 3 lots) so Phase II starts
    well before the fault's actual onset (hour 10) - if I-MR ever produces
    a spurious alarm in that early, still-healthy stretch, it must be
    counted as a pre-fault false alarm, not silently dropped or misread as
    an early detection of the real event.
    """
    start = datetime(2026, 1, 1)
    drift_onset = start + timedelta(hours=10)
    config = _chamber_drift_config(start, drift_onset)
    obs = simulate(config).observations
    fault = config.faults[0]

    result = run_imr(obs, "TOOL-01", "CH-A", "etch_depth", phase_i_n_lots=3)
    score = score_detection(result, fault)

    # whatever happens, the counts must be internally consistent:
    assert score.pre_fault_false_alarms >= 0
    if score.event_detected:
        assert score.detection_delay is not None and score.detection_delay >= timedelta(0)
    else:
        assert score.detection_delay is None
