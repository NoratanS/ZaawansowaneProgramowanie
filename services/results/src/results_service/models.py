from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    HttpUrl,
    StrictInt,
    model_validator,
)

ErrorCode = Literal["image_unreachable", "not_an_image", "image_too_large"]


class Detection(BaseModel):
    """One person's box, in integer pixels of the original image."""

    x: Annotated[StrictInt, Field(ge=0)]
    y: Annotated[StrictInt, Field(ge=0)]
    width: Annotated[StrictInt, Field(ge=1)]
    height: Annotated[StrictInt, Field(ge=1)]
    confidence: Annotated[float, Field(ge=0, le=1)]


class ResultError(BaseModel):
    code: ErrorCode
    message: str


class AnalysisResult(BaseModel):
    """The outcome of one Analysis Job, as the Results Service stores it."""

    job_id: UUID
    image_url: HttpUrl
    status: Literal["succeeded", "failed"]
    person_count: Annotated[StrictInt, Field(ge=0)] | None
    detections: list[Detection] | None
    error: ResultError | None
    model: str
    requested_at: AwareDatetime
    analyzed_at: AwareDatetime

    @model_validator(mode="after")
    def check_shape(self) -> Self:
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
