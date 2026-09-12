"""Unit tests for src/fabtwin/spc/rules.py - the Western Electric zone
rules. Each test hand-constructs a sequence designed to trigger exactly one
rule, in standardized (center=0, sigma=1) z-score units unless noted, so
the trigger condition is verifiable by inspection.
"""

import pytest

from fabtwin.spc.rules import evaluate


def test_rule1_single_point_beyond_3_sigma():
    values = [0.0, 0.0, 0.0, 3.5, 0.0]
    violations = evaluate(values, center_line=0.0, sigma=1.0)
    rule1 = [v for v in violations if v.rule_id == "WE1"]
    assert len(rule1) == 1
    assert rule1[0].trigger_index == 3
    assert rule1[0].contributing_window == (3, 3)


def test_rule1_does_not_fire_at_exactly_3_sigma():
    values = [0.0, 3.0, 0.0]  # boundary: "beyond" 3 sigma, not at it
    violations = evaluate(values, center_line=0.0, sigma=1.0)
    assert not any(v.rule_id == "WE1" for v in violations)


def test_rule2_two_of_three_beyond_2_sigma_same_side():
    values = [0.0, 2.5, 2.2, 0.0]
    violations = evaluate(values, center_line=0.0, sigma=1.0)
    rule2 = [v for v in violations if v.rule_id == "WE2"]
    # the window at i=2 ([0, 2.5, 2.2]) and the window at i=3 ([2.5, 2.2, 0])
    # both contain 2 of 3 points beyond 2 sigma - both legitimately fire, one
    # violation per completed window, not deduplicated across overlapping windows.
    assert len(rule2) == 2
    assert rule2[0].trigger_index == 2
    assert rule2[0].contributing_window == (0, 2)
    assert rule2[1].trigger_index == 3
    assert rule2[1].contributing_window == (1, 3)


def test_rule2_does_not_fire_for_opposite_sides():
    values = [0.0, 2.5, -2.2, 0.0]  # beyond 2 sigma but on opposite sides
    violations = evaluate(values, center_line=0.0, sigma=1.0)
    assert not any(v.rule_id == "WE2" for v in violations)


def test_rule3_four_of_five_beyond_1_sigma_same_side():
    values = [0.0, 1.5, 1.2, 1.3, 1.1]
    violations = evaluate(values, center_line=0.0, sigma=1.0)
    rule3 = [v for v in violations if v.rule_id == "WE3"]
    assert len(rule3) == 1
    assert rule3[0].trigger_index == 4
    assert rule3[0].contributing_window == (0, 4)


def test_rule4_eight_consecutive_same_side():
    values = [0.3] * 8
    violations = evaluate(values, center_line=0.0, sigma=1.0)
    rule4 = [v for v in violations if v.rule_id == "WE4"]
    assert len(rule4) == 1
    assert rule4[0].trigger_index == 7
    assert rule4[0].contributing_window == (0, 7)


def test_rule4_does_not_fire_when_sides_alternate():
    values = [0.3, -0.3, 0.3, -0.3, 0.3, -0.3, 0.3, -0.3]
    violations = evaluate(values, center_line=0.0, sigma=1.0)
    assert not any(v.rule_id == "WE4" for v in violations)


def test_evaluate_standardizes_using_center_and_sigma_not_raw_values():
    # same shape as the rule-1 test, but shifted/scaled - center=100, sigma=2
    # means a raw value of 107 is 3.5 sigma away, matching the z=3.5 case above.
    values = [100.0, 100.0, 100.0, 107.0, 100.0]
    violations = evaluate(values, center_line=100.0, sigma=2.0)
    assert any(v.rule_id == "WE1" and v.trigger_index == 3 for v in violations)


def test_evaluate_rejects_nonpositive_sigma():
    with pytest.raises(ValueError, match="sigma must be positive"):
        evaluate([1.0, 2.0], center_line=0.0, sigma=0.0)


def test_no_violations_for_well_behaved_series():
    values = [0.1, -0.1, 0.2, -0.2, 0.1, -0.1, 0.15, -0.15]
    violations = evaluate(values, center_line=0.0, sigma=1.0)
    assert violations == []
