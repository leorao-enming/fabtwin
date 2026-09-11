"""Wires the T1 simulator's observation table into the T2 SPC/capability
layer - the first place simulator output and SPC methods actually meet.
Everything in spc/ has so far only been exercised against static NIST data
or synthetic lists built by hand in tests; this module is what proves the
two layers actually fit together.

Spec limits (usl/lsl) are passed in as explicit analysis-time arguments
here, not read from SimulationConfig: SimulationConfig only describes how
the process behaves (data-dictionary.md sections 1-6), not what counts as
acceptable. Case-level spec limits become a configs/ concern at Gate T4;
until then, callers supply them directly.

The Phase I/II window is a prefix/suffix split of the per-lot series in
timestamp order - callers choose phase_i_n_lots to mark where the
"known-healthy history" ends, per Overview section 4.2's requirement that
Phase I never include data a case is trying to detect a fault in.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from fabtwin.config import Metric
from fabtwin.spc.capability import CapabilityResult, cp_cpk, sigma_within
from fabtwin.spc.ewma import apply_phase_ii as ewma_apply_phase_ii
from fabtwin.spc.ewma import fit_phase_i as ewma_fit_phase_i
from fabtwin.spc.imr import apply_phase_ii as imr_apply_phase_ii
from fabtwin.spc.imr import fit_phase_i as imr_fit_phase_i
from fabtwin.spc.phase import ChartPoint, FrozenLimits


def extract_lot_series(
    observations: pd.DataFrame, tool_id: str, chamber_id: str, metric: Metric
) -> pd.DataFrame:
    """One row per lot: lot_id, timestamp, mean `metric` value across that
    lot's site/wafer readings, for one (tool_id, chamber_id), in
    timestamp order.

    A per-lot mean is the v1 monitoring granularity - matching how the
    simulator advances time lot-by-lot (simulator.py) rather than treating
    every individual site reading as its own time point.
    """
    subset = observations[
        (observations["tool_id"] == tool_id)
        & (observations["chamber_id"] == chamber_id)
        & (observations["metric"] == metric)
    ]
    if subset.empty:
        raise ValueError(
            f"no observations for tool_id={tool_id!r} chamber_id={chamber_id!r} metric={metric!r}"
        )
    return (
        subset.groupby(["lot_id", "timestamp"], as_index=False)["value"]
        .mean()
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def split_phase_i_ii(
    series: pd.DataFrame, phase_i_n_lots: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if phase_i_n_lots < 2:
        raise ValueError("Phase I window needs at least 2 lots to estimate a moving-range sigma")
    if phase_i_n_lots >= len(series):
        raise ValueError(
            f"phase_i_n_lots={phase_i_n_lots} leaves no Phase II data "
            f"(series has {len(series)} lots total)"
        )
    return series.iloc[:phase_i_n_lots].reset_index(drop=True), series.iloc[
        phase_i_n_lots:
    ].reset_index(drop=True)


@dataclass
class SPCRunResult:
    """Phase I fit + Phase II scoring, bundled with the exact data each
    phase was computed from - so a result is always traceable back to
    which lots were "healthy history" vs "monitored", not just a bare
    pass/fail.
    """

    method: str
    limits: FrozenLimits
    phase_i: pd.DataFrame
    phase_ii: pd.DataFrame
    points: list[ChartPoint]

    @property
    def any_out_of_control(self) -> bool:
        return any(p.out_of_control for p in self.points)

    @property
    def first_alarm_index(self) -> int | None:
        """Index into `points` (i.e. into phase_ii) of the first alarm, or
        None. This is scaffolding, not the T3 detection-scoring API -
        Overview section 4.3's event_detected/detection_delay/
        pre_fault_false_alarms/missed_event fields (which need the
        simulator's hidden-truth fault ground truth, not just this
        observation-only result) still belong to Gate T3.
        """
        for p in self.points:
            if p.out_of_control:
                return p.index
        return None


def run_imr(
    observations: pd.DataFrame,
    tool_id: str,
    chamber_id: str,
    metric: Metric,
    phase_i_n_lots: int,
) -> SPCRunResult:
    series = extract_lot_series(observations, tool_id, chamber_id, metric)
    phase_i, phase_ii = split_phase_i_ii(series, phase_i_n_lots)
    limits = imr_fit_phase_i(phase_i["value"].tolist())
    points = imr_apply_phase_ii(phase_ii["value"].tolist(), limits)
    return SPCRunResult("I-MR", limits, phase_i, phase_ii, points)


def run_ewma(
    observations: pd.DataFrame,
    tool_id: str,
    chamber_id: str,
    metric: Metric,
    phase_i_n_lots: int,
    lam: float = 0.3,
    l_factor: float = 3.0,
) -> SPCRunResult:
    series = extract_lot_series(observations, tool_id, chamber_id, metric)
    phase_i, phase_ii = split_phase_i_ii(series, phase_i_n_lots)
    phase_i_values = phase_i["value"].tolist()
    target = sum(phase_i_values) / len(phase_i_values)
    sigma = sigma_within(phase_i_values)  # moving-range sigma estimator, shared with capability.py
    limits = ewma_fit_phase_i(target=target, sigma=sigma, lam=lam, l_factor=l_factor)
    points = ewma_apply_phase_ii(phase_ii["value"].tolist(), limits)
    return SPCRunResult("EWMA", limits, phase_i, phase_ii, points)


def run_capability(
    observations: pd.DataFrame,
    tool_id: str,
    chamber_id: str,
    metric: Metric,
    phase_i_n_lots: int,
    usl: float,
    lsl: float,
) -> CapabilityResult:
    """Capability is computed from the Phase I (known-healthy) window only
    - scoring capability on data that may include a fault would silently
    reintroduce the same mistake Phase I/II separation exists to prevent.
    """
    series = extract_lot_series(observations, tool_id, chamber_id, metric)
    phase_i, _ = split_phase_i_ii(series, phase_i_n_lots)
    values = phase_i["value"].tolist()
    mean = sum(values) / len(values)
    sigma = sigma_within(values)
    return cp_cpk(mean=mean, sigma_within=sigma, usl=usl, lsl=lsl, n=len(values))
