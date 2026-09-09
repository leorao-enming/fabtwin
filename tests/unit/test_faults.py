"""Unit tests for src/fabtwin/faults.py."""

from datetime import datetime, timedelta

from fabtwin.config import FaultEvent, RecoveryAction
from fabtwin.faults import (
    noise_sigma_multiplier,
    process_value_contribution,
    sensor_bias_offset,
    total_process_contribution,
)

T0 = datetime(2026, 1, 1, 0, 0)


def test_step_mean_shift_is_constant_once_active():
    fault = FaultEvent(
        event_id="E1",
        fault_type="step_mean_shift",
        onset=T0,
        tool_id="TOOL-01",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=10.0,
    )
    before = process_value_contribution(
        fault, "TOOL-01", "CH-A", "etch_depth", T0 - timedelta(seconds=1)
    )
    at_onset = process_value_contribution(fault, "TOOL-01", "CH-A", "etch_depth", T0)
    later = process_value_contribution(
        fault, "TOOL-01", "CH-A", "etch_depth", T0 + timedelta(hours=5)
    )
    assert before == 0.0
    assert at_onset == 10.0
    assert later == 10.0


def test_linear_drift_grows_with_elapsed_time():
    fault = FaultEvent(
        event_id="E1",
        fault_type="linear_drift",
        onset=T0,
        tool_id="TOOL-01",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=2.0,  # nm/hour
    )
    v1 = process_value_contribution(fault, "TOOL-01", "CH-A", "etch_depth", T0 + timedelta(hours=1))
    v3 = process_value_contribution(fault, "TOOL-01", "CH-A", "etch_depth", T0 + timedelta(hours=3))
    assert v1 == 2.0
    assert v3 == 6.0
    assert v3 > v1


def test_fault_does_not_leak_to_other_chamber_or_metric():
    fault = FaultEvent(
        event_id="E1",
        fault_type="step_mean_shift",
        onset=T0,
        tool_id="TOOL-01",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=10.0,
    )
    other_chamber = process_value_contribution(fault, "TOOL-01", "CH-B", "etch_depth", T0)
    other_metric = process_value_contribution(fault, "TOOL-01", "CH-A", "cd_bias", T0)
    other_tool = process_value_contribution(fault, "TOOL-02", "CH-A", "etch_depth", T0)
    assert other_chamber == 0.0
    assert other_metric == 0.0
    assert other_tool == 0.0


def test_whole_tool_fault_applies_to_every_chamber():
    fault = FaultEvent(
        event_id="E1",
        fault_type="step_mean_shift",
        onset=T0,
        tool_id="TOOL-01",
        chamber_id=None,  # whole tool, per schema
        metric="etch_depth",
        magnitude=5.0,
    )
    assert process_value_contribution(fault, "TOOL-01", "CH-A", "etch_depth", T0) == 5.0
    assert process_value_contribution(fault, "TOOL-01", "CH-B", "etch_depth", T0) == 5.0


def test_degradation_stops_after_recovery_action():
    fault = FaultEvent(
        event_id="E1",
        fault_type="monotonic_equipment_degradation",
        onset=T0,
        tool_id="TOOL-01",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=1.0,
        recovery_action=RecoveryAction(
            timestamp=T0 + timedelta(hours=10), action_type="maintenance"
        ),
    )
    before_recovery = process_value_contribution(
        fault, "TOOL-01", "CH-A", "etch_depth", T0 + timedelta(hours=9)
    )
    after_recovery = process_value_contribution(
        fault, "TOOL-01", "CH-A", "etch_depth", T0 + timedelta(hours=11)
    )
    assert before_recovery == 9.0
    assert after_recovery == 0.0


def test_variance_inflation_multiplies_and_compounds():
    faults = [
        FaultEvent(
            event_id="E1",
            fault_type="variance_inflation",
            onset=T0,
            tool_id="TOOL-01",
            chamber_id="CH-A",
            metric="etch_depth",
            magnitude=2.0,
        ),
        FaultEvent(
            event_id="E2",
            fault_type="variance_inflation",
            onset=T0,
            tool_id="TOOL-01",
            chamber_id="CH-A",
            metric="etch_depth",
            magnitude=1.5,
        ),
    ]
    multiplier = noise_sigma_multiplier(
        faults, "TOOL-01", "CH-A", "etch_depth", T0 + timedelta(hours=1)
    )
    assert multiplier == 3.0
    baseline = noise_sigma_multiplier(
        faults, "TOOL-01", "CH-B", "etch_depth", T0 + timedelta(hours=1)
    )
    assert baseline == 1.0


def test_sensor_bias_is_additive_offset_not_process_contribution():
    faults = [
        FaultEvent(
            event_id="E1",
            fault_type="sensor_bias",
            onset=T0,
            tool_id="TOOL-01",
            chamber_id="CH-A",
            metric="etch_depth",
            magnitude=-3.0,
        )
    ]
    offset = sensor_bias_offset(faults, "TOOL-01", "CH-A", "etch_depth", T0 + timedelta(minutes=1))
    assert offset == -3.0
    # sensor_bias must NOT show up in the process-value contribution
    assert (
        total_process_contribution(
            faults, "TOOL-01", "CH-A", "etch_depth", T0 + timedelta(minutes=1)
        )
        == 0.0
    )


def test_total_process_contribution_sums_multiple_faults():
    faults = [
        FaultEvent(
            event_id="E1",
            fault_type="step_mean_shift",
            onset=T0,
            tool_id="TOOL-01",
            chamber_id="CH-A",
            metric="etch_depth",
            magnitude=10.0,
        ),
        FaultEvent(
            event_id="E2",
            fault_type="linear_drift",
            onset=T0,
            tool_id="TOOL-01",
            chamber_id="CH-A",
            metric="etch_depth",
            magnitude=1.0,
        ),
    ]
    total = total_process_contribution(
        faults, "TOOL-01", "CH-A", "etch_depth", T0 + timedelta(hours=2)
    )
    assert total == 12.0
