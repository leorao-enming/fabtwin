"""Fault detection scoring - Overview section 4.3 / data-dictionary.md
section 7.

Compares SPC detection output (analysis.py's SPCRunResult, Phase II only)
against the simulator's hidden-truth fault ground truth to compute the
formal fields data-dictionary.md section 7 requires: event_detected,
first_alarm_timestamp, detection_delay, pre_fault_false_alarms,
missed_event, plus post_fault_alarms (ADR 0002).

This is deliberately a separate module from analysis.py: analysis.py and
everything in spc/ must never see fault ground truth while computing a
chart's limits or out-of-control points - matching data-dictionary.md
section 5's "fault ground truth 单独保存，避免分析代码偷看标签." detection.py
is the one place hidden truth is allowed to meet detection output, and only
for *scoring after the fact* - it never feeds back into how a chart's
limits or points are computed.

Detection window (ADR 0002): an alarm counts as a detection only if it fires
while the fault is active (`FaultEvent.active_at`). Alarms after the fault has
ended or been recovered are `post_fault_alarms`, not detections. Known cost:
EWMA and CUSUM carry memory, so an alarm that fires just after a short fault
ends is not credited; revisit in an ADR if case 3 shows this is too strict.

Refused inputs (each raises ValueError instead of returning a misleading score):
- the fault is active anywhere in the Phase I window - the limits were fitted on
  faulty data (Overview 4.2 red line);
- the fault is never active in the Phase II window - nothing could be detected,
  so "missed" would be meaningless;
- the fault's scope does not match the chart's (tool, chamber, metric). An
  etch_depth fault may be scored on etch_rate / wiwnu charts, which are derived
  from etch_depth. `sibling_control=True` allows a chart of a *different chamber*
  on the same tool, for the explicit "healthy sibling stays quiet" comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from fabtwin.analysis import SPCRunResult
from fabtwin.config import DERIVED_FROM, FaultEvent


@dataclass(frozen=True)
class DetectionScore:
    event_id: str
    method: str
    event_detected: bool
    first_alarm_timestamp: datetime | None
    detection_delay: timedelta | None
    pre_fault_false_alarms: int
    missed_event: bool
    post_fault_alarms: int


def _timestamps(frame: pd.DataFrame) -> list[datetime]:
    if frame.empty or "timestamp" not in frame:
        return []
    return [ts.to_pydatetime() for ts in pd.to_datetime(frame["timestamp"])]


def _check_scope(result: SPCRunResult, fault: FaultEvent, sibling_control: bool) -> None:
    problems = []
    if fault.tool_id != result.tool_id:
        problems.append(f"tool {fault.tool_id!r} vs chart {result.tool_id!r}")
    if fault.chamber_id is not None and fault.chamber_id != result.chamber_id:
        if not sibling_control:
            problems.append(f"chamber {fault.chamber_id!r} vs chart {result.chamber_id!r}")
    elif sibling_control:
        problems.append("sibling_control=True but the chart is of the faulted chamber itself")
    chart_metrics = {DERIVED_FROM.get(m, m) for m in result.metrics}
    if fault.metric not in chart_metrics:
        problems.append(f"metric {fault.metric!r} vs chart metrics {list(result.metrics)}")
    if problems:
        raise ValueError(
            f"fault {fault.event_id} scope does not match the chart: " + "; ".join(problems)
        )


def score_detection(
    result: SPCRunResult, fault: FaultEvent, *, sibling_control: bool = False
) -> DetectionScore:
    """Score one SPCRunResult (a specific chamber/metric/method's Phase II
    run) against one fault event. See the module docstring for the detection
    window and for the inputs that are refused.

    `pre_fault_false_alarms` counts Phase II alarms strictly before onset.
    `event_detected` / `missed_event` are complements: detected iff at least
    one alarm fires while the fault is active.
    """
    timestamps = _timestamps(result.phase_ii)
    if len(timestamps) != len(result.points):
        raise ValueError(
            f"phase_ii has {len(timestamps)} rows but points has {len(result.points)} - "
            "these must correspond 1:1 (see analysis.py's SPCRunResult contract)"
        )
    _check_scope(result, fault, sibling_control)
    if any(fault.active_at(ts) for ts in _timestamps(result.phase_i)):
        raise ValueError(
            f"fault {fault.event_id} is active inside the Phase I window: the chart's limits "
            "were fitted on faulty data, so no detection score is meaningful"
        )
    if not any(fault.active_at(ts) for ts in timestamps):
        raise ValueError(
            f"fault {fault.event_id} is never active in the Phase II window, so there is "
            "nothing to detect (this is not a missed event)"
        )

    onset = fault.onset
    pre_fault_false_alarms = 0
    post_fault_alarms = 0
    first_alarm_timestamp: datetime | None = None
    for ts, point in zip(timestamps, result.points, strict=True):
        if not point.out_of_control:
            continue
        if ts < onset:
            pre_fault_false_alarms += 1
        elif fault.active_at(ts):
            if first_alarm_timestamp is None:
                first_alarm_timestamp = ts
        else:
            post_fault_alarms += 1

    detected = first_alarm_timestamp is not None
    return DetectionScore(
        event_id=fault.event_id,
        method=result.method,
        event_detected=detected,
        first_alarm_timestamp=first_alarm_timestamp,
        detection_delay=(first_alarm_timestamp - onset) if first_alarm_timestamp else None,
        pre_fault_false_alarms=pre_fault_false_alarms,
        missed_event=not detected,
        post_fault_alarms=post_fault_alarms,
    )
