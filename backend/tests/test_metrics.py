import pytest

from app.config import Criteria
from app.services.metrics import (STATUS_FAIL, STATUS_INCOMPLETE, STATUS_NOT_ASSESSABLE, STATUS_PASS, assess,
                                  classify_change, delta_curve, interp)

C = Criteria()  # 15 mm, 0–50 Hz


def codes(a):
    return {w.code for w in a.warnings}


def test_exactly_at_limit_passes():
    a = assess([5, 30, 50], [1, 15.0, 2], C)
    assert a.status == STATUS_PASS and a.peak_magnitude == 15.0 and a.margin == 0


def test_just_above_limit_fails():
    a = assess([5, 30, 50], [1, 15.01, 2], C)
    assert a.status == STATUS_FAIL and a.margin < 0


def test_50hz_is_inclusive():
    a = assess([5, 25, 50], [1, 2, 16], C)
    assert a.status == STATUS_FAIL and a.peak_frequency == 50


def test_just_over_50hz_is_excluded():
    a = assess([5, 25, 50, 50.1, 60], [1, 2, 3, 99, 99], C)
    assert a.status == STATUS_PASS and a.peak_magnitude == 3
    assert a.overall_peak_magnitude == 99  # still reported, but does not affect the verdict


def test_peak_above_range_does_not_fail():
    a = assess([5, 40, 60, 100], [1, 5, 40, 50], C)
    assert a.status == STATUS_PASS


def test_peak_tie_uses_lowest_frequency():
    a = assess([10, 20, 30], [5, 5, 1], C)
    assert a.peak_frequency == 10


def test_incomplete_coverage_is_not_a_pass():
    a = assess([5, 20, 40], [1, 2, 3], C)
    assert a.status == STATUS_INCOMPLETE and "RANGE_INCOMPLETE" in codes(a)


def test_incomplete_but_violation_observed_still_fails():
    assert assess([5, 20, 40], [1, 20, 3], C).status == STATUS_FAIL


def test_no_samples_in_range():
    a = assess([60, 80], [1, 2], C)
    assert a.status == STATUS_NOT_ASSESSABLE and a.peak_magnitude is None


def test_marginal_pass_flagged():
    a = assess([5, 37.8, 50], [1, 14.9, 1], C)
    assert a.status == STATUS_PASS and a.marginal and "MARGINAL" in codes(a)
    assert not assess([5, 37.8, 50], [1, 10, 1], C).marginal


def test_low_start_is_info():
    a = assess([5, 25, 50], [1, 2, 3], C)
    assert "LOW_START" in codes(a)


def test_custom_criteria():
    a = assess([5, 30, 50], [1, 8, 2], Criteria(limit=7.5, f_max=30))
    assert a.status == STATUS_FAIL and a.peak_frequency == 30


def test_empty_input_raises():
    with pytest.raises(ValueError):
        assess([], [], C)


def test_interp_and_delta_curve_on_different_grids():
    assert interp([0, 10], [0, 10], 4) == 4
    d = delta_curve([0, 10], [0, 10], [0, 5, 10], [0, 5, 20])
    assert [p["frequency"] for p in d] == [0, 5, 10]
    assert d[1]["delta"] == pytest.approx(5 - 5) and d[2]["delta"] == 10


def test_delta_curve_no_overlap():
    assert delta_curve([0, 1], [1, 1], [5, 6], [1, 1]) == []


def test_classify_change():
    assert classify_change(-0.5, 0.05) == "improved"
    assert classify_change(0.5, 0.05) == "degraded"
    assert classify_change(0.04, 0.05) == "unchanged"
    assert classify_change(None, 0.05) == "unknown"
