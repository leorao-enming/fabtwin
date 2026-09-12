"""Western Electric zone rules for out-of-control pattern detection.

Applies on top of any chart with symmetric 3-sigma FrozenLimits (I-MR,
EWMA, Xbar) - not CUSUM, which has its own h-based alarm criterion
(spc/cusum.py) and no meaningful "sigma zones."

Standard four-rule set (Western Electric Statistical Quality Control
Handbook, 1956 - the same rule set NIST's handbook section 6.3.3,
"Out-of-Control Signals," describes qualitatively). Zones are defined in
units of sigma from the center line: Zone C = 0-1 sigma, Zone B = 1-2
sigma, Zone A = 2-3 sigma, beyond = >3 sigma.

Rule 1: one point beyond 3 sigma (zone A / beyond).
Rule 2: 2 of 3 consecutive points beyond 2 sigma, same side (zone A or beyond).
Rule 3: 4 of 5 consecutive points beyond 1 sigma, same side (zone B or beyond).
Rule 4: 8 consecutive points on the same side of the center line.

Every triggered rule returns which rule fired, the index of the point that
completed the pattern, and the contributing window - Overview section 4.2:
"Western Electric/Nelson 规则返回 rule id、触发点与 contributing window."
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleViolation:
    rule_id: str
    trigger_index: int
    contributing_window: tuple[int, int]  # inclusive (start, end) indices into the input series


def evaluate(values: list[float], center_line: float, sigma: float) -> list[RuleViolation]:
    if sigma <= 0:
        raise ValueError("sigma must be positive to evaluate zone rules")
    z = [(v - center_line) / sigma for v in values]
    violations: list[RuleViolation] = []

    for i, zi in enumerate(z):
        if abs(zi) > 3:
            violations.append(RuleViolation("WE1", i, (i, i)))

    for i in range(2, len(z)):
        window = z[i - 2 : i + 1]
        if sum(1 for w in window if w > 2) >= 2 or sum(1 for w in window if w < -2) >= 2:
            violations.append(RuleViolation("WE2", i, (i - 2, i)))

    for i in range(4, len(z)):
        window = z[i - 4 : i + 1]
        if sum(1 for w in window if w > 1) >= 4 or sum(1 for w in window if w < -1) >= 4:
            violations.append(RuleViolation("WE3", i, (i - 4, i)))

    for i in range(7, len(z)):
        window = z[i - 7 : i + 1]
        if all(w > 0 for w in window) or all(w < 0 for w in window):
            violations.append(RuleViolation("WE4", i, (i - 7, i)))

    return violations
