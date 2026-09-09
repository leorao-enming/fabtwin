"""Configuration models for the FabTwin simulator.

Mirrors docs/data-dictionary.md sections 1-6 exactly: these are the types
that make a simulation run reproducible from a frozen config. Nothing in
this module runs a simulation - see simulator.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Metric = Literal["etch_depth", "etch_rate", "cd_bias", "wiwnu", "defect_count"]

SITE_LEVEL_METRICS: tuple[Metric, ...] = ("etch_depth", "etch_rate", "cd_bias")
WAFER_LEVEL_METRICS: tuple[Metric, ...] = ("wiwnu", "defect_count")

FaultType = Literal[
    "step_mean_shift",
    "linear_drift",
    "variance_inflation",
    "sensor_bias",
    "monotonic_equipment_degradation",
]

METRIC_UNITS: dict[Metric, str] = {
    "etch_depth": "nm",
    "etch_rate": "nm/min",
    "cd_bias": "nm",
    "wiwnu": "%",
    "defect_count": "count",
}


class RecipeConfig(BaseModel):
    """Section 2 of the data dictionary — the fixed-effect input."""

    recipe_id: str
    rf_power_w: float = Field(gt=0)
    pressure_mtorr: float = Field(gt=0)
    gas_flow_sccm: float = Field(gt=0)
    etch_time_s: float = Field(gt=0)


class ToolChamberConfig(BaseModel):
    """One (tool_id, chamber_id) pair and its random-effect scale.

    depth_offset_sigma_nm / cd_bias_offset_sigma_nm parameterize the
    tool/chamber random effect (data dictionary section 5, item 2): a single
    offset is drawn once per chamber per simulation run from
    Normal(0, sigma) and held fixed for the whole run.
    """

    tool_id: str
    chamber_id: str
    depth_offset_sigma_nm: float = Field(default=15.0, ge=0)
    cd_bias_offset_sigma_nm: float = Field(default=3.0, ge=0)


class RecoveryAction(BaseModel):
    timestamp: datetime
    action_type: str
    description: str | None = None


class FaultEvent(BaseModel):
    """Mirrors docs/schemas/fault-event.schema.json exactly."""

    event_id: str
    fault_type: FaultType
    onset: datetime
    duration_s: float | None = None
    tool_id: str
    chamber_id: str | None = None
    metric: Metric
    magnitude: float
    recovery_action: RecoveryAction | None = None

    def active_at(self, t: datetime) -> bool:
        if t < self.onset:
            return False
        if self.recovery_action is not None and t >= self.recovery_action.timestamp:
            return False
        if self.duration_s is not None:
            elapsed = (t - self.onset).total_seconds()
            return elapsed <= self.duration_s
        return True

    def elapsed_hours(self, t: datetime) -> float:
        return max(0.0, (t - self.onset).total_seconds() / 3600.0)


class RandomEffectConfig(BaseModel):
    """Section 5 items 3 and 5 — lot/wafer effects and measurement noise."""

    lot_sigma_nm: float = Field(default=5.0, ge=0)
    wafer_sigma_nm: float = Field(default=3.0, ge=0)
    site_noise_sigma_nm: float = Field(default=2.0, ge=0)
    cd_bias_lot_sigma_nm: float = Field(default=1.0, ge=0)
    cd_bias_wafer_sigma_nm: float = Field(default=0.5, ge=0)
    cd_bias_noise_sigma_nm: float = Field(default=0.5, ge=0)
    defect_count_base_rate: float = Field(default=2.0, ge=0)


class HierarchyConfig(BaseModel):
    """Section 1 cardinalities — v1 defaults, overridable per run."""

    lot_size_wafers: int = Field(default=25, ge=1)
    sites_per_wafer: int = Field(default=5, ge=1)
    n_lots: int = Field(default=10, ge=1)
    lot_interval_minutes: float = Field(default=30.0, gt=0)


class SimulationConfig(BaseModel):
    """The full frozen input to one simulator run — see simulator.simulate()."""

    seed: int
    start_time: datetime
    recipe: RecipeConfig
    tool_chambers: list[ToolChamberConfig]
    hierarchy: HierarchyConfig = Field(default_factory=HierarchyConfig)
    random_effects: RandomEffectConfig = Field(default_factory=RandomEffectConfig)
    faults: list[FaultEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def _faults_reference_known_tool_chambers(self) -> SimulationConfig:
        known = {(tc.tool_id, tc.chamber_id) for tc in self.tool_chambers}
        known_tools = {tc.tool_id for tc in self.tool_chambers}
        for fault in self.faults:
            if fault.chamber_id is None:
                if fault.tool_id not in known_tools:
                    raise ValueError(
                        f"fault {fault.event_id} references unknown tool_id {fault.tool_id!r}"
                    )
            elif (fault.tool_id, fault.chamber_id) not in known:
                raise ValueError(
                    f"fault {fault.event_id} references unknown tool/chamber "
                    f"{(fault.tool_id, fault.chamber_id)!r}"
                )
        return self
