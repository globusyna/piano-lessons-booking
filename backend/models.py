from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True, extra="forbid")


class StudentStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    FLAGGED = "flagged"


class LessonStatus(StrEnum):
    SCHEDULED = "scheduled"
    DONE = "done"


Weekday = Annotated[int, Field(ge=1, le=5)]
LocalTime = Annotated[str, StringConstraints(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]


class Package(ApiModel):
    id: int | None = None
    size: Literal[5, 8, 10]
    used: int = Field(ge=0)
    period_no: int = Field(alias="periodNo", ge=1)


class Student(ApiModel):
    id: int
    name: str
    status: StudentStatus
    token: str
    slot_day: Weekday = Field(alias="slotDay")
    slot_time: LocalTime = Field(alias="slotTime")
    pkg: Package
    invoice_sent: bool = Field(alias="invoiceSent")


class StudentSummary(ApiModel):
    id: int
    name: str
    status: StudentStatus


class Lesson(ApiModel):
    id: int
    seq: int = Field(ge=1)
    student_id: int = Field(alias="studentId")
    starts_at: datetime = Field(alias="startsAt")
    status: LessonStatus


class StudentLesson(ApiModel):
    id: int
    seq: int
    starts_at: datetime = Field(alias="startsAt")
    status: LessonStatus
    can_move: bool = Field(alias="canMove")


class StudentView(ApiModel):
    student: StudentSummary
    package: Package
    next_lesson: StudentLesson | None = Field(alias="nextLesson")
    lessons: list[StudentLesson]
    can_request_pause: bool = Field(alias="canRequestPause")


class Blackout(ApiModel):
    id: int
    starts_at: datetime = Field(alias="startsAt")
    note: str


class OpenSlot(ApiModel):
    starts_at: datetime = Field(alias="startsAt")


class RescheduleRequest(ApiModel):
    starts_at: datetime = Field(alias="startsAt")

    @field_validator("starts_at")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("startsAt must include a UTC offset")
        return value


class AvailabilityRequest(ApiModel):
    day: Weekday
    times: list[LocalTime]

    @field_validator("times")
    @classmethod
    def unique_times(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("times must be unique")
        return sorted(value)


class BlackoutRequest(ApiModel):
    starts_at: datetime = Field(alias="startsAt")
    note: str = Field(min_length=1)


class StudentCreate(ApiModel):
    name: str = Field(min_length=1)
    slot_day: Weekday = Field(alias="slotDay")
    slot_time: LocalTime = Field(alias="slotTime")


class StudentSlotRequest(ApiModel):
    slot_day: Weekday = Field(alias="slotDay")
    slot_time: LocalTime = Field(alias="slotTime")


class PackageRequest(ApiModel):
    size: Literal[5, 8, 10]


class StatusRequest(ApiModel):
    status: StudentStatus


class LoginRequest(ApiModel):
    username: str
    password: str


class TokenResponse(ApiModel):
    access_token: str = Field(alias="accessToken")
    token_type: Literal["bearer"] = Field(default="bearer", alias="tokenType")
