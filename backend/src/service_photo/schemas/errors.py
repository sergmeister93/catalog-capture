"""Pydantic schemas for error responses — must match openapi_service_photo_poc.yaml."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error envelope used by all non-validation error responses."""
    error: str
    message: str


class ValidationFailure(BaseModel):
    """One failing approval rule."""
    rule: str
    detail: str


class ApprovalValidationError(BaseModel):
    """Returned by POST /jobs/{job_id}/approve when the approval gate fails."""
    error: str = "approval_validation_failed"
    message: str = "Job cannot be approved; required content is missing or invalid"
    validation_failures: list[ValidationFailure]
