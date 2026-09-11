"""Phase I / Phase II separation - Overview section 4.2.

Phase I uses a health-labeled historical window to estimate a center line
and control limits. Phase II freezes those parameters and monitors
subsequent data without ever recomputing limits from data that may contain
a fault. Using the full (possibly fault-contaminated) run to both estimate
limits and then score detection on is exactly the mistake Overview section
4.2 forbids ("禁止用包含 fault 的全量数据重算控制限后再声称检测成功") - this
module makes that mistake structurally harder: FrozenLimits is immutable
once a Phase I fit function returns one, and every chart module's "apply"
function takes a FrozenLimits in, never re-estimates it from the data it is
scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FrozenLimits:
    """Control limits estimated once from Phase I data and held fixed.

    `params` always records every method-specific parameter that produced
    these limits (Overview 4.2: "lambda/L/k/h/target 全部写入结果元数据") -
    so a chart's limits are always independently reconstructable and
    auditable, never a bare pair of numbers with no provenance.
    """

    center_line: float
    ucl: float
    lcl: float
    method: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChartPoint:
    """One Phase II monitored point - not the same thing as a spec-limit
    pass/fail (Overview 4.2: "control limits 与 specification limits 在数据
    模型和图例中永久分开"). Capability functions in capability.py take spec
    limits as an entirely separate, explicit argument; nothing in this
    module ever compares a value to a spec limit.
    """

    index: int
    value: float
    out_of_control: bool
