"""Tests for dynamic scoring, decay calculation, and first blood bonuses."""

from app.services.scoring import (
    calculate_first_blood_bonus,
    compute_dynamic_points,
)


def test_dynamic_decay_first_solve_gets_base_points():
    pts = compute_dynamic_points(base_points=500, solve_count=1, min_points=100, decay_scale=10)
    assert pts == 500


def test_dynamic_decay_drops_as_solves_increase():
    p1 = compute_dynamic_points(base_points=500, solve_count=1, min_points=100, decay_scale=10)
    p2 = compute_dynamic_points(base_points=500, solve_count=2, min_points=100, decay_scale=10)
    p5 = compute_dynamic_points(base_points=500, solve_count=5, min_points=100, decay_scale=10)
    p20 = compute_dynamic_points(base_points=500, solve_count=20, min_points=100, decay_scale=10)
    p100 = compute_dynamic_points(base_points=500, solve_count=100, min_points=100, decay_scale=10)

    assert p1 > p2 > p5 > p20 >= p100
    assert p100 >= 100  # Never drops below minimum floor


def test_first_blood_bonus_scaling():
    base = 500
    b1 = calculate_first_blood_bonus(1, base)
    b2 = calculate_first_blood_bonus(2, base)
    b3 = calculate_first_blood_bonus(3, base)
    b4 = calculate_first_blood_bonus(4, base)

    assert b1 == 100  # 20%
    assert b2 == 50  # 10%
    assert b3 == 25  # 5%
    assert b4 == 0  # No bonus for 4th onwards
