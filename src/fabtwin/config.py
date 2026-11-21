"""Configuration models for the FabTwin simulator.

Mirrors docs/data-dictionary.md sections 1-6 exactly: these are the types
that make a simulation run reproducible from a frozen config. Nothing in
this module runs a simulation - see simulator.py.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

Metric = Literal["etch_depth", "etch_rate", "cd_bias", "wiwnu", "defect_count"]

# Metrics a fault can target. etch_rate and wiwnu are computed from etch_depth
# (data dictionary section 3), so a fault acts on them through etch_depth; a fault declared
# on them directly used to be accepted and silently did nothing (ADR 0002).
FaultMetric = Literal["etch_depth", "cd_bias", "defect_count"]
FAULT_METRICS: tuple[FaultMetric, ...] = ("etch_depth", "cd_bias", "defect_count")
DERIVED_FROM: dict[Metric, Metric] = {"etch_rate": "etch_depth", "wiwnu": "etch_depth"}

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
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    action_type: str
    description: str | None = None

    @model_serializer(mode="wrap")
    def _omit_missing_description(self, handler: SerializerFunctionWrapHandler) -> dict:
        # the schema allows description to be absent but not null
        data = handler(self)
        if data.get("description") is None:
            data.pop("description", None)
        return data


class FaultEvent(BaseModel):
    """One fault in the hidden ground-truth schedule.

    Accepts both the schema form (docs/schemas/fault-event.schema.json, with a nested
    `affected_scope`) and the flat keyword form used in Python code; always serializes to the
    schema form, so `model_dump(mode="json")` validates against the schema and round-trips.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str
    fault_type: FaultType
    onset: datetime
    duration_s: float | None = None
    tool_id: str
    chamber_id: str | None = None
    metric: FaultMetric
    magnitude: float
    recovery_action: RecoveryAction | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_schema_form(cls, data: Any) -> Any:
        if isinstance(data, dict) and "affected_scope" in data:
            data = dict(data)
            scope = data.pop("affected_scope")
            if not isinstance(scope, dict):
                raise ValueError("affected_scope must be an object")
            clash = {"tool_id", "chamber_id", "metric"} & data.keys()
            if clash:
                raise ValueError(f"give {sorted(clash)} either flat or in affected_scope, not both")
            data.update(scope)
        return data

    @model_serializer(mode="wrap")
    def _to_schema_form(self, handler: SerializerFunctionWrapHandler) -> dict:
        data = handler(self)
        scope = {k: data.pop(k) for k in ("tool_id", "chamber_id", "metric") if k in data}
        out = {}
        for key in ("event_id", "fault_type", "onset", "duration_s"):
            if key in data:
                out[key] = data.pop(key)
        out["affected_scope"] = scope
        out.update(data)
        return out

    @model_validator(mode="after")
    def _check_values(self) -> FaultEvent:
        if not math.isfinite(self.magnitude):
            raise ValueError(f"fault {self.event_id}: magnitude must be finite")
        if self.duration_s is not None and self.duration_s <= 0:
            raise ValueError(f"fault {self.event_id}: duration_s must be positive (or null)")
        if self.recovery_action is not None and self.recovery_action.timestamp <= self.onset:
            raise ValueError(f"fault {self.event_id}: recovery_action must come after onset")
        if self.fault_type == "variance_inflation":
            if self.magnitude <= 0:
                raise ValueError(f"fault {self.event_id}: variance factor must be positive")
            if self.metric == "defect_count" and self.magnitude < 1:
                # the count model can widen a Poisson (negative binomial) but not narrow it
                raise ValueError(
                    f"fault {self.event_id}: variance factor on defect_count must be >= 1"
                )
        return self

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
