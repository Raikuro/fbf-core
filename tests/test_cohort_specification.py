"""Unit tests for CohortSpecification value object."""

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from research import CohortSpecification


def test_cohort_specification_creation_with_default_id() -> None:
    d = date(1871, 1, 15)
    cohort = CohortSpecification(start_date=d)

    assert cohort.start_date == d
    assert cohort.id == "1871-01-15"


def test_cohort_specification_creation_with_custom_id() -> None:
    d = date(1929, 10, 1)
    cohort = CohortSpecification(start_date=d, id="GreatDepression_1929")

    assert cohort.start_date == d
    assert cohort.id == "GreatDepression_1929"


def test_cohort_specification_immutability() -> None:
    cohort = CohortSpecification(start_date=date(2000, 1, 1))

    with pytest.raises(FrozenInstanceError):
        cohort.start_date = date(2001, 1, 1)  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        cohort.id = "modified_id"  # type: ignore[misc]


def test_cohort_specification_validation_null_date() -> None:
    with pytest.raises(ValueError, match="start_date cannot be None"):
        CohortSpecification(start_date=None)  # type: ignore[arg-type]


def test_cohort_specification_validation_invalid_date_type() -> None:
    with pytest.raises(TypeError, match="must be a datetime.date instance"):
        CohortSpecification(start_date="1871-01-01")  # type: ignore[arg-type]


def test_cohort_specification_validation_empty_id() -> None:
    with pytest.raises(ValueError, match="id cannot be empty or whitespace"):
        CohortSpecification(start_date=date(1871, 1, 1), id="   ")


def test_cohort_specification_equality_and_hashing() -> None:
    c1 = CohortSpecification(start_date=date(1871, 1, 1), id="1871-01-01")
    c2 = CohortSpecification(start_date=date(1871, 1, 1))
    c3 = CohortSpecification(start_date=date(1871, 2, 1))

    assert c1 == c2
    assert c1 != c3
    assert hash(c1) == hash(c2)
    assert hash(c1) != hash(c3)

    cohort_set = {c1, c2, c3}
    assert len(cohort_set) == 2


def test_cohort_specification_chronological_sorting() -> None:
    c1 = CohortSpecification(start_date=date(1999, 1, 1), id="Z_cohort")
    c2 = CohortSpecification(start_date=date(1871, 1, 1), id="A_cohort")
    c3 = CohortSpecification(start_date=date(1929, 10, 1), id="M_cohort")

    cohorts = [c1, c2, c3]
    sorted_cohorts = sorted(cohorts, key=lambda c: c.start_date)

    assert sorted_cohorts == [c2, c3, c1]
