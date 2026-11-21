"""Measure what calibrated limits (spc/calibration.py) change, on simulator data.

Scenario (the case-1 shape used in tests/unit/test_analysis.py): two chambers, 30 lots,
1 lot per hour, small lot/wafer/site sigma; chamber A starts a 5 nm/h etch_depth drift at
hour 10; Phase I = first 10 lots, Phase II = the remaining 20. Over many seeds:

- healthy false-alarm rate: share of runs where chamber B's chart alarms at least once;
- detection on chamber A: share detected, and the median detection delay.

Classical limits vs limits calibrated to a 5 % family-wise false-alarm target. A second,
small-shift scenario (step +1.0 nm lot-mean shift) shows the cost in sensitivity.
PCA (etch_depth, cd_bias, wiwnu; 15-lot Phase I, 25-lot Phase II) is measured separately
with fewer seeds because each calibrated run refits a bootstrap.

Writes evidence/t4-false-alarm-calibration.json (gitignored).
Usage: python scripts/t4_false_alarm_calibration.py [n_seeds]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

from fabtwin.analysis import run_cusum, run_ewma, run_imr, run_pca_monitor
from fabtwin.config import (
    FaultEvent,
    HierarchyConfig,
    RandomEffectConfig,
    RecipeConfig,
    SimulationConfig,
    ToolChamberConfig,
)
from fabtwin.detection import score_detection
from fabtwin.simulator import simulate

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evidence" / "t4-false-alarm-calibration.json"
START = datetime(2026, 1, 1)
TARGET = 0.05
RUNNERS = {"I-MR": run_imr, "EWMA": run_ewma, "CUSUM": run_cusum}


def config(seed: int, fault: FaultEvent, n_lots: int = 30) -> SimulationConfig:
    return SimulationConfig(
        seed=seed,
        start_time=START,
        recipe=RecipeConfig(
            recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
        ),
        tool_chambers=[
            ToolChamberConfig(tool_id="T1", chamber_id="A"),
            ToolChamberConfig(tool_id="T1", chamber_id="B"),
        ],
        hierarchy=HierarchyConfig(
            lot_size_wafers=10, sites_per_wafer=5, n_lots=n_lots, lot_interval_minutes=60
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=0.5, wafer_sigma_nm=0.5, site_noise_sigma_nm=0.5
        ),
        faults=[fault],
    )


def fault(kind: str, magnitude: float, onset_h: float) -> FaultEvent:
    return FaultEvent(
        event_id="F",
        fault_type=kind,
        onset=START + timedelta(hours=onset_h),
        tool_id="T1",
        chamber_id="A",
        metric="etch_depth",
        magnitude=magnitude,
    )


def univariate(n_seeds: int, f: FaultEvent) -> dict:
    out: dict = {}
    for name, runner in RUNNERS.items():
        for mode, target in (("classical", None), ("calibrated_5pct", TARGET)):
            fa = det = 0
            delays: list[float] = []
            for seed in range(n_seeds):
                obs = simulate(config(seed, f)).observations
                healthy = runner(obs, "T1", "B", "etch_depth", 10, false_alarm_target=target)
                faulty = runner(obs, "T1", "A", "etch_depth", 10, false_alarm_target=target)
                fa += healthy.any_out_of_control
                s = score_detection(faulty, f)
                if s.event_detected and s.detection_delay is not None:
                    det += 1
                    delays.append(s.detection_delay.total_seconds() / 3600)
            out[f"{name}/{mode}"] = {
                "healthy_any_alarm_rate": fa / n_seeds,
                "detected_rate": det / n_seeds,
                "median_delay_h": median(delays) if delays else None,
            }
    return out


def pca(n_seeds: int) -> dict:
    f = fault("step_mean_shift", 8.0, 15.0)
    metrics = ["etch_depth", "cd_bias", "wiwnu"]
    out: dict = {}
    for mode, target in (("classical", None), ("calibrated_5pct", TARGET)):
        fa = det = 0
        for seed in range(n_seeds):
            obs = simulate(config(seed, f, n_lots=40)).observations
            kw = {"n_components": 2, "false_alarm_target": target}
            fa += run_pca_monitor(obs, "T1", "B", metrics, 15, **kw).any_out_of_control
            det += score_detection(
                run_pca_monitor(obs, "T1", "A", metrics, 15, **kw), f
            ).event_detected
        out[f"PCA-T2-SPE/{mode}"] = {
            "healthy_any_alarm_rate": fa / n_seeds,
            "detected_rate": det / n_seeds,
        }
    return out


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    report = {
        "n_seeds": n,
        "target_false_alarm": TARGET,
        "drift_5nm_per_h": univariate(n, fault("linear_drift", 5.0, 10.0)),
        "step_1nm": univariate(n, fault("step_mean_shift", 1.0, 10.0)),
        "pca_step_8nm": pca(max(20, n // 5)),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for scenario in ("drift_5nm_per_h", "step_1nm", "pca_step_8nm"):
        print(scenario)
        for k, v in report[scenario].items():
            print(
                f"  {k:24s} "
                + "  ".join(
                    f"{a}={b:.2f}" if isinstance(b, float) else f"{a}={b}" for a, b in v.items()
                )
            )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
