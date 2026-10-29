"""Validation helpers for recurring cluster job settings."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CRON_FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def timezone_error(timezone: object) -> str | None:
    if not isinstance(timezone, str):
        return f"Invalid timezone value: {timezone}; expected an IANA timezone name"
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return f"Invalid timezone value: {timezone}; expected an IANA timezone name"
    return None


def schedule_error(schedule: object) -> str | None:
    if not isinstance(schedule, str):
        return (
            f"Invalid schedule value: {schedule}; expected a five-field cron expression"
        )

    fields = schedule.split()
    if len(fields) != len(CRON_FIELD_RANGES):
        return (
            f"Invalid schedule value: {schedule}; expected a five-field cron expression"
        )

    for field, (minimum, maximum) in zip(fields, CRON_FIELD_RANGES):
        for part in field.split(","):
            match = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", part)
            if match is None:
                return (
                    f"Invalid schedule value: {schedule}; invalid cron field: {field}"
                )

            bounds = match.group(1)
            if bounds == "*":
                continue

            numbers = [int(value) for value in bounds.split("-")]
            if any(number < minimum or number > maximum for number in numbers):
                return (
                    f"Invalid schedule value: {schedule}; "
                    f"field {field} is outside {minimum}-{maximum}"
                )

            step = match.group(2)
            if step is not None and int(step) == 0:
                return (
                    f"Invalid schedule value: {schedule}; "
                    f"field {field} has a zero step"
                )
    return None
