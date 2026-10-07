"""Unit + integration tests for yields.py (Gate T3: three-level yield, DPPM).

Unit tests use a hand-built observation table whose answers are computed by
hand in the comments, so the expectations do not share code with the
implementation.
"""

from datetime import datetime, timedelta

import pandas as pd
import pytest
from pydantic import ValidationError

from fabtwin.config import (
    FaultEvent,
    HierarchyConfig,
    RandomEffectConfig,
    RecipeConfig,
    SimulationConfig,
    ToolChamberConfig,
)
from fabtwin.simulator import simulate
from fabtwin.yields import (
    DPPMConfig,
    SpecLimit,
    YieldConfig,
    compute_dppm,
    evaluate_yield,
    wilson_interval,
)

SITES = ["center", "N"]


def _obs(wafers: list[dict]) -> pd.DataFrame:
    rows = []
    for w in wafers:
        base = {
            "timestamp": "2026-01-01T00:00:00",
            "tool_id": "T1",
            "chamber_id": "CH-A",
            "lot_id": w["lot"],
            "wafer_id": w["wafer"],
            "recipe_id": "R1",
        }
        for site, depth in zip(SITES, w["depths"], strict=True):
            rows.append(
                {**base, "site_id": site, "metric": "etch_depth", "value": depth, "unit": "nm"}
            )
        rows.append({**base, "site_id": None, "metric": "wiwnu", "value": w["wiwnu"], "unit": "%"})
        rows.append(
            {
                **base,
                "site_id": None,
                "metric": "defect_count",
                "value": w["defects"],
                "unit": "count",
            }
        )
    return pd.DataFrame(rows)


# Spec: etch_depth in [90, 110], wiwnu <= 5. Required: both, sites center+N.
#  L1-W1: 100,105 / 3  -> pass     L1-W2: 100,111 / 3 -> fail (111 > 110)
#  L2-W1: 95,92 / 6    -> fail (wiwnu)   L2-W2: 90,110 / 5 -> pass (limits inclusive)
WAFERS = [
    {"lot": "L1", "wafer": "L1-W1", "depths": [100, 105], "wiwnu": 3, "defects": 1},
    {"lot": "L1", "wafer": "L1-W2", "depths": [100, 111], "wiwnu": 3, "defects": 2},
    {"lot": "L2", "wafer": "L2-W1", "depths": [95, 92], "wiwnu": 6, "defects": 3},
    {"lot": "L2", "wafer": "L2-W2", "depths": [90, 110], "wiwnu": 5, "defects": 2},
]


def _cfg(**kw) -> YieldConfig:
    base = {
        "spec_limits": {
            "etch_depth": SpecLimit(lsl=90, usl=110),
            "wiwnu": SpecLimit(usl=5),
        },
        "required_metrics": ["etch_depth", "wiwnu"],
        "required_sites": SITES,
    }
    return YieldConfig(**{**base, **kw})


def test_measurement_wafer_and_lot_levels_differ():
    res = evaluate_yield(_obs(WAFERS), _cfg())
    # 4 wafers x (2 depth + 1 wiwnu) = 12 measurements; failures: 111 and wiwnu 6 -> 10/12
    assert res.n_measurements == 12
    assert res.measurement_pass_rate == pytest.approx(10 / 12)
    wafer = res.wafer_table.set_index("wafer_id")["wafer_pass"]
    assert wafer.to_dict() == {"L1-W1": True, "L1-W2": False, "L2-W1": False, "L2-W2": True}
    lot = res.lot_table.set_index("lot_id")
    assert lot["wafer_pass_fraction"].to_dict() == {"L1": 0.5, "L2": 0.5}
    # default threshold 100%: neither lot passes, although 83% of measurements pass
    assert not lot["lot_pass"].any()


def test_lot_threshold_is_config_driven():
    res = evaluate_yield(_obs(WAFERS), _cfg(lot_pass_threshold=0.5))
    assert res.lot_table["lot_pass"].all()


def test_unrequired_metric_does_not_affect_wafer_pass():
    cfg = _cfg(required_metrics=["etch_depth"])
    res = evaluate_yield(_obs(WAFERS), cfg)
    wafer = res.wafer_table.set_index("wafer_id")["wafer_pass"]
    assert bool(wafer["L2-W1"]) is True  # only failed on wiwnu, which is not required


def test_unrequired_site_does_not_affect_wafer_pass():
    cfg = _cfg(required_sites=["center"])
    res = evaluate_yield(_obs(WAFERS), cfg)
    wafer = res.wafer_table.set_index("wafer_id")["wafer_pass"]
    assert bool(wafer["L1-W2"]) is True  # the 111 nm reading was at site N


def test_incomplete_wafer_is_refused_not_silently_passed():
    obs = _obs(WAFERS)
    obs = obs[~((obs["wafer_id"] == "L1-W1") & (obs["site_id"] == "N"))]
    with pytest.raises(ValueError, match="incomplete"):
        evaluate_yield(obs, _cfg())


def test_wafer_missing_every_required_measurement_is_refused():
    obs = _obs(WAFERS)
    obs = obs[~((obs["wafer_id"] == "L1-W1") & obs["metric"].isin(["etch_depth", "wiwnu"]))]
    with pytest.raises(ValueError, match="incomplete"):
        evaluate_yield(obs, _cfg())


def test_config_rejects_bad_specs():
    with pytest.raises(ValidationError):
        SpecLimit()
    with pytest.raises(ValidationError):
        SpecLimit(lsl=5, usl=5)
    with pytest.raises(ValidationError):
        _cfg(required_metrics=["cd_bias"])  # no spec limit for it
    with pytest.raises(ValidationError):
        _cfg(required_sites=[])  # site-level metric required, no sites


def test_dppm_uses_explicit_denominator():
    cfg = DPPMConfig(opportunities_per_wafer=100, defect_definition="any inspected defect")
    res = compute_dppm(_obs(WAFERS), cfg)
    # defects 1+2+3+2 = 8 over 4 wafers x 100 opportunities = 400 -> 20000 DPPM
    assert res.total_defects == 8
    assert res.opportunities == 400
    assert res.dppm == pytest.approx(20000.0)
    assert res.defect_definition == "any inspected defect"


def test_dppm_is_independent_of_spec_failures():
    cfg = DPPMConfig(opportunities_per_wafer=100, defect_definition="d")
    a = compute_dppm(_obs(WAFERS), cfg).dppm
    shifted = [{**w, "depths": [d + 1000 for d in w["depths"]]} for w in WAFERS]
    assert compute_dppm(_obs(shifted), cfg).dppm == a


def test_dppm_requires_denominator_and_definition():
    with pytest.raises(ValidationError):
        DPPMConfig(defect_definition="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        DPPMConfig(opportunities_per_wafer=0, defect_definition="x")
    with pytest.raises(ValidationError):
        DPPMConfig(opportunities_per_wafer=10, defect_definition="")


def test_dppm_with_no_defect_data_raises():
    obs = _obs(WAFERS)
    with pytest.raises(ValueError, match="no defect_count"):
        compute_dppm(
            obs[obs["metric"] != "defect_count"],
            DPPMConfig(opportunities_per_wafer=10, defect_definition="x"),
        )


def test_wilson_interval_known_values():
    lo, hi = wilson_interval(8, 10)
    assert lo == pytest.approx(0.4902, abs=1e-3)
    assert hi == pytest.approx(0.9433, abs=1e-3)
    lo0, hi0 = wilson_interval(0, 10)
    assert lo0 == 0.0 and 0 < hi0 < 0.35
    lo1, hi1 = wilson_interval(10, 10)
    assert hi1 == 1.0 and 0.65 < lo1 < 1.0


def test_wilson_interval_rejects_bad_input():
    with pytest.raises(ValueError):
        wilson_interval(1, 0)
    with pytest.raises(ValueError):
        wilson_interval(11, 10)


def test_yield_end_to_end_on_simulated_fault():
    """Real simulate(): a step shift hits CH-A from lot 5; CH-B stays healthy."""
    start = datetime(2026, 1, 1)
    config = SimulationConfig(
        seed=7,
        start_time=start,
        recipe=RecipeConfig(
            recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
        ),
        tool_chambers=[
            ToolChamberConfig(tool_id="T1", chamber_id="CH-A", depth_offset_sigma_nm=0),
            ToolChamberConfig(tool_id="T1", chamber_id="CH-B", depth_offset_sigma_nm=0),
        ],
        hierarchy=HierarchyConfig(
            lot_size_wafers=5, sites_per_wafer=5, n_lots=10, lot_interval_minutes=60
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=0.5, wafer_sigma_nm=0.5, site_noise_sigma_nm=0.5
        ),
        faults=[
            FaultEvent(
                event_id="SHIFT-1",
                fault_type="step_mean_shift",
                onset=start + timedelta(hours=5),
                tool_id="T1",
                chamber_id="CH-A",
                metric="etch_depth",
                magnitude=200.0,
            )
        ],
    )
    result = simulate(config)
    nominal = result.hidden_truth["fixed_effect_etch_depth_nm"]
    cfg = YieldConfig(
        spec_limits={"etch_depth": SpecLimit(lsl=nominal - 100, usl=nominal + 100)},
        required_metrics=["etch_depth"],
        required_sites=["center", "N", "E", "S", "W"],
    )
    res = evaluate_yield(result.observations, cfg)
    lots = res.lot_table.set_index(["chamber_id", "lot_id"])["lot_pass"]
    a = lots.xs("CH-A")
    b = lots.xs("CH-B")
    assert b.all()
    assert a.sum() == 5 and not a.iloc[5:].any() and a.iloc[:5].all()
