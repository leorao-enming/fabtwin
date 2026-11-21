"""Regression tests for the six issues found in the 2026-11-05 T3 review.

Each test pins the behaviour the review's fix plan asks for (docs/adr/0002). They were
written before the fixes and failed against 775ce5e.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import jsonschema
import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from fabtwin.analysis import SPCRunResult, run_imr, run_pca_monitor
from fabtwin.config import (
    FaultEvent,
    HierarchyConfig,
    RandomEffectConfig,
    RecipeConfig,
    SimulationConfig,
    ToolChamberConfig,
)
from fabtwin.detection import score_detection
from fabtwin.faults import process_value_contribution
from fabtwin.simulator import simulate
from fabtwin.spc.phase import ChartPoint, FrozenLimits

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "docs/schemas/fault-event.schema.json").read_text(encoding="utf-8"))
T0 = datetime(2026, 1, 1)
RECIPE = RecipeConfig(
    recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
)


def fault(kind="step_mean_shift", metric="etch_depth", mag=10.0, onset_h=20.0, **kw) -> FaultEvent:
    return FaultEvent(
        event_id=kw.pop("event_id", "E"),
        fault_type=kind,
        onset=T0 + timedelta(hours=onset_h),
        tool_id=kw.pop("tool_id", "T1"),
        chamber_id=kw.pop("chamber_id", "A"),
        metric=metric,
        magnitude=mag,
        **kw,
    )


def run(faults=(), interval=60.0, random_effects=None, n_lots=40, seed=42) -> pd.DataFrame:
    return simulate(
        SimulationConfig(
            seed=seed,
            start_time=T0,
            recipe=RECIPE,
            faults=list(faults),
            tool_chambers=[ToolChamberConfig(tool_id="T1", chamber_id=c) for c in "AB"],
            hierarchy=HierarchyConfig(
                lot_size_wafers=5, sites_per_wafer=5, n_lots=n_lots, lot_interval_minutes=interval
            ),
            random_effects=random_effects or RandomEffectConfig(),
        )
    ).observations


def changed(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    return b[~np.isclose(a["value"].to_numpy(), b["value"].to_numpy(), atol=1e-9)]


# ---------------------------------------------------------------- issue 1


@pytest.mark.parametrize("metric", ["etch_rate", "wiwnu"])
def test_1_fault_on_derived_metric_is_rejected(metric):
    with pytest.raises(ValidationError):
        fault(metric=metric)


def test_1_schema_metric_enum_matches_model():
    enum = SCHEMA["properties"]["affected_scope"]["properties"]["metric"]["enum"]
    assert sorted(enum) == ["cd_bias", "defect_count", "etch_depth"]


# ---------------------------------------------------------------- issue 2


def _per_lot_shift(interval: float, kind: str) -> pd.Series:
    re = RandomEffectConfig()
    a = run(interval=interval, random_effects=re)
    b = run([fault(kind, mag=1.0, onset_h=0.0)], interval=interval, random_effects=re)
    pick = (a.chamber_id == "A") & (a.metric == "etch_depth")
    return (b.value[pick] - a.value[pick]).groupby(a.lot_id[pick]).mean()


def test_2_degradation_is_per_lot_processed_not_per_hour():
    for interval in (30.0, 120.0):
        shift = _per_lot_shift(interval, "monotonic_equipment_degradation")
        # first affected lot has zero offset; each further lot adds `magnitude`
        assert shift.iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert np.diff(shift.to_numpy()) == pytest.approx(np.ones(len(shift) - 1))


def test_2_degradation_differs_from_linear_drift():
    # at 60 min spacing one lot = one hour and the two coincide; 30 min separates them
    assert not changed(
        run([fault("linear_drift", mag=2.0, onset_h=5.0)], interval=30.0),
        run([fault("monotonic_equipment_degradation", mag=2.0, onset_h=5.0)], interval=30.0),
    ).empty


def test_2_degradation_without_lot_count_raises():
    f = fault("monotonic_equipment_degradation", onset_h=0.0)
    with pytest.raises(ValueError, match="lot"):
        process_value_contribution(f, "T1", "A", "etch_depth", T0 + timedelta(hours=1))


def test_2_degradation_stops_at_recovery():
    f = fault(
        "monotonic_equipment_degradation",
        mag=1.0,
        onset_h=0.0,
        recovery_action={"timestamp": T0 + timedelta(hours=10), "action_type": "PM"},
    )
    a, b = run(), run([f])
    pick = (a.chamber_id == "A") & (a.metric == "etch_depth")
    shift = (b.value[pick] - a.value[pick]).groupby(a.timestamp[pick]).mean()
    after = shift[pd.to_datetime(shift.index) >= T0 + timedelta(hours=10)]
    assert (after.abs() < 1e-9).all()


# ---------------------------------------------------------------- issue 3


def _result(
    phase_i_ts, phase_ii_ts, flags, chamber="A", metrics=("etch_depth",), tool="T1"
) -> SPCRunResult:
    def frame(ts):
        return pd.DataFrame({"lot_id": [f"L{i}" for i in range(len(ts))], "timestamp": ts})

    return SPCRunResult(
        method="TEST",
        limits=FrozenLimits(center_line=0.0, ucl=1.0, lcl=-1.0, method="TEST", params={}),
        phase_i=frame(phase_i_ts),
        phase_ii=frame(phase_ii_ts),
        points=[ChartPoint(index=i, value=0.0, out_of_control=f) for i, f in enumerate(flags)],
        tool_id=tool,
        chamber_id=chamber,
        metrics=tuple(metrics),
    )


HOURS = [T0 + timedelta(hours=h) for h in range(30)]


def test_3_alarm_after_fault_ended_is_not_a_detection():
    f = fault(onset_h=12.0, duration_s=3 * 3600)  # active hours 12..15
    flags = [False] * 20
    flags[20 - 10 + 8] = True  # alarm at hour 18, after the fault ended
    s = score_detection(_result(HOURS[:10], HOURS[10:30], flags), f)
    assert s.event_detected is False
    assert s.missed_event is True
    assert s.post_fault_alarms == 1


def test_3_alarm_while_active_is_a_detection():
    f = fault(onset_h=12.0, duration_s=3 * 3600)
    flags = [False] * 20
    flags[4] = True  # hour 14
    s = score_detection(_result(HOURS[:10], HOURS[10:30], flags), f)
    assert s.event_detected is True
    assert s.detection_delay == timedelta(hours=2)
    assert s.post_fault_alarms == 0


def test_3_fault_active_in_phase_i_raises():
    f = fault(onset_h=5.0)
    with pytest.raises(ValueError, match="Phase I"):
        score_detection(_result(HOURS[:10], HOURS[10:30], [False] * 20), f)


def test_3_fault_never_active_in_phase_ii_raises():
    f = fault(onset_h=40.0)
    with pytest.raises(ValueError, match="Phase II"):
        score_detection(_result(HOURS[:10], HOURS[10:30], [False] * 20), f)


def test_3_scope_mismatch_raises_and_sibling_control_allows_it():
    f = fault(onset_h=12.0, chamber_id="B")
    r = _result(HOURS[:10], HOURS[10:30], [False] * 20, chamber="A")
    with pytest.raises(ValueError, match="scope"):
        score_detection(r, f)
    assert score_detection(r, f, sibling_control=True).missed_event is True


def test_3_metric_mismatch_raises_but_derived_metrics_are_allowed():
    r_cd = _result(HOURS[:10], HOURS[10:30], [False] * 20, metrics=("cd_bias",))
    with pytest.raises(ValueError, match="scope"):
        score_detection(r_cd, fault(onset_h=12.0, metric="etch_depth"))
    for derived in ("etch_rate", "wiwnu"):
        r = _result(HOURS[:10], HOURS[10:30], [False] * 20, metrics=(derived,))
        score_detection(r, fault(onset_h=12.0, metric="etch_depth"))


def test_3_run_results_carry_their_scope():
    r = run_imr(run(), "T1", "A", "etch_rate", 10)
    assert (r.tool_id, r.chamber_id, r.metrics) == ("T1", "A", ("etch_rate",))


# ---------------------------------------------------------------- issue 4


def test_4_model_dump_matches_schema_and_round_trips():
    f = fault(
        duration_s=3600.0,
        recovery_action={"timestamp": T0 + timedelta(hours=30), "action_type": "PM"},
    )
    doc = f.model_dump(mode="json")
    jsonschema.validate(doc, SCHEMA)
    assert "description" not in doc["recovery_action"]
    assert FaultEvent.model_validate(doc) == f
    assert FaultEvent.model_validate_json(f.model_dump_json()) == f


def test_4_schema_document_loads_and_flat_form_still_accepted():
    doc = {
        "event_id": "E9",
        "fault_type": "sensor_bias",
        "onset": "2026-01-01T05:00:00",
        "duration_s": None,
        "affected_scope": {"tool_id": "T1", "chamber_id": None, "metric": "cd_bias"},
        "magnitude": 1.5,
        "recovery_action": None,
    }
    jsonschema.validate(doc, SCHEMA)
    f = FaultEvent.model_validate(doc)
    assert (f.tool_id, f.chamber_id, f.metric) == ("T1", None, "cd_bias")
    assert fault(metric="cd_bias").metric == "cd_bias"  # flat keyword form


def test_4_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        FaultEvent.model_validate({**fault().model_dump(), "severity": "high"})


# ---------------------------------------------------------------- issue 5


def test_5_defect_count_fault_changes_only_its_own_rows():
    f = fault("linear_drift", "defect_count", 2.0, duration_s=36000.0)
    d = changed(run(), run([f]))
    assert not d.empty
    assert set(d.chamber_id) == {"A"}
    assert set(d.metric) == {"defect_count"}
    assert (pd.to_datetime(d.timestamp) >= f.onset).all()


def test_5_fault_in_one_chamber_leaves_the_other_chamber_identical():
    base, faulted = run(), run([fault("variance_inflation", mag=3.0)])
    b = base.chamber_id == "B"
    assert np.array_equal(base.value[b].to_numpy(), faulted.value[b].to_numpy())


# ---------------------------------------------------------------- issue 6


def test_6_variance_inflation_scales_process_sigma_not_site_noise():
    # only site noise: inflation must change nothing
    noise_only = RandomEffectConfig(lot_sigma_nm=0.0, wafer_sigma_nm=0.0, site_noise_sigma_nm=2.0)
    f = fault("variance_inflation", mag=5.0, onset_h=20.0)
    assert changed(run(random_effects=noise_only), run([f], random_effects=noise_only)).empty

    # only process-level (lot + wafer) variation: value = base + lot + wafer, and the fault run
    # draws the same standard normals scaled by 5, so value_b = base + 5 (value_a - base).
    # Solving for base must give one constant (fixed effect + chamber offset) on every row.
    process_only = RandomEffectConfig(lot_sigma_nm=2.0, wafer_sigma_nm=1.0, site_noise_sigma_nm=0.0)
    a, b = run(random_effects=process_only), run([f], random_effects=process_only)
    pick = (a.chamber_id == "A") & (a.metric == "etch_depth")
    post = pick & (pd.to_datetime(a.timestamp) >= f.onset)
    base = (b.value[post] - 5.0 * a.value[post]) / (1.0 - 5.0)
    assert np.allclose(base, base.iloc[0], atol=1e-8)
    assert not np.allclose(a.value[post], b.value[post])
    pre = pick & (pd.to_datetime(a.timestamp) < f.onset)
    assert np.array_equal(a.value[pre].to_numpy(), b.value[pre].to_numpy())


# ---------------------------------------------------------------- small fixes


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "variance_inflation", "mag": 0.0},
        {"kind": "variance_inflation", "mag": -2.0},
        {"kind": "variance_inflation", "metric": "defect_count", "mag": 0.5},
        {"duration_s": 0.0},
        {"duration_s": -5.0},
        {"mag": math.inf},
        {"mag": math.nan},
        {"recovery_action": {"timestamp": T0 + timedelta(hours=20), "action_type": "PM"}},
    ],
)
def test_invalid_fault_configs_rejected(kwargs):
    with pytest.raises(ValidationError):
        fault(**kwargs)


@pytest.mark.parametrize(
    ("statistic", "method"), [("T2", "PCA-T2"), ("SPE", "PCA-SPE"), ("either", "PCA-T2-SPE")]
)
def test_pca_statistic_selects_method_name(statistic, method):
    r = run_pca_monitor(run(), "T1", "A", ["etch_depth", "cd_bias"], 15, statistic=statistic)
    assert r.method == method
    assert r.metrics == ("etch_depth", "cd_bias")
