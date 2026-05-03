"""Unit tests for job number generation."""

from datetime import date


def test_generate_job_number_format(db):
    """Generated job number matches JOB-YYYYMMDD-NNN format."""
    from service_photo.utils.job_number import generate_job_number
    result = generate_job_number(db, for_date=date(2026, 4, 19))
    assert result.startswith("JOB-20260419-")
    # The sequence part should be 3 digits.
    seq_part = result.split("-")[-1]
    assert len(seq_part) == 3
    assert seq_part.isdigit()


def test_generate_job_number_first_of_day(db):
    """First job of the day gets sequence 001."""
    from service_photo.utils.job_number import generate_job_number
    result = generate_job_number(db, for_date=date(2099, 1, 1))
    assert result == "JOB-20990101-001"


def test_generate_job_number_increments(db):
    """Sequence increments for each job on the same date."""
    from service_photo.utils.job_number import generate_job_number
    from service_photo.services.job_service import create_listing_job

    # Create two jobs and verify both get sequential numbers.
    job1 = create_listing_job(db, None, None, None)
    job2 = create_listing_job(db, None, None, None)

    today_str = job1.job_number.split("JOB-")[1].split("-")[0]
    assert job1.job_number == f"JOB-{today_str}-001"
    assert job2.job_number == f"JOB-{today_str}-002"
