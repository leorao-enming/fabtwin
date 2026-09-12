"""Unit tests for src/fabtwin/detection.py, using hand-built SPCRunResult
objects (not simulate() output) so the scoring logic itself is isolated
from the simulator - the end-to-end integration test lives in
tests/unit/test_detection_integration.py.
"""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from fabtwin.analysis import SPCRunResult
from fabtwin.config import FaultEvent
from fabtwin.detection import score_detection
from fabtwin.spc.phase import ChartPoint, FrozenLimits

BASE = datetime(2026, 1, 1)


def _result(timestamps: list[datetime], flags: list[bool]) -> SPCRunResult:
    phase_ii = pd.DataFrame(
        {
            "lot_id": [f"L{i:04d}" for i in range(len(timestamps))],
            "timestamp": timestamps,
            "value": [0.0] * len(timestamps),
        }
    )
    points = [ChartPoint(index=i, value=0.0, out_of_control=flag) for i, flag in enumerate(flags)]
    limits = FrozenLimits(center_line=0.0, ucl=1.0, lcl=-1.0, method="TEST", params={})
    return SPCRunResult(
        method="TEST", limits=limits, phase_i=pd.DataFrame(), phase_ii=phase_ii, points=points
    )


def _fault(onset: datetime) -> FaultEvent:
    return FaultEvent(
        event_id="E1",
        fault_type="linear_drift",
        onset=onset,
        tool_id="TOOL-01",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=1.0,
    )


def test_no_alarms_is_a_missed_event():
    timestamps = [BASE + timedelta(hours=i) for i in range(5)]
    result = _result(timestamps, [False] * 5)
    score = score_detection(result, _fault(onset=BASE + timedelta(hours=2)))
    assert score.event_detected is False
    assert score.missed_event is True
    assert score.first_alarm_timestamp is None
    assert score.detection_delay is None
    assert score.pre_fault_false_alarms == 0


def test_alarm_after_onset_is_detected_with_correct_delay():
    timestamps = [BASE + timedelta(hours=i) for i in range(5)]
    flags = [False, False, False, True, False]  # alarm at hour 3
    result = _result(timestamps, flags)
    score = score_detection(result, _fault(onset=BASE + timedelta(hours=2)))
    assert score.event_detected is True
    assert score.missed_event is False
    assert score.first_alarm_timestamp == BASE + timedelta(hours=3)
    assert score.detection_delay == timedelta(hours=1)


def test_alarm_exactly_at_onset_counts_as_detected():
    timestamps = [BASE + timedelta(hours=i) for i in range(3)]
    flags = [False, True, False]
    onset = BASE + timedelta(hours=1)
    result = _result(timestamps, flags)
    score = score_detection(result, _fault(onset=onset))
    assert score.event_detected is True
    assert score.detection_delay == timedelta(0)


def test_alarm_before_onset_is_a_pre_fault_false_alarm_not_a_detection():
    timestamps = [BASE + timedelta(hours=i) for i in range(5)]
    flags = [False, True, False, False, False]  # alarm at hour 1, onset at hour 3
    result = _result(timestamps, flags)
    score = score_detection(result, _fault(onset=BASE + timedelta(hours=3)))
    assert score.pre_fault_false_alarms == 1
    assert score.event_detected is False  # no alarm at or after onset
    assert score.missed_event is True


def test_multiple_pre_fault_false_alarms_counted_and_true_detection_still_scored():
    timestamps = [BASE + timedelta(hours=i) for i in range(6)]
    flags = [True, False, True, False, True, False]  # hours 0, 2 pre-onset; hour 4 post-onset
    result = _result(timestamps, flags)
    score = score_detection(result, _fault(onset=BASE + timedelta(hours=3)))
    assert score.pre_fault_false_alarms == 2
    assert score.event_detected is True
    assert score.first_alarm_timestamp == BASE + timedelta(hours=4)
    assert score.detection_delay == timedelta(hours=1)


def test_first_alarm_after_onset_is_the_one_reported_not_a_later_one():
    timestamps = [BASE + timedelta(hours=i) for i in range(5)]
    flags = [False, False, True, False, True]  # onset at hour 1: alarms at hour 2 and hour 4
    result = _result(timestamps, flags)
    score = score_detection(result, _fault(onset=BASE + timedelta(hours=1)))
    assert score.first_alarm_timestamp == BASE + timedelta(hours=2)
    assert score.detection_delay == timedelta(hours=1)


def test_event_id_and_method_are_carried_through():
    timestamps = [BASE]
    result = _result(timestamps, [False])
    fault = _fault(onset=BASE)
    score = score_detection(result, fault)
    assert score.event_id == "E1"
    assert score.method == "TEST"


def test_mismatched_lengths_raise():
    result = _result([BASE, BASE + timedelta(hours=1)], [False, False])
    result.points.pop()  # deliberately desync phase_ii and points
    with pytest.raises(ValueError, match="must correspond 1:1"):
        score_detection(result, _fault(onset=BASE))
