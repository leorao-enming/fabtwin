"""Fault schedule application - data dictionary section 6, layer 4 of the
random-effect decomposition ("time-dependent drift/degradation").

Each function answers "what does this one active fault contribute right
now", for one (tool_id, chamber_id, metric, timestamp). The simulator sums
contributions from every fault whose scope matches. Faults never look at
each other - composability comes from simple summation, per Overview
section 4.3 ("implemented as composable schedules").

sensor_bias is handled separately (measurement-stage, not process-stage) -
see sensor_bias_offset() and the module docstring in effects.py section 5.
variance_inflation is handled separately too, via process_sigma_multiplier(),
since it scales the process-level sigma rather than adding a value.

monotonic_equipment_degradation is counted in lots processed, not in hours
(data dictionary section 6: "per wafer (or per lot) processed"; v1 counts lots,
ADR 0002). The count is state the simulator keeps per chamber and must be
passed in; it is never defaulted, because a missing count silently meaning
"zero" would hide the fault.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from fabtwin.config import FaultEvent, Metric


def matches_scope(fault: FaultEvent, tool_id: str, chamber_id: str, metric: Metric) -> bool:
    if fault.metric != metric:
        return False
    if fault.tool_id != tool_id:
        return False
    if fault.chamber_id is not None and fault.chamber_id != chamber_id:
        return False
    return True


def process_value_contribution(
    fault: FaultEvent,
    tool_id: str,
    chamber_id: str,
    metric: Metric,
    t: datetime,
    lots_processed: Mapping[str, int] | None = None,
) -> float:
    """Additive contribution to the underlying process value.

    Only step_mean_shift, linear_drift, and monotonic_equipment_degradation
    act here - per docs/data-dictionary.md section 6, sensor_bias acts at
    measurement time instead, and variance_inflation scales sigma rather
    than shifting the mean.

    `lots_processed[event_id]` is the number of lots this chamber has already
    processed while the degradation fault was active (0 for the first affected
    lot). Required for monotonic_equipment_degradation.
    """
    if not matches_scope(fault, tool_id, chamber_id, metric) or not fault.active_at(t):
        return 0.0

    if fault.fault_type == "step_mean_shift":
        return fault.magnitude

    if fault.fault_type == "linear_drift":
        # magnitude: rate of change per hour, per docs/data-dictionary.md section 6.
        return fault.magnitude * fault.elapsed_hours(t)

    if fault.fault_type == "monotonic_equipment_degradation":
        # magnitude: drift per lot processed on the affected chamber (ADR 0002).
        if lots_processed is None or fault.event_id not in lots_processed:
            raise ValueError(
                f"degradation fault {fault.event_id} needs the number of lots processed on "
                f"{tool_id}/{chamber_id} since onset; it is not defaulted to 0"
            )
        return fault.magnitude * lots_processed[fault.event_id]

    return 0.0


def process_sigma_multiplier(
    faults: list[FaultEvent], tool_id: str, chamber_id: str, metric: Metric, t: datetime
) -> float:
    """Multiplicative factor on the process-level sigma (lot and wafer layers).

    variance_inflation's magnitude is the multiplicative factor itself
    (docs/data-dictionary.md section 6: "on the process-level sigma"). Site
    measurement noise is the measurement layer (section 5 item 5) and is not
    scaled. Multiple simultaneous variance_inflation faults on the same scope
    compound multiplicatively.
    """
    multiplier = 1.0
    for fault in faults:
        if fault.fault_type != "variance_inflation":
            continue
        if matches_scope(fault, tool_id, chamber_id, metric) and fault.active_at(t):
            multiplier *= fault.magnitude
    return multiplier


def sensor_bias_offset(
    faults: list[FaultEvent], tool_id: str, chamber_id: str, metric: Metric, t: datetime
) -> float:
    """Additive offset applied at the measurement stage (not the process).

    A sensor_bias fault corrupts what gets *measured*, not the underlying
    process state - so it must be added after measurement noise, not mixed
    into the process-value contribution above (data dictionary section 6).
    """
    total = 0.0
    for fault in faults:
        if fault.fault_type != "sensor_bias":
            continue
        if matches_scope(fault, tool_id, chamber_id, metric) and fault.active_at(t):
            total += fault.magnitude
    return total


def total_process_contribution(
    faults: list[FaultEvent],
    tool_id: str,
    chamber_id: str,
    metric: Metric,
    t: datetime,
    lots_processed: Mapping[str, int] | None = None,
) -> float:
    return sum(
        process_value_contribution(fault, tool_id, chamber_id, metric, t, lots_processed)
        for fault in faults
    )
