"""Fault detection scoring - Overview section 4.3 / data-dictionary.md
section 7.

Compares SPC detection output (analysis.py's SPCRunResult, Phase II only)
against the simulator's hidden-truth fault ground truth to compute the five
formal fields data-dictionary.md section 7 requires: event_detected,
first_alarm_timestamp, detection_delay, pre_fault_false_alarms,
missed_event.

This is deliberately a separate module from analysis.py: analysis.py and
everything in spc/ must never see fault ground truth while computing a
chart's limits or out-of-control points - matching data-dictionary.md
section 5's "fault ground truth 单独保存，避免分析代码偷看标签." detection.py
is the one place hidden truth is allowed to meet detection output, and only
for *scoring after the fact* - it never feeds back into how a chart's
limits or points are computed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from fabtwin.analysis import SPCRunResult
from fabtwin.config import FaultEvent


@dataclass(frozen=True)
class DetectionScore:
    event_id: str
    method: str
    event_detected: bool
    first_alarm_timestamp: datetime | None
    detection_delay: timedelta | None
    pre_fault_false_alarms: int
    missed_event: bool


def score_detection(result: SPCRunResult, fault: FaultEvent) -> DetectionScore:
    """Score one SPCRunResult (a specific chamber/metric/method's Phase II
    run) against one fault event.

    `pre_fault_false_alarms` counts Phase II alarms strictly before the
    fault's onset - Overview 4.3's "alarms raised in the Phase II window
    before onset." `event_detected`/`missed_event` are complements of each
    other by construction: an event is detected iff at least one alarm
    fires at or after onset.

    Only meaningful when result.phase_ii's time window actually overlaps
    the fault's active period for the chamber/metric the result was
    computed on - scoring a chamber against a fault that was never
    scheduled for it will correctly (but not usefully) report
    missed_event=True with zero false alarms; callers are responsible for
    passing a matching (result, fault) pair.
    """
    timestamps = pd.to_datetime(result.phase_ii["timestamp"]).tolist()
    if len(timestamps) != len(result.points):
        raise ValueError(
            f"phase_ii has {len(timestamps)} rows but points has {len(result.points)} - "
            "these must correspond 1:1 (see analysis.py's SPCRunResult contract)"
        )

    onset = fault.onset
    pre_fault_false_alarms = sum(
        1
        for ts, point in zip(timestamps, result.points, strict=True)
        if ts < onset and point.out_of_control
    )

    first_alarm_timestamp: datetime | None = None
    for ts, point in zip(timestamps, result.points, strict=True):
        if ts >= onset and point.out_of_control:
            first_alarm_timestamp = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            break

    if first_alarm_timestamp is None:
        return DetectionScore(
            event_id=fault.event_id,
            method=result.method,
            event_detected=False,
            first_alarm_timestamp=None,
            detection_delay=None,
            pre_fault_false_alarms=pre_fault_false_alarms,
            missed_event=True,
        )

    return DetectionScore(
        event_id=fault.event_id,
        method=result.method,
        event_detected=True,
        first_alarm_timestamp=first_alarm_timestamp,
        detection_delay=first_alarm_timestamp - onset,
        pre_fault_false_alarms=pre_fault_false_alarms,
        missed_event=False,
    )
