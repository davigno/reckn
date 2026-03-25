"""Value and Unit types for carrying unit metadata through evaluation."""

from dataclasses import dataclass
from datetime import date as Date
from typing import Optional, Tuple, Union


@dataclass(frozen=True)
class Unit:
    """Immutable unit representation, supporting simple and compound units."""

    numerator: Tuple[str, ...]    # e.g., ("km",) or ("MB",)
    denominator: Tuple[str, ...]  # e.g., () or ("s",) for rates
    category: Optional[str] = None  # "length", "time", "currency", etc.
    iso_code: Optional[str] = None  # For currencies: "USD", "EUR", etc.

    @classmethod
    def simple(cls, name: str, category: Optional[str] = None) -> "Unit":
        """Create a simple unit like 'km' or 'USD'."""
        return cls(numerator=(name,), denominator=(), category=category)

    @classmethod
    def currency(cls, iso_code: str) -> "Unit":
        """Create a currency unit."""
        return cls(
            numerator=(iso_code,),
            denominator=(),
            category="currency",
            iso_code=iso_code
        )

    @classmethod
    def rate(cls, num_unit: str, denom_unit: str,
             num_category: Optional[str] = None) -> "Unit":
        """Create a rate unit like 'km/h' or 'MB/s'."""
        return cls(
            numerator=(num_unit,),
            denominator=(denom_unit,),
            category=num_category
        )

    @property
    def is_currency(self) -> bool:
        """Check if this is a currency unit."""
        return self.category == "currency"

    @property
    def is_rate(self) -> bool:
        """Check if this is a rate (has denominator)."""
        return len(self.denominator) > 0

    @property
    def is_dimensionless(self) -> bool:
        """Check if this unit has been cancelled out."""
        return not self.numerator and not self.denominator

    @property
    def canonical(self) -> str:
        """Get the canonical string representation."""
        if self.is_dimensionless:
            return ""
        if not self.numerator:
            num = "1"
        elif len(self.numerator) == 1:
            num = self.numerator[0]
        else:
            num = "*".join(self.numerator)

        if self.denominator:
            if len(self.denominator) == 1:
                return f"{num}/{self.denominator[0]}"
            return f"{num}/{'/'.join(self.denominator)}"
        return num

    def __str__(self) -> str:
        return self.canonical

    def __mul__(self, other: "Unit") -> "Unit":
        """Combine units via multiplication: km * km → km*km"""
        return Unit(
            numerator=self.numerator + other.numerator,
            denominator=self.denominator + other.denominator
        )

    def __truediv__(self, other: "Unit") -> "Unit":
        """Divide units: km / h → km/h"""
        return Unit(
            numerator=self.numerator + other.denominator,
            denominator=self.denominator + other.numerator
        )

    def simplify(self) -> "Unit":
        """Cancel matching units: km/km → dimensionless, km²/km → km."""
        from collections import Counter
        num_counts = Counter(self.numerator)
        denom_counts = Counter(self.denominator)

        # Cancel common units
        for unit in list(num_counts.keys()):
            if unit in denom_counts:
                common = min(num_counts[unit], denom_counts[unit])
                num_counts[unit] -= common
                denom_counts[unit] -= common

        # Rebuild tuples, removing zeros
        num = tuple(u for u, c in num_counts.items() for _ in range(c) if c > 0)
        denom = tuple(u for u, c in denom_counts.items() for _ in range(c) if c > 0)

        if not num and not denom:
            return Unit((), ())
        return Unit(
            num,
            denom,
            category=self.category if num else None,
            iso_code=self.iso_code if num else None
        )

    def with_category(self, category: str) -> "Unit":
        """Return a copy with the specified category."""
        return Unit(
            self.numerator,
            self.denominator,
            category=category,
            iso_code=self.iso_code
        )


@dataclass
class Value:
    """A value with optional unit metadata. Supports floats, dates, date intervals, and clock times."""

    value: Union[float, Date, "DateInterval", "ClockTime"]
    unit: Optional[Unit] = None

    @classmethod
    def plain(cls, value: float) -> "Value":
        """Create a plain dimensionless value."""
        return cls(value=value, unit=None)

    @classmethod
    def with_unit(cls, value: float, unit_name: str,
                  category: Optional[str] = None) -> "Value":
        """Create a value with a simple unit."""
        return cls(value=value, unit=Unit.simple(unit_name, category))

    @classmethod
    def with_currency(cls, value: float, iso_code: str) -> "Value":
        """Create a currency value."""
        return cls(value=value, unit=Unit.currency(iso_code))

    @classmethod
    def date(cls, d: Date) -> "Value":
        """Create a date value."""
        return cls(value=d, unit=Unit.simple("date", "date"))

    @classmethod
    def interval(cls, iv: "DateInterval") -> "Value":
        """Create a date interval value."""
        return cls(value=iv, unit=Unit.simple("interval", "date_interval"))

    @classmethod
    def clock_time(cls, ct: "ClockTime") -> "Value":
        """Create a clock time value."""
        return cls(value=ct, unit=Unit.simple("time", "clock_time"))

    @classmethod
    def timespan(cls, total_seconds: float) -> "Value":
        """Create a timespan display value (duration in seconds)."""
        return cls(value=total_seconds, unit=Unit.simple("timespan", "timespan"))

    @classmethod
    def loading(cls) -> "Value":
        """Create a loading placeholder value (for async currency fetch)."""
        return cls(value=0.0, unit=Unit.simple("loading", "loading"))

    @property
    def is_plain(self) -> bool:
        """Check if this value has no unit and is a number."""
        return self.unit is None and isinstance(self.value, (int, float))

    @property
    def is_currency(self) -> bool:
        """Check if this is a currency value."""
        return self.unit is not None and self.unit.is_currency

    @property
    def is_date(self) -> bool:
        """Check if this is a date value."""
        return isinstance(self.value, Date)

    @property
    def is_interval(self) -> bool:
        """Check if this is a date interval value."""
        # Lazy import to avoid circular dependency
        from datetime import date as _Date
        if isinstance(self.value, _Date):
            return False
        return hasattr(self.value, 'years') and hasattr(self.value, 'months')

    @property
    def is_clock_time(self) -> bool:
        """Check if this is a clock time value."""
        return self.unit is not None and self.unit.category == "clock_time"

    @property
    def is_timespan(self) -> bool:
        """Check if this is a timespan display value."""
        return self.unit is not None and self.unit.category == "timespan"

    @property
    def is_loading(self) -> bool:
        """Check if this is a loading placeholder."""
        return self.unit is not None and self.unit.category == "loading"

    def __repr__(self) -> str:
        if self.unit:
            return f"Value({self.value}, {self.unit})"
        return f"Value({self.value})"
