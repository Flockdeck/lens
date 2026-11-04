"""Date-range query parameters: a bare date covers whole UTC days, a datetime is exact."""

from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute

RANGE_DOC = (
    "`from` and `to` accept an ISO date or datetime (UTC when no offset is given). A bare "
    "`from=YYYY-MM-DD` starts at 00:00 UTC that day and a bare `to=YYYY-MM-DD` includes that whole "
    "UTC day; a datetime bound is exact (`from` inclusive, `to` inclusive)."
)


def _parse(value: str, name: str) -> tuple[datetime, bool]:
    """Return (naive UTC instant, was_date_only)."""
    try:
        try:
            # Any date form `date.fromisoformat` takes, including 20260101, is a whole day.
            return datetime.combine(date.fromisoformat(value), datetime.min.time()), True
        except ValueError:
            pass
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    except (ValueError, OverflowError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"invalid `{name}`: expected ISO date or datetime",
        ) from exc
    return parsed, False


def range_conditions(
    column: "InstrumentedAttribute[datetime | None] | ColumnElement[datetime]",
    from_: str | None,
    to: str | None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if from_ is not None:
        conditions.append(column >= _parse(from_, "from")[0])
    if to is not None:
        end, date_only = _parse(to, "to")
        if date_only:
            try:
                end += timedelta(days=1)
            except OverflowError:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid `to`: date out of range"
                ) from None
        conditions.append(column < end if date_only else column <= end)
    return conditions
