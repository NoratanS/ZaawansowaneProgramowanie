from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, HttpUrl


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


class AnalysisJob(BaseModel):
    """The message on ``analysis-jobs``: one image to analyse."""

    job_id: UUID
    image_url: HttpUrl
    requested_at: UtcDatetime
