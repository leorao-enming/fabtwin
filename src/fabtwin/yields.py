"""Three-level yield and DPPM - Overview section 4.3 / data-dictionary.md
section 8.

Yield is three explicit, non-interchangeable levels (measurement_pass,
wafer_pass, lot_pass), each driven by config. DPPM is computed from the
`defect_count` metric against an explicit opportunity count; it is never
derived from spec-limit failures, and there is no default denominator.

Reads only the observation table. Hidden truth is never needed here, which
keeps this layer honest in the same way analysis.py is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from fabtwin.config import SITE_LEVEL_METRICS, Metric

_WAFER_KEYS = ["tool_id", "chamber_id", "lot_id", "wafer_id"]


class SpecLimit(BaseModel):
    lsl: float | None = None
    usl: float | None = None

    @model_validator(mode="after")
    def _at_least_one_ordered(self) -> SpecLimit:
        if self.lsl is None and self.usl is None:
            raise ValueError("a spec limit needs at least one of lsl / usl")
        if self.lsl is not None and self.usl is not None and self.lsl >= self.usl:
            raise ValueError(f"lsl ({self.lsl}) must be below usl ({self.usl})")
        return self

    def passes(self, values: pd.Series) -> pd.Series:
        ok = pd.Series(True, index=values.index)
        if self.lsl is not None:
            ok &= values >= self.lsl
        if self.usl is not None:
            ok &= values <= self.usl
        return ok


class YieldConfig(BaseModel):
    """data-dictionary.md section 8 - every pass rule is config-driven."""

    spec_limits: dict[Metric, SpecLimit]
    required_metrics: list[Metric] = Field(min_length=1)
    required_sites: list[str] = Field(default_factory=list)
    lot_pass_threshold: float = Field(default=1.0, gt=0, le=1.0)

    @model_validator(mode="after")
    def _consistent(self) -> YieldConfig:
        missing = [m for m in self.required_metrics if m not in self.spec_limits]
        if missing:
            raise ValueError(f"required metrics without a spec limit: {missing}")
        if any(m in SITE_LEVEL_METRICS for m in self.required_metrics) and not self.required_sites:
            raise ValueError("a site-level metric is required but required_sites is empty")
        return self


class DPPMConfig(BaseModel):
    """Explicit denominator and defect definition; no implicit defaults."""

    opportunities_per_wafer: int = Field(gt=0)
    defect_definition: str = Field(min_length=1)


@dataclass(frozen=True)
class YieldResult:
    wafer_table: pd.DataFrame
    lot_table: pd.DataFrame
    measurement_pass_rate: float
    n_measurements: int


@dataclass(frozen=True)
class DPPMResult:
    dppm: float
    total_defects: float
    n_wafers: int
    opportunities: int
    defect_definition: str


def wilson_interval(passes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= passes <= n:
        raise ValueError("passes must be within [0, n]")
    p = passes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _required_rows(observations: pd.DataFrame, cfg: YieldConfig) -> pd.DataFrame:
    site_level = observations["metric"].isin(SITE_LEVEL_METRICS)
    wanted = observations["metric"].isin(cfg.required_metrics) & (
        ~site_level | observations["site_id"].isin(cfg.required_sites)
    )
    return observations.loc[wanted].copy()


def _check_complete(required: pd.DataFrame, observations: pd.DataFrame, cfg: YieldConfig) -> None:
    per_wafer = sum(
        len(cfg.required_sites) if m in SITE_LEVEL_METRICS else 1 for m in cfg.required_metrics
    )
    n_wafers = observations.drop_duplicates(_WAFER_KEYS).shape[0]
    counts = required.groupby(_WAFER_KEYS).size()
    short = int(((counts != per_wafer).sum()) + (n_wafers - len(counts)))
    if short:
        raise ValueError(
            f"{short} wafer(s) lack the {per_wafer} required measurements; "
            "refusing to score yield on incomplete wafers"
        )


def evaluate_yield(observations: pd.DataFrame, cfg: YieldConfig) -> YieldResult:
    required = _required_rows(observations, cfg)
    _check_complete(required, observations, cfg)

    required["measurement_pass"] = False
    for metric in cfg.required_metrics:
        mask = required["metric"] == metric
        required.loc[mask, "measurement_pass"] = cfg.spec_limits[metric].passes(
            required.loc[mask, "value"]
        )

    wafer = (
        required.groupby(_WAFER_KEYS, sort=True)["measurement_pass"]
        .all()
        .rename("wafer_pass")
        .reset_index()
    )
    lot = (
        wafer.groupby(["tool_id", "chamber_id", "lot_id"], sort=True)["wafer_pass"]
        .agg(n_wafers="size", n_wafers_pass="sum")
        .reset_index()
    )
    lot["n_wafers_pass"] = lot["n_wafers_pass"].astype(int)
    lot["wafer_pass_fraction"] = lot["n_wafers_pass"] / lot["n_wafers"]
    lot["lot_pass"] = lot["wafer_pass_fraction"] >= cfg.lot_pass_threshold

    return YieldResult(
        wafer_table=wafer,
        lot_table=lot,
        measurement_pass_rate=float(required["measurement_pass"].mean()),
        n_measurements=len(required),
    )


def compute_dppm(observations: pd.DataFrame, cfg: DPPMConfig) -> DPPMResult:
    defects = observations.loc[observations["metric"] == "defect_count"]
    n_wafers = defects.drop_duplicates(_WAFER_KEYS).shape[0]
    if n_wafers == 0:
        raise ValueError("no defect_count observations to compute DPPM from")
    if len(defects) != n_wafers:
        raise ValueError("expected exactly one defect_count observation per wafer")
    total = float(defects["value"].sum())
    opportunities = n_wafers * cfg.opportunities_per_wafer
    return DPPMResult(
        dppm=total / opportunities * 1e6,
        total_defects=total,
        n_wafers=n_wafers,
        opportunities=opportunities,
        defect_definition=cfg.defect_definition,
    )
