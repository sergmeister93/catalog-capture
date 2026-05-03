"""
Unit tests for the approval validator.

Tests that _run_approval_validation collects ALL failures in one pass
without short-circuiting, as required by approval_validation_rules.md.
"""

import pytest
from tests.fixtures.factories import (
    scenario_e_approval_failure,
    scenario_f_approved,
    scenario_d_partial_review,
)
from service_photo.services.approval_service import _run_approval_validation


def test_approval_failure_returns_all_rules(db):
    """
    Scenario E: all four sections have invalid values.
    Validator must return all 4 failures in a single pass.
    """
    job = scenario_e_approval_failure(db)
    failures = _run_approval_validation(db, job.job_id)
    rule_ids = {f.rule for f in failures}

    # Each failing rule must be reported.
    assert "review_overview.product_name_blank" in rule_ids
    assert "review_description.description_text_blank" in rule_ids
    assert "review_specifications.no_meaningful_spec" in rule_ids
    assert "review_accessories.included_accessories_text_blank" in rule_ids


def test_approval_passes_on_valid_content(db):
    """Scenario F: all review rows are valid — no failures."""
    job = scenario_f_approved(db)
    # Set back to under_review for validator test only (don't change the DB fixture).
    job.status = "under_review"
    failures = _run_approval_validation(db, job.job_id)
    assert failures == []


def test_approval_fails_on_missing_sections(db):
    """Scenario D: only overview + description saved — specs and accessories missing."""
    job = scenario_d_partial_review(db)
    failures = _run_approval_validation(db, job.job_id)
    rule_ids = {f.rule for f in failures}

    assert "missing_review_specifications" in rule_ids
    assert "missing_review_accessories" in rule_ids


def test_approval_does_not_short_circuit(db):
    """Multiple failures must all appear; not just the first one."""
    job = scenario_e_approval_failure(db)
    failures = _run_approval_validation(db, job.job_id)
    # There should be at least 4 distinct failures.
    assert len(failures) >= 4
