from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

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
    """A package as it is read back: ``size`` is the running total it holds.

    Not `Literal[5, 8, 10]` -- renewing tops a package up in place, so any total
    from 1 upward can be read back. `PackageRequest` below is what keeps the
    purchasable sizes to 5, 8 and 10.
    """

    id: int | None = None
    size: int = Field(ge=1)
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
    paused_until: date | None = Field(default=None, alias="pausedUntil")


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
    """One upcoming lesson as the student sees it.

    A *pending* move request is still reported through `requested_starts_at`
    alone, exactly as before -- "pending" was always representable. The two
    fields below are only for a request that has been answered: `declined` with
    an optional reason, or `expired`. In that case `requested_starts_at` stays
    `None`, because a resolved request has no live requested time left to show.
    """

    id: int
    seq: int
    starts_at: datetime = Field(alias="startsAt")
    status: LessonStatus
    can_move: bool = Field(alias="canMove")
    requested_starts_at: datetime | None = Field(default=None, alias="requestedStartsAt")
    move_request_status: Literal["declined", "expired"] | None = Field(
        default=None, alias="moveRequestStatus"
    )
    decline_reason: str | None = Field(default=None, alias="declineReason")


class MoveRequestStatus(StrEnum):
    """How a move request ended, or that it has not.

    `PENDING` is the only status that blocks anything: it is what keeps a
    lesson's slot reserved, what the alerts queue lists, and what stops a
    second request for the same lesson. `DECLINED` and `EXPIRED` are history
    and must never be read as a block -- that mistake is what would leave a
    student unable to ever ask again (#10).
    """

    PENDING = "pending"
    DECLINED = "declined"
    EXPIRED = "expired"


class LessonMoveRequest(ApiModel):
    id: int
    lesson_id: int = Field(alias="lessonId")
    requested_starts_at: datetime = Field(alias="requestedStartsAt")
    status: Literal["pending", "declined", "expired"] = MoveRequestStatus.PENDING.value
    decline_reason: str | None = Field(default=None, alias="declineReason")
    resolved_at: datetime | None = Field(default=None, alias="resolvedAt")


class DeclineMoveRequestBody(ApiModel):
    """The body of a decline. Everything about it is optional.

    An absent body, `{}` and `{"reason": null}` all mean "no reason given", and
    so does a reason that is nothing but whitespace -- `reason_or_none` below
    is what the store stores, so an empty string never reaches the database
    pretending to be an explanation.
    """

    reason: str | None = Field(default=None, max_length=500)

    def reason_or_none(self) -> str | None:
        stripped = (self.reason or "").strip()
        return stripped or None


class StudentView(ApiModel):
    student: StudentSummary
    package: Package
    next_lesson: StudentLesson | None = Field(alias="nextLesson")
    lessons: list[StudentLesson]
    can_request_pause: bool = Field(alias="canRequestPause")
    paused_until: date | None = Field(default=None, alias="pausedUntil")


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
    """The body for both opening a package and renewing one.

    The sizes on the price list, and the only sizes either endpoint accepts.
    `Package.size` above is unconstrained because a renewal adds to the stored
    total; what can be *bought* in one go is still 5, 8 or 10.
    """

    size: Literal[5, 8, 10]


class StatusRequest(ApiModel):
    status: StudentStatus


class PauseRequest(ApiModel):
    """A break of 1-6 weeks.

    `weeks` is deliberately untyped here. The store checks it and raises the one
    named error the API promises, `INVALID_PAUSE_LENGTH`, so that 0, -2, 7 and
    "three" all answer the same way instead of splitting into a range error and
    a type error.
    """

    weeks: Any


class LoginRequest(ApiModel):
    username: str
    password: str


class TokenResponse(ApiModel):
    access_token: str = Field(alias="accessToken")
    token_type: Literal["bearer"] = Field(default="bearer", alias="tokenType")
