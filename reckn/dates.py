"""Date, calendar, and clock time support for Reckn."""

import re
import locale
import calendar
from datetime import date, timedelta, datetime
from typing import Optional, Callable, Union
from dataclasses import dataclass


# Month name mappings (case-insensitive lookup)
MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# Full month names for formatting (1-indexed)
MONTH_DISPLAY = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

DATE_KEYWORDS = {"today", "yesterday", "tomorrow", "now"}


@dataclass
class DateInterval:
    """A calendar-aware duration (months/years are variable length)."""
    years: int = 0
    months: int = 0
    days: int = 0

    def __neg__(self) -> "DateInterval":
        return DateInterval(-self.years, -self.months, -self.days)

    def __add__(self, other: object) -> "DateInterval":
        if isinstance(other, DateInterval):
            return DateInterval(
                self.years + other.years,
                self.months + other.months,
                self.days + other.days,
            )
        return NotImplemented

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DateInterval):
            return (self.years == other.years and
                    self.months == other.months and
                    self.days == other.days)
        return NotImplemented

    def __repr__(self) -> str:
        parts = []
        if self.years:
            parts.append(f"{self.years}y")
        if self.months:
            parts.append(f"{self.months}m")
        if self.days:
            parts.append(f"{self.days}d")
        return f"DateInterval({' '.join(parts) if parts else '0d'})"


@dataclass
class DateResult:
    """Result of a date expression pre-parser."""
    value: Union[date, DateInterval]
    is_date: bool = True  # True for date, False for interval


def is_date_reserved_word(name: str) -> bool:
    """Check if a name is a date-related reserved word (keyword or month name)."""
    lower = name.lower()
    return lower in DATE_KEYWORDS or lower in MONTH_NAMES


def resolve_date_keyword(keyword: str) -> date:
    """Resolve today/yesterday/tomorrow/now to a date."""
    today = date.today()
    kw = keyword.lower()
    if kw in ("today", "now"):
        return today
    elif kw == "yesterday":
        return today - timedelta(days=1)
    elif kw == "tomorrow":
        return today + timedelta(days=1)
    raise ValueError(f"Unknown date keyword: {keyword}")


def parse_date_literal(text: str) -> Optional[date]:
    """
    Parse a date literal string into a date object.

    Supported formats:
    - ISO: 2025-06-12
    - Month-first: June 12, June 12, 2025
    - Day-first: 12 June, 12 June 2025
    - Numeric: 12/06/2025 (locale-aware)
    - Keywords: today, yesterday, tomorrow, now
    """
    text = text.strip()
    if not text:
        return None

    # Date keywords
    if text.lower() in DATE_KEYWORDS:
        return resolve_date_keyword(text)

    # ISO format: 2025-06-12
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    # "June 12" or "June 12, 2025"
    m = re.match(r'^([A-Za-z]+)\s+(\d{1,2})(?:\s*,\s*(\d{4}))?$', text)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        if month:
            day = int(m.group(2))
            year = int(m.group(3)) if m.group(3) else _infer_year(month, day)
            try:
                return date(year, month, day)
            except ValueError:
                return None

    # "12 June" or "12 June 2025"
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]+)(?:\s+(\d{4}))?$', text)
    if m:
        month = MONTH_NAMES.get(m.group(2).lower())
        if month:
            day = int(m.group(1))
            year = int(m.group(3)) if m.group(3) else _infer_year(month, day)
            try:
                return date(year, month, day)
            except ValueError:
                return None

    # Numeric: DD/MM/YYYY or MM/DD/YYYY (locale-dependent)
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', text)
    if m:
        return _parse_numeric_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    return None


def _infer_year(month: int, day: int) -> int:
    """When no year given, pick next occurrence of month/day."""
    today = date.today()
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        # Invalid date like Feb 30 — try next year in case it's a leap year issue
        try:
            candidate = date(today.year + 1, month, day)
            return candidate.year
        except ValueError:
            return today.year
    # If the date is more than 6 months in the past, assume next year
    if (today - candidate).days > 180:
        return today.year + 1
    return candidate.year


def _parse_numeric_date(a: int, b: int, year: int) -> Optional[date]:
    """Parse ambiguous numeric date using locale."""
    # Try to detect locale preference
    try:
        loc = locale.getlocale(locale.LC_TIME)
        # US locale uses MM/DD
        if loc and loc[0] and loc[0].startswith("en_US"):
            month, day = a, b
        else:
            # International: DD/MM
            day, month = a, b
    except Exception:
        # Default to DD/MM
        day, month = a, b

    try:
        return date(year, month, day)
    except ValueError:
        # Try the other interpretation
        try:
            return date(year, a, b)
        except ValueError:
            return None


def add_interval_to_date(d: date, interval: DateInterval) -> date:
    """Add a DateInterval to a date, handling month/year rollover."""
    # Add years and months first
    new_year = d.year + interval.years
    new_month = d.month + interval.months

    # Normalize month overflow/underflow
    while new_month > 12:
        new_month -= 12
        new_year += 1
    while new_month < 1:
        new_month += 12
        new_year -= 1

    # Clamp day to valid range for new month
    max_day = calendar.monthrange(new_year, new_month)[1]
    new_day = min(d.day, max_day)

    result = date(new_year, new_month, new_day)

    # Then add days
    if interval.days:
        result += timedelta(days=interval.days)

    return result


def date_difference(d1: date, d2: date) -> DateInterval:
    """
    Compute the interval between two dates.
    Returns a positive interval representing the distance between d1 and d2.
    """
    # Ensure d1 <= d2 for calculation
    if d1 > d2:
        d1, d2 = d2, d1

    years = 0
    months = 0

    # Count full years
    temp = d1
    while True:
        try:
            next_year = temp.replace(year=temp.year + 1)
        except ValueError:
            # Feb 29 → Feb 28
            next_year = temp.replace(year=temp.year + 1, day=28)
        if next_year <= d2:
            years += 1
            temp = next_year
        else:
            break

    # Count full months from temp
    while True:
        next_month_num = temp.month + 1
        next_year_num = temp.year
        if next_month_num > 12:
            next_month_num = 1
            next_year_num += 1
        max_day = calendar.monthrange(next_year_num, next_month_num)[1]
        try:
            next_month = date(next_year_num, next_month_num, min(temp.day, max_day))
        except ValueError:
            break
        if next_month <= d2:
            months += 1
            temp = next_month
        else:
            break

    remaining_days = (d2 - temp).days

    return DateInterval(years=years, months=months, days=remaining_days)


def format_date(d: date) -> str:
    """Format a date for display: '12 June 2025'."""
    return f"{d.day} {MONTH_DISPLAY[d.month]} {d.year}"


def format_interval(interval: DateInterval) -> str:
    """
    Format an interval for human-readable display.

    Rules:
    - If interval has years or months, show as "X years Y months Z days"
    - If interval is days only and >= 7, show as "X weeks Y days"
    - Otherwise show as "X days"
    - Omit zero components (except always show at least one)
    """
    years = abs(interval.years)
    months = abs(interval.months)
    days = abs(interval.days)

    # Has years or months — show full breakdown
    if years or months:
        parts = []
        if years:
            parts.append(f"{years} year{'s' if years != 1 else ''}")
        if months:
            parts.append(f"{months} month{'s' if months != 1 else ''}")
        if days:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if not parts:
            parts.append("0 days")
        return " ".join(parts)

    # Days only — use weeks + days if >= 7
    if days >= 7:
        weeks = days // 7
        remaining = days % 7
        if remaining:
            return f"{weeks} week{'s' if weeks != 1 else ''} {remaining} day{'s' if remaining != 1 else ''}"
        return f"{weeks} week{'s' if weeks != 1 else ''}"

    return f"{days} day{'s' if days != 1 else ''}"


def parse_duration_spec(text: str) -> Optional[DateInterval]:
    """
    Parse compound duration like '3 months 5 days' or '2 weeks'.
    Returns DateInterval or None if no duration units found.
    """
    text = text.strip().lower()
    interval = DateInterval()
    found = False

    for m in re.finditer(r'(\d+)\s*(years?|months?|weeks?|days?)', text):
        n = int(m.group(1))
        unit = m.group(2).rstrip('s')  # normalize to singular
        if unit == "year":
            interval.years += n
        elif unit == "month":
            interval.months += n
        elif unit == "week":
            interval.days += n * 7
        elif unit == "day":
            interval.days += n
        found = True

    return interval if found else None


def _resolve_date_or_var(text: str, resolve_var: Optional[Callable]) -> Optional[date]:
    """
    Try to parse text as a date literal, then as a variable holding a date.

    Args:
        text: The text to parse
        resolve_var: Function that resolves variable names to Value objects
    """
    text = text.strip()

    # Try as date literal
    d = parse_date_literal(text)
    if d is not None:
        return d

    # Try as variable
    if resolve_var is not None:
        val = resolve_var(text)
        if val is not None and hasattr(val, 'value') and isinstance(val.value, date):
            return val.value

    return None


def try_parse_date_expression(
    expression: str,
    resolve_var: Optional[Callable] = None,
) -> Optional[DateResult]:
    """
    Try to parse a date/calendar expression.
    Called before the main evaluator, like percentages.

    Patterns handled:
    - "from <date> to <date>" → interval
    - "<duration> from now" / "<duration> from today" → date
    - "<duration> after <date>" → date
    - "<duration> before <date>" → date
    - Standalone date literals: "June 12", "March 14, 2025", etc.

    Args:
        expression: The expression string to parse
        resolve_var: Function to resolve variable names to Value objects

    Returns:
        DateResult if this is a date expression, None otherwise
    """
    expr = expression.strip()
    if not expr:
        return None

    # Pattern: "from <date> to <date>"
    result = _try_from_to(expr, resolve_var)
    if result is not None:
        return result

    # Pattern: "<duration> from now" / "<duration> from <date>"
    result = _try_duration_from(expr, resolve_var)
    if result is not None:
        return result

    # Pattern: "<duration> after <date>"
    result = _try_duration_after(expr, resolve_var)
    if result is not None:
        return result

    # Pattern: "<duration> before <date>"
    result = _try_duration_before(expr, resolve_var)
    if result is not None:
        return result

    # Pattern: "<date> +/- <duration>" (e.g., "June 12 + 3 months 5 days")
    result = _try_date_plus_duration(expr, resolve_var)
    if result is not None:
        return result

    # Standalone date literal
    # First try as-is (handles ISO dates like 2025-06-12 which contain hyphens)
    d = parse_date_literal(expr)
    if d is not None:
        return DateResult(value=d, is_date=True)

    # Try variable-held dates (only if no operators present)
    if not re.search(r'[+\-*/^=]', expr):
        d = _resolve_date_or_var(expr, resolve_var)
        if d is not None:
            return DateResult(value=d, is_date=True)

    return None


def _try_from_to(expr: str, resolve_var: Optional[Callable]) -> Optional[DateResult]:
    """Parse: from March 12 to July 30 → interval."""
    m = re.match(r'^from\s+(.+?)\s+to\s+(.+)$', expr, re.IGNORECASE)
    if m:
        d1 = _resolve_date_or_var(m.group(1).strip(), resolve_var)
        d2 = _resolve_date_or_var(m.group(2).strip(), resolve_var)
        if d1 is not None and d2 is not None:
            interval = date_difference(d1, d2)
            return DateResult(value=interval, is_date=False)
    return None


def _try_duration_from(expr: str, resolve_var: Optional[Callable]) -> Optional[DateResult]:
    """Parse: 4 days from now → date, 3 weeks from today → date."""
    m = re.match(r'^(.+?)\s+from\s+(.+)$', expr, re.IGNORECASE)
    if m:
        interval = parse_duration_spec(m.group(1).strip())
        base = _resolve_date_or_var(m.group(2).strip(), resolve_var)
        if interval is not None and base is not None:
            result = add_interval_to_date(base, interval)
            return DateResult(value=result, is_date=True)
    return None


def _try_duration_after(expr: str, resolve_var: Optional[Callable]) -> Optional[DateResult]:
    """Parse: 3 weeks after March 14 → date."""
    m = re.match(r'^(.+?)\s+after\s+(.+)$', expr, re.IGNORECASE)
    if m:
        interval = parse_duration_spec(m.group(1).strip())
        base = _resolve_date_or_var(m.group(2).strip(), resolve_var)
        if interval is not None and base is not None:
            result = add_interval_to_date(base, interval)
            return DateResult(value=result, is_date=True)
    return None


def _try_date_plus_duration(expr: str, resolve_var: Optional[Callable]) -> Optional[DateResult]:
    """Parse: June 12 + 3 months 5 days, January 31 + 1 month, today - 2 weeks."""
    # Split on + or - (but not hyphens inside dates like 2025-06-12)
    m = re.match(r'^(.+?)\s*([+-])\s*(\d+\s+(?:years?|months?|weeks?|days?).*)$', expr, re.IGNORECASE)
    if m:
        date_part = m.group(1).strip()
        op = m.group(2)
        duration_part = m.group(3).strip()

        base = _resolve_date_or_var(date_part, resolve_var)
        interval = parse_duration_spec(duration_part)
        if base is not None and interval is not None:
            if op == '-':
                interval = -interval
            result = add_interval_to_date(base, interval)
            return DateResult(value=result, is_date=True)
    return None


def _try_duration_before(expr: str, resolve_var: Optional[Callable]) -> Optional[DateResult]:
    """Parse: 28 days before March 12 → date."""
    m = re.match(r'^(.+?)\s+before\s+(.+)$', expr, re.IGNORECASE)
    if m:
        interval = parse_duration_spec(m.group(1).strip())
        base = _resolve_date_or_var(m.group(2).strip(), resolve_var)
        if interval is not None and base is not None:
            result = add_interval_to_date(base, -interval)
            return DateResult(value=result, is_date=True)
    return None


# ---------------------------------------------------------------------------
# Clock Time Support
# ---------------------------------------------------------------------------

@dataclass
class ClockTime:
    """A time of day (0:00 to 23:59)."""
    hour: int   # 0-23
    minute: int  # 0-59

    def total_minutes(self) -> int:
        """Total minutes since midnight."""
        return self.hour * 60 + self.minute

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ClockTime):
            return self.hour == other.hour and self.minute == other.minute
        return NotImplemented

    def __repr__(self) -> str:
        return f"ClockTime({self.hour}:{self.minute:02d})"


@dataclass
class ClockTimeResult:
    """Result of a clock time expression pre-parser."""
    value: object  # ClockTime or float (seconds, for timespan)
    result_type: str  # "clock_time" or "timespan"


def resolve_now_time() -> ClockTime:
    """Resolve 'now' to the current time of day."""
    n = datetime.now()
    return ClockTime(hour=n.hour, minute=n.minute)


def parse_clock_time(text: str) -> Optional[ClockTime]:
    """
    Parse a clock time literal.

    Formats:
    - 7:45am, 7:45 am, 7:45AM
    - 3:35pm, 3:35 pm, 3:35PM
    - 15:35 (24-hour)
    - now (current time)
    """
    text = text.strip()

    if text.lower() == "now":
        return resolve_now_time()

    # 12-hour format: 7:45am, 7:45 am, 12:00pm
    m = re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)$', text, re.IGNORECASE)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        period = m.group(3).lower()
        if hour < 1 or hour > 12 or minute > 59:
            return None
        if period == "am":
            if hour == 12:
                hour = 0
        else:  # pm
            if hour != 12:
                hour += 12
        return ClockTime(hour=hour, minute=minute)

    # 24-hour format: 15:35, 0:00, 23:59
    m = re.match(r'^(\d{1,2}):(\d{2})$', text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if hour > 23 or minute > 59:
            return None
        return ClockTime(hour=hour, minute=minute)

    return None


def format_clock_time(ct: ClockTime) -> str:
    """Format a clock time for display: '7:45 am', '3:35 pm'."""
    if ct.hour == 0:
        return f"12:{ct.minute:02d} am"
    elif ct.hour < 12:
        return f"{ct.hour}:{ct.minute:02d} am"
    elif ct.hour == 12:
        return f"12:{ct.minute:02d} pm"
    else:
        return f"{ct.hour - 12}:{ct.minute:02d} pm"


def clock_time_add_minutes(ct: ClockTime, minutes: int) -> ClockTime:
    """Add (or subtract) minutes to a clock time, wrapping around 24 hours."""
    total = (ct.total_minutes() + minutes) % (24 * 60)
    if total < 0:
        total += 24 * 60
    return ClockTime(hour=total // 60, minute=total % 60)


def clock_time_difference(ct1: ClockTime, ct2: ClockTime) -> int:
    """
    Compute the difference in minutes: ct1 - ct2.
    Returns a positive value (absolute difference).
    """
    diff = ct1.total_minutes() - ct2.total_minutes()
    return abs(diff)


def format_timespan(total_seconds: float) -> str:
    """
    Format a duration in seconds as a human-readable timespan.

    Examples:
    - 19800 → "5 hr 30 min"
    - 5400 → "1 hr 30 min"
    - 302400 → "3 days 12 hr"
    - 90 → "1 min 30 sec"
    """
    total_seconds = abs(total_seconds)

    days = int(total_seconds // 86400)
    remaining = total_seconds % 86400
    hours = int(remaining // 3600)
    remaining = remaining % 3600
    minutes = int(remaining // 60)
    seconds = int(remaining % 60)

    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hr")
    if minutes:
        parts.append(f"{minutes} min")
    if seconds and not days and not hours:
        # Only show seconds if no larger units
        parts.append(f"{seconds} sec")
    if not parts:
        parts.append("0 min")

    return " ".join(parts)


def _parse_time_duration_minutes(text: str) -> Optional[int]:
    """Parse a duration spec that uses hours and/or minutes. Returns total minutes."""
    text = text.strip().lower()
    total = 0
    found = False

    for m in re.finditer(r'(\d+)\s*(hours?|hr|minutes?|min)', text):
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("hour") or unit == "hr":
            total += n * 60
        elif unit.startswith("min"):
            total += n
        found = True

    return total if found else None


def _resolve_clock_time_or_var(text: str, resolve_var: Optional[Callable]) -> Optional[ClockTime]:
    """Try to parse text as a clock time literal, then as a variable holding a clock time."""
    text = text.strip()

    ct = parse_clock_time(text)
    if ct is not None:
        return ct

    if resolve_var is not None:
        val = resolve_var(text)
        if val is not None and hasattr(val, 'value') and isinstance(val.value, ClockTime):
            return val.value

    return None


def try_parse_clock_time_expression(
    expression: str,
    resolve_var: Optional[Callable] = None,
) -> Optional[ClockTimeResult]:
    """
    Try to parse a clock time expression.
    Called before the date pre-parser.

    Patterns handled:
    - Standalone clock time: "7:45am", "15:35", "now"
    - Clock time +/- duration: "7:45am + 9 hours 20 minutes"
    - Clock time - clock time: "3:35pm - 11:00am"
    - "X hours/minutes as timespan"

    Returns:
        ClockTimeResult if matched, None otherwise
    """
    expr = expression.strip()
    if not expr:
        return None

    # Pattern: "<value> as timespan" (e.g., "5.5 hours as timespan")
    result = _try_as_timespan(expr, resolve_var)
    if result is not None:
        return result

    # Pattern: "<time> +/- <hours/minutes duration>"
    result = _try_time_plus_duration(expr, resolve_var)
    if result is not None:
        return result

    # Pattern: "<time> - <time>" (time difference)
    result = _try_time_minus_time(expr, resolve_var)
    if result is not None:
        return result

    # Standalone clock time (only if no operators present, except inside the time itself)
    if not re.search(r'[+\-*/^=]', expr):
        ct = _resolve_clock_time_or_var(expr, resolve_var)
        if ct is not None:
            return ClockTimeResult(value=ct, result_type="clock_time")

    return None


def _try_time_plus_duration(expr: str, resolve_var: Optional[Callable]) -> Optional[ClockTimeResult]:
    """Parse: 7:45am + 9 hours 20 minutes, now + 2 hours."""
    m = re.match(r'^(.+?)\s*([+-])\s*(\d+\s+(?:hours?|hr|minutes?|min).*)$', expr, re.IGNORECASE)
    if m:
        time_part = m.group(1).strip()
        op = m.group(2)
        duration_part = m.group(3).strip()

        ct = _resolve_clock_time_or_var(time_part, resolve_var)
        minutes = _parse_time_duration_minutes(duration_part)
        if ct is not None and minutes is not None:
            if op == '-':
                minutes = -minutes
            result = clock_time_add_minutes(ct, minutes)
            return ClockTimeResult(value=result, result_type="clock_time")
    return None


def _try_time_minus_time(expr: str, resolve_var: Optional[Callable]) -> Optional[ClockTimeResult]:
    """Parse: 3:35pm - 11:00am → duration in seconds."""
    m = re.match(r'^(.+?)\s*-\s*(.+)$', expr)
    if m:
        left_text = m.group(1).strip()
        right_text = m.group(2).strip()

        left = _resolve_clock_time_or_var(left_text, resolve_var)
        right = _resolve_clock_time_or_var(right_text, resolve_var)
        if left is not None and right is not None:
            diff_minutes = clock_time_difference(left, right)
            # Return as total seconds for timespan formatting
            return ClockTimeResult(value=float(diff_minutes * 60), result_type="timespan")
    return None


def _try_as_timespan(expr: str, resolve_var: Optional[Callable]) -> Optional[ClockTimeResult]:
    """Parse: 5.5 hours as timespan, 90 minutes as timespan."""
    m = re.match(r'^(.+?)\s+as\s+timespan$', expr, re.IGNORECASE)
    if m:
        value_part = m.group(1).strip()

        # Try to parse as "<number> <time_unit>"
        vm = re.match(r'^([\d.]+)\s*(hours?|hr|minutes?|min|seconds?|sec|days?|weeks?)$',
                       value_part, re.IGNORECASE)
        if vm:
            num = float(vm.group(1))
            unit = vm.group(2).lower()

            # Convert to seconds
            if unit.startswith("hour") or unit == "hr":
                total_seconds = num * 3600
            elif unit.startswith("min"):
                total_seconds = num * 60
            elif unit.startswith("sec"):
                total_seconds = num
            elif unit.startswith("day"):
                total_seconds = num * 86400
            elif unit.startswith("week"):
                total_seconds = num * 604800
            else:
                return None

            return ClockTimeResult(value=total_seconds, result_type="timespan")

        # Try as a plain number variable with time unit
        # e.g., "varname as timespan" where var holds a time-unit value
        if resolve_var is not None:
            val = resolve_var(value_part)
            if val is not None and hasattr(val, 'value') and hasattr(val, 'unit'):
                if val.unit and val.unit.category == "time":
                    # Convert to seconds using the unit
                    canonical = val.unit.canonical
                    multipliers = {
                        "s": 1, "min": 60, "hr": 3600,
                        "day": 86400, "week": 604800,
                        "month": 2629746, "year": 31556952,
                    }
                    mult = multipliers.get(canonical)
                    if mult:
                        return ClockTimeResult(value=float(val.value * mult), result_type="timespan")
                elif isinstance(val.value, (int, float)) and val.unit is None:
                    # Plain number — treat as seconds
                    return ClockTimeResult(value=float(val.value), result_type="timespan")
    return None
