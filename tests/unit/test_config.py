"""Unit tests for src/fabtwin/config.py — schema/validation only, no simulation."""

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from fabtwin.config import (
    FaultEvent,
    HierarchyConfig,
    RecipeConfig,
    SimulationConfig,
    ToolChamberConfig,
)


def _recipe() -> RecipeConfig:
    return RecipeConfig(
        recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
    )


def _tool_chambers() -> list[ToolChamberConfig]:
    return [
        ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-A"),
        ToolChamberConfig(tool_id="TOOL-01", chamber_id="CH-B"),
    ]


def test_recipe_rejects_nonpositive_setpoints():
    with pytest.raises(ValidationError):
        RecipeConfig(
            recipe_id="R1", rf_power_w=0, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
        )


def test_simulation_config_accepts_fault_on_known_chamber():
    cfg = SimulationConfig(
        seed=1,
        start_time=datetime(2026, 1, 1),
        recipe=_recipe(),
        tool_chambers=_tool_chambers(),
        faults=[
            FaultEvent(
                event_id="E1",
                fault_type="linear_drift",
                onset=datetime(2026, 1, 1, 1),
                tool_id="TOOL-01",
                chamber_id="CH-A",
                metric="etch_depth",
                magnitude=2.0,
            )
        ],
    )
    assert cfg.faults[0].tool_id == "TOOL-01"


def test_simulation_config_rejects_fault_on_unknown_chamber():
    with pytest.raises(ValidationError):
        SimulationConfig(
            seed=1,
            start_time=datetime(2026, 1, 1),
            recipe=_recipe(),
            tool_chambers=_tool_chambers(),
            faults=[
                FaultEvent(
                    event_id="E1",
                    fault_type="linear_drift",
                    onset=datetime(2026, 1, 1, 1),
                    tool_id="TOOL-01",
                    chamber_id="CH-DOES-NOT-EXIST",
                    metric="etch_depth",
                    magnitude=2.0,
                )
            ],
        )


def test_simulation_config_rejects_fault_on_unknown_tool():
    with pytest.raises(ValidationError):
        SimulationConfig(
            seed=1,
            start_time=datetime(2026, 1, 1),
            recipe=_recipe(),
            tool_chambers=_tool_chambers(),
            faults=[
                FaultEvent(
                    event_id="E1",
                    fault_type="monotonic_equipment_degradation",
                    onset=datetime(2026, 1, 1, 1),
                    tool_id="TOOL-99",
                    metric="etch_depth",
                    magnitude=1.0,
                )
            ],
        )


def test_fault_active_at_respects_onset_duration_and_recovery():
    from fabtwin.config import RecoveryAction

    onset = datetime(2026, 1, 1, 0, 0)
    fault = FaultEvent(
        event_id="E1",
        fault_type="step_mean_shift",
        onset=onset,
        duration_s=3600,
        tool_id="TOOL-01",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=10.0,
    )
    assert fault.active_at(onset - timedelta(seconds=1)) is False
    assert fault.active_at(onset) is True
    assert fault.active_at(onset + timedelta(seconds=1800)) is True
    assert fault.active_at(onset + timedelta(seconds=3601)) is False

    recovered = FaultEvent(
        event_id="E2",
        fault_type="monotonic_equipment_degradation",
        onset=onset,
        tool_id="TOOL-01",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=1.0,
        recovery_action=RecoveryAction(
            timestamp=onset + timedelta(hours=2), action_type="maintenance"
        ),
    )
    assert recovered.active_at(onset + timedelta(hours=1)) is True
    assert recovered.active_at(onset + timedelta(hours=3)) is False


def test_hierarchy_defaults_match_data_dictionary():
    h = HierarchyConfig()
    assert h.lot_size_wafers == 25
    assert h.sites_per_wafer == 5
