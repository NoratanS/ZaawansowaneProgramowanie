from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    Field,
    HttpUrl,
    model_validator,
)

ErrorCode = Literal["image_unreachable", "not_an_image", "image_too_large"]


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


class AnalysisJob(BaseModel):
    """The message on ``analysis-jobs``: one image to analyse."""

    job_id: UUID
    image_url: HttpUrl
    requested_at: UtcDatetime


class Box(BaseModel):
    """One person's box, in integer pixels of the original image."""

    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]
    confidence: Annotated[float, Field(ge=0, le=1)]


class ResultError(BaseModel):
    code: ErrorCode
    message: str


class AnalysisResult(BaseModel):
    """The message on ``analysis-results``: the final outcome of one job."""

    job_id: UUID
    image_url: HttpUrl
    status: Literal["succeeded", "failed"]
    person_count: Annotated[int, Field(ge=0)] | None = None
    detections: list[Box] | None = None
    error: ResultError | None = None
    model: str
    requested_at: UtcDatetime
    analyzed_at: UtcDatetime

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if self.status == "succeeded":
            if self.person_count is None or self.detections is None:
                raise ValueError("a succeeded Result needs person_count and detections")
            if self.error is not None:
                raise ValueError("a succeeded Result has no error")
            if self.person_count != len(self.detections):
                raise ValueError("person_count must equal the number of detections")
        else:
            if self.error is None:
                raise ValueError("a failed Result needs an error")
            if self.person_count is not None or self.detections is not None:
                raise ValueError("a failed Result has no person_count or detections")
        return self
