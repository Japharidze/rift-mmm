"""The match label reads how well the point is known, not only how close the
champion is (2026-09-30: two or three games and one comparison showed "a real
match")."""

import pytest

from r3m import quiz, scoring


def est_with(evidence: float, point=(0.6, 0.5, 0.6)) -> quiz.Estimate:
    return quiz.Estimate(dimensions={d: quiz.DimensionEstimate(value=v, informative=evidence)
                                     for d, v in zip(quiz.DIMENSIONS, point)})


def test_uncertainty_falls_with_evidence_as_a_standard_error():
    assert quiz.uncertainty(est_with(1.0))["micro"] == pytest.approx(quiz.EVIDENCE_SIGMA)
    assert quiz.uncertainty(est_with(4.0))["micro"] == pytest.approx(quiz.EVIDENCE_SIGMA / 2)
    assert quiz.point_uncertainty(est_with(0.0)) is None


def test_few_answers_never_yield_a_real_match_even_right_on_a_champion():
    thin = est_with(0.7)          # two or three games' worth on each dimension
    assert quiz.confidence(0.0, thin, recognised=3, loves=3) == "fair"
    assert quiz.confidence(0.0, thin, recognised=20, loves=10) == "fair"   # the arithmetic, not only the floor


def test_the_same_point_with_more_evidence_can():
    rich = est_with(3.0)
    assert quiz.point_uncertainty(rich) <= quiz.CONFIDENT_UNCERTAINTY
    assert quiz.confidence(0.05, rich, recognised=20, loves=8) == "close"


def test_the_floor_holds_whatever_the_arithmetic_says():
    rich = est_with(3.0)
    assert quiz.confidence(0.05, rich, recognised=quiz.CONFIDENT_RECOGNISED - 1, loves=8) == "fair"
    assert quiz.confidence(0.05, rich, recognised=20, loves=quiz.CONFIDENT_LOVES - 1) == "fair"


def test_distance_alone_still_decides_distant():
    assert quiz.confidence(scoring.FAIR + 0.01, est_with(3.0), recognised=20, loves=8) == "distant"
    assert quiz.confidence(scoring.FAIR - 0.01, est_with(0.7), recognised=3, loves=2) == "fair"
