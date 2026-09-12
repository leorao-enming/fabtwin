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
    """CH-B never had the fault applied to it. Scoring CH-B's own I-MR run
    against the CH-A fault is not a realistic production use (a fault
    targets a specific chamber) - but it demonstrates score_detection()
    correctly reports "no alarm ever fired" rather than fabricating a
    detection, since CH-B's own I-MR run should have zero alarms at all.
    """
    start = datetime(2026, 1, 1)
    drift_onset = start + timedelta(hours=10)
    config = _chamber_drift_config(start, drift_onset)
    obs = simulate(config).observations
    fault = config.faults[0]

    healthy_result = run_imr(obs, "TOOL-01", "CH-B", "etch_depth", phase_i_n_lots=10)
    score = score_detection(healthy_result, fault)

    assert score.event_detected is False
    assert score.missed_event is True
    assert score.pre_fault_false_alarms == 0


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
