"""ORM model registry — import all models so Base.metadata is fully populated."""

from service_photo.models.listing_job import ListingJob
from service_photo.models.listing_job_image import ListingJobImage
from service_photo.models.listing_job_status_history import ListingJobStatusHistory
from service_photo.models.listing_draft_overview import ListingDraftOverview
from service_photo.models.listing_draft_description import ListingDraftDescription
from service_photo.models.listing_draft_specifications import ListingDraftSpecifications
from service_photo.models.listing_draft_accessories import ListingDraftAccessories
from service_photo.models.listing_review_overview import ListingReviewOverview
from service_photo.models.listing_review_description import ListingReviewDescription
from service_photo.models.listing_review_specifications import ListingReviewSpecifications
from service_photo.models.listing_review_accessories import ListingReviewAccessories
from service_photo.models.listing_exports import ListingExport

__all__ = [
    "ListingJob",
    "ListingJobImage",
    "ListingJobStatusHistory",
    "ListingDraftOverview",
    "ListingDraftDescription",
    "ListingDraftSpecifications",
    "ListingDraftAccessories",
    "ListingReviewOverview",
    "ListingReviewDescription",
    "ListingReviewSpecifications",
    "ListingReviewAccessories",
    "ListingExport",
]
