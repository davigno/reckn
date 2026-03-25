"""Unit definitions and conversion logic for Reckn."""

import re
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, Callable, List


@dataclass
class UnitResult:
    """Result of a unit conversion."""
    value: float
    unit: str  # The target unit for display
    error: bool = False  # True if expression was recognized but invalid (e.g., incompatible units)


# Unit definitions:
# CASE_SENSITIVE_SYMBOLS: short symbols that are case-sensitive (e.g., km, MB, kg)
# CASE_INSENSITIVE_WORDS: full words that are case-insensitive (e.g., kilometer, megabyte)
# Both map to (category, base_value, canonical_symbol)

CASE_SENSITIVE_SYMBOLS: Dict[str, Tuple[str, float, str]] = {}
CASE_INSENSITIVE_WORDS: Dict[str, Tuple[str, float, str]] = {}


def _register_unit(category: str, base_value: float, symbol: str, *word_aliases: str) -> None:
    """
    Register a unit.

    Args:
        category: Unit category (e.g., 'length', 'weight', 'data_bytes')
        base_value: Multiplier to convert to base unit of category
        symbol: Case-sensitive short symbol (e.g., 'km', 'MB', 'kg')
        word_aliases: Case-insensitive full words (e.g., 'kilometer', 'megabyte')
    """
    CASE_SENSITIVE_SYMBOLS[symbol] = (category, base_value, symbol)
    for alias in word_aliases:
        CASE_INSENSITIVE_WORDS[alias.lower()] = (category, base_value, symbol)


# =============================================================================
# Data Storage - BYTES (uppercase B) - base unit: bytes
# =============================================================================
# Base-10 (SI) units - Note: KB uses uppercase K for kilo in computing context
_register_unit("data_bytes", 1, "B", "byte", "bytes")
_register_unit("data_bytes", 1e3, "KB", "kilobyte", "kilobytes")
_register_unit("data_bytes", 1e6, "MB", "megabyte", "megabytes")
_register_unit("data_bytes", 1e9, "GB", "gigabyte", "gigabytes")
_register_unit("data_bytes", 1e12, "TB", "terabyte", "terabytes")
_register_unit("data_bytes", 1e15, "PB", "petabyte", "petabytes")

# Base-2 (binary) units
_register_unit("data_bytes", 1024, "KiB", "kibibyte", "kibibytes")
_register_unit("data_bytes", 1024**2, "MiB", "mebibyte", "mebibytes")
_register_unit("data_bytes", 1024**3, "GiB", "gibibyte", "gibibytes")
_register_unit("data_bytes", 1024**4, "TiB", "tebibyte", "tebibytes")
_register_unit("data_bytes", 1024**5, "PiB", "pebibyte", "pebibytes")

# =============================================================================
# Data Storage - BITS (lowercase b) - base unit: bits
# =============================================================================
_register_unit("data_bits", 1, "b", "bit", "bits")
_register_unit("data_bits", 1e3, "Kb", "kilobit", "kilobits")
_register_unit("data_bits", 1e6, "Mb", "megabit", "megabits")
_register_unit("data_bits", 1e9, "Gb", "gigabit", "gigabits")
_register_unit("data_bits", 1e12, "Tb", "terabit", "terabits")

# =============================================================================
# Rate Units - Data rates
# =============================================================================
# Bits per second - note: kbps uses lowercase k (SI prefix)
_register_unit("rate_bits", 1, "bps")
_register_unit("rate_bits", 1e3, "kbps")  # lowercase k for SI kilo
_register_unit("rate_bits", 1e3, "Kbps")  # Also accept uppercase (common usage)
_register_unit("rate_bits", 1e6, "Mbps")
_register_unit("rate_bits", 1e9, "Gbps")
_register_unit("rate_bits", 1e12, "Tbps")

# Bytes per second (uppercase B)
_register_unit("rate_bytes", 1, "B/s", "Bps")
_register_unit("rate_bytes", 1e3, "KB/s", "KBps")
_register_unit("rate_bytes", 1e6, "MB/s", "MBps")
_register_unit("rate_bytes", 1e9, "GB/s", "GBps")
_register_unit("rate_bytes", 1e12, "TB/s", "TBps")

# =============================================================================
# Speed Units (base unit: meters per second)
# Symbol case: m/s, km/h (lowercase), mph (lowercase)
# =============================================================================
_register_unit("speed", 1, "m/s")
_register_unit("speed", 1000/3600, "km/h", "kph", "kmh")
_register_unit("speed", 1609.344/3600, "mph")
_register_unit("speed", 0.3048, "ft/s", "fps")
_register_unit("speed", 0.514444, "knot", "knots", "kn")

# =============================================================================
# Length (base unit: meters)
# Symbols are case-sensitive: mm, cm, m, km (all lowercase)
# =============================================================================
_register_unit("length", 0.001, "mm", "millimeter", "millimeters", "millimetre", "millimetres")
_register_unit("length", 0.01, "cm", "centimeter", "centimeters", "centimetre", "centimetres")
_register_unit("length", 1, "m", "meter", "meters", "metre", "metres")
_register_unit("length", 1000, "km", "kilometer", "kilometers", "kilometre", "kilometres")
_register_unit("length", 0.0254, "in", "inch", "inches")
_register_unit("length", 0.3048, "ft", "foot", "feet")
_register_unit("length", 0.9144, "yd", "yard", "yards")
_register_unit("length", 1609.344, "mi", "mile", "miles")

# =============================================================================
# Weight/Mass (base unit: grams)
# Symbols: mg, g, kg (all lowercase)
# =============================================================================
_register_unit("weight", 0.001, "mg", "milligram", "milligrams")
_register_unit("weight", 1, "g", "gram", "grams")
_register_unit("weight", 1000, "kg", "kilogram", "kilograms", "kilo", "kilos")
_register_unit("weight", 28.349523125, "oz", "ounce", "ounces")
_register_unit("weight", 453.59237, "lb", "lbs", "pound", "pounds")

# =============================================================================
# Time (base unit: seconds)
# Symbols: ms, s, min, hr (lowercase)
# =============================================================================
_register_unit("time", 0.001, "ms", "millisecond", "milliseconds")
_register_unit("time", 1, "s", "sec", "second", "seconds")
_register_unit("time", 60, "min", "minute", "minutes")
_register_unit("time", 3600, "hr", "hour", "hours")
_register_unit("time", 86400, "day", "days")
_register_unit("time", 604800, "week", "weeks")
_register_unit("time", 2629746, "month", "months")  # Average month (30.44 days)
_register_unit("time", 31556952, "year", "years")  # Average year (365.25 days)


# =============================================================================
# Temperature (special handling - not simple multiplication)
# K (uppercase) is case-sensitive for Kelvin
# C and F can be either case for convenience
# =============================================================================
# Case-sensitive temperature symbols
TEMP_SYMBOLS_CASE_SENSITIVE = {
    "K": "K",      # Kelvin - uppercase only (lowercase k is SI prefix for kilo)
    "C": "°C",     # Celsius
    "F": "°F",     # Fahrenheit
}

# Case-insensitive temperature words/aliases
TEMP_WORDS_CASE_INSENSITIVE = {
    "degc": "°C", "celsius": "°C", "°c": "°C",
    "degf": "°F", "fahrenheit": "°F", "°f": "°F",
    "degk": "K", "kelvin": "K",
}


def _get_temp_canonical(unit_str: str) -> Optional[str]:
    """Get canonical temperature unit, respecting case sensitivity."""
    # Check case-sensitive symbols first
    if unit_str in TEMP_SYMBOLS_CASE_SENSITIVE:
        return TEMP_SYMBOLS_CASE_SENSITIVE[unit_str]
    # Then case-insensitive words
    return TEMP_WORDS_CASE_INSENSITIVE.get(unit_str.lower())


def _celsius_to_fahrenheit(c: float) -> float:
    return (c * 9 / 5) + 32


def _fahrenheit_to_celsius(f: float) -> float:
    return (f - 32) * 5 / 9


def _celsius_to_kelvin(c: float) -> float:
    return c + 273.15


def _kelvin_to_celsius(k: float) -> float:
    return k - 273.15


def _convert_temperature(value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """Convert between temperature units."""
    from_canonical = _get_temp_canonical(from_unit)
    to_canonical = _get_temp_canonical(to_unit)

    if not from_canonical or not to_canonical:
        return None

    if from_canonical == to_canonical:
        return value

    # Convert to Celsius first, then to target
    if from_canonical == "°C":
        celsius = value
    elif from_canonical == "°F":
        celsius = _fahrenheit_to_celsius(value)
    elif from_canonical == "K":
        celsius = _kelvin_to_celsius(value)
    else:
        return None

    # Convert from Celsius to target
    if to_canonical == "°C":
        return celsius
    elif to_canonical == "°F":
        return _celsius_to_fahrenheit(celsius)
    elif to_canonical == "K":
        return _celsius_to_kelvin(celsius)

    return None


# =============================================================================
# Cross-category conversions (bits <-> bytes)
# =============================================================================

# Maps compatible categories for cross-conversion
COMPATIBLE_CATEGORIES = {
    ("rate_bits", "rate_bytes"): 8,  # 8 bits = 1 byte
    ("rate_bytes", "rate_bits"): 1/8,
    ("data_bits", "data_bytes"): 8,
    ("data_bytes", "data_bits"): 1/8,
}


def get_unit_info(unit_str: str) -> Optional[Tuple[str, float, str]]:
    """Get unit info: (category, base_value, canonical_name)."""
    # Check case-sensitive symbols first
    if unit_str in CASE_SENSITIVE_SYMBOLS:
        return CASE_SENSITIVE_SYMBOLS[unit_str]

    # Then check case-insensitive word aliases
    return CASE_INSENSITIVE_WORDS.get(unit_str.lower())


def is_temperature_unit(unit_str: str) -> bool:
    """Check if a unit is a temperature unit."""
    return _get_temp_canonical(unit_str) is not None


def is_rate_unit(unit_str: str) -> bool:
    """Check if a unit is a rate unit."""
    info = get_unit_info(unit_str)
    if info:
        return info[0].startswith("rate_") or info[0] == "speed"
    return False


def convert_units(value: float, from_unit: str, to_unit: str) -> Optional[UnitResult]:
    """
    Convert a value from one unit to another.

    Returns UnitResult with converted value and target unit, or None if conversion not possible.
    """
    # Check for temperature first
    if is_temperature_unit(from_unit) and is_temperature_unit(to_unit):
        result = _convert_temperature(value, from_unit, to_unit)
        if result is not None:
            to_canonical = _get_temp_canonical(to_unit)
            return UnitResult(value=result, unit=to_canonical)
        return None

    # Standard unit conversion
    from_info = get_unit_info(from_unit)
    to_info = get_unit_info(to_unit)

    if not from_info or not to_info:
        return None

    from_category, from_base, _ = from_info
    to_category, to_base, to_canonical = to_info

    # Same category - direct conversion
    if from_category == to_category:
        base_value = value * from_base
        result = base_value / to_base
        return UnitResult(value=result, unit=to_canonical)

    # Check for compatible categories (bits <-> bytes)
    conversion_key = (from_category, to_category)
    if conversion_key in COMPATIBLE_CATEGORIES:
        bits_per_byte = COMPATIBLE_CATEGORIES[conversion_key]
        # Convert to base unit of from_category, then cross-convert, then to target
        base_value = value * from_base
        cross_value = base_value / bits_per_byte
        result = cross_value / to_base
        return UnitResult(value=result, unit=to_canonical)

    return None


def try_parse_unit_expression(expression: str, resolve_var: Callable) -> Optional[UnitResult]:
    """
    Try to parse and evaluate a unit conversion expression.

    Patterns:
    - "X unit in unit"
    - "X unit to unit"
    - "X unit as unit"
    - "X unit / Y unit" (rate formation)
    - "X unit + Y unit" (unit arithmetic)
    - "X unit - Y unit" (unit arithmetic)

    Args:
        expression: The expression string to parse
        resolve_var: Function to resolve variable names to values

    Returns:
        UnitResult if this is a unit conversion, None otherwise
    """
    expression = expression.strip()

    # Try unit arithmetic first: X unit +/- Y unit
    result = _try_unit_arithmetic(expression, resolve_var)
    if result is not None:
        return result

    # Try rate formation: X unit / Y unit
    result = _try_rate_formation(expression, resolve_var)
    if result is not None:
        return result

    # Pattern: <number> <unit> (in|to|as) <unit>
    # The number can include SI suffixes
    # Units can include / for rates like MB/s
    pattern = r'^([\d,]+\.?\d*[kKmMbB]?)\s*([a-zA-Z°][a-zA-Z°/]*)\s+(?:in|to|as)\s+([a-zA-Z°][a-zA-Z°/]*)$'
    match = re.match(pattern, expression)

    if not match:
        # Try with variable instead of number
        pattern_var = r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s+([a-zA-Z°][a-zA-Z°/]*)\s+(?:in|to|as)\s+([a-zA-Z°][a-zA-Z°/]*)$'
        match = re.match(pattern_var, expression)
        if match:
            var_name = match.group(1)
            value = resolve_var(var_name)
            if value is None:
                return None
            from_unit = match.group(2)
            to_unit = match.group(3)
            return convert_units(value, from_unit, to_unit)
        return None

    num_str = match.group(1).replace(',', '')
    from_unit = match.group(2)
    to_unit = match.group(3)

    # Parse number with SI suffix
    value = _parse_number_with_suffix(num_str)
    if value is None:
        return None

    return convert_units(value, from_unit, to_unit)


MAX_ARITHMETIC_DEPTH = 50  # Prevent stack overflow on long chains


def _try_unit_arithmetic(expression: str, resolve_var: Callable,
                         _depth: int = 0) -> Optional[UnitResult]:
    """
    Try to parse unit arithmetic: X unit +/- Y unit
    The result uses the unit of the last operand.

    Examples:
        1 m + 100 cm → 200 cm
        1 km + 500 m → 1500 m
        2 lb + 500 g → 1407.19 g
        1 hr + 30 min → 90 min
        1 hr - 30 min → 30 min
    """
    if _depth > MAX_ARITHMETIC_DEPTH:
        return None  # Prevent stack overflow

    # Pattern: <number> <unit> (+|-) <number> <unit>
    # Handle multiple operations left to right
    pattern = r'^([\d,]+\.?\d*[kKmMbB]?)\s*([a-zA-Z][a-zA-Z]*)\s*([+\-])\s*([\d,]+\.?\d*[kKmMbB]?)\s*([a-zA-Z][a-zA-Z]*)(.*)$'
    match = re.match(pattern, expression)

    if not match:
        return None

    num1_str = match.group(1)
    unit1 = match.group(2)
    operator = match.group(3)
    num2_str = match.group(4)
    unit2 = match.group(5)
    rest = match.group(6).strip()

    num1 = _parse_number_with_suffix(num1_str)
    num2 = _parse_number_with_suffix(num2_str)

    if num1 is None or num2 is None:
        return None

    # Get unit info for both
    unit1_info = get_unit_info(unit1)
    unit2_info = get_unit_info(unit2)

    if not unit1_info or not unit2_info:
        return None

    cat1, base1, _ = unit1_info
    cat2, base2, canonical2 = unit2_info

    # Must be same category for addition/subtraction
    if cat1 != cat2:
        # Check for compatible categories (bits <-> bytes)
        if (cat1, cat2) not in COMPATIBLE_CATEGORIES:
            # Return error result - expression was recognized but units are incompatible
            return UnitResult(value=0, unit="", error=True)

    # Convert both to base units, then to target unit (unit2)
    if cat1 == cat2:
        # Same category - direct conversion
        base_value1 = num1 * base1
        base_value2 = num2 * base2

        if operator == '+':
            result_base = base_value1 + base_value2
        else:
            result_base = base_value1 - base_value2

        result_value = result_base / base2
    else:
        # Cross-category (bits <-> bytes)
        conversion_factor = COMPATIBLE_CATEGORIES[(cat1, cat2)]
        base_value1 = num1 * base1 / conversion_factor
        base_value2 = num2 * base2

        if operator == '+':
            result_base = base_value1 + base_value2
        else:
            result_base = base_value1 - base_value2

        result_value = result_base / base2

    # Handle chained operations: if there's more expression, continue
    if rest:
        # Check if rest starts with another operator
        rest_match = re.match(r'^([+\-])\s*([\d,]+\.?\d*[kKmMbB]?)\s*([a-zA-Z][a-zA-Z]*)(.*)$', rest)
        if rest_match:
            # Recursively handle the rest
            next_op = rest_match.group(1)
            next_num_str = rest_match.group(2)
            next_unit = rest_match.group(3)
            next_rest = rest_match.group(4).strip()

            next_num = _parse_number_with_suffix(next_num_str)
            if next_num is None:
                return None

            next_unit_info = get_unit_info(next_unit)
            if not next_unit_info:
                return None

            next_cat, next_base, next_canonical = next_unit_info

            # Check compatibility with current result category
            if next_cat != cat2 and (cat2, next_cat) not in COMPATIBLE_CATEGORIES:
                return None

            # Convert current result to base, then operate with next value
            if next_cat == cat2:
                current_base = result_value * base2
                next_base_value = next_num * next_base

                if next_op == '+':
                    new_result_base = current_base + next_base_value
                else:
                    new_result_base = current_base - next_base_value

                result_value = new_result_base / next_base
                canonical2 = next_canonical
            else:
                # Cross-category
                conversion_factor = COMPATIBLE_CATEGORIES[(cat2, next_cat)]
                current_base = result_value * base2 / conversion_factor
                next_base_value = next_num * next_base

                if next_op == '+':
                    new_result_base = current_base + next_base_value
                else:
                    new_result_base = current_base - next_base_value

                result_value = new_result_base / next_base
                canonical2 = next_canonical
                cat2 = next_cat
                base2 = next_base

            # Continue with more if present
            if next_rest:
                # Build new expression for recursive call
                new_expr = f"{result_value} {canonical2}{next_rest}"
                return _try_unit_arithmetic(new_expr, resolve_var, _depth + 1)

    return UnitResult(value=result_value, unit=canonical2)


def _try_rate_formation(expression: str, resolve_var: Callable) -> Optional[UnitResult]:
    """
    Try to parse rate formation: X unit / Y unit
    Examples:
        100 MB / 10 s → 10 MB/s
        500 km / 2 hours → 250 km/h
    """
    # Pattern: <number> <unit> / <number> <unit>
    pattern = r'^([\d,]+\.?\d*[kKmMbB]?)\s*([a-zA-Z]+)\s*/\s*([\d,]+\.?\d*[kKmMbB]?)\s*([a-zA-Z]+)$'
    match = re.match(pattern, expression)

    if not match:
        return None

    num1_str = match.group(1)
    unit1 = match.group(2)
    num2_str = match.group(3)
    unit2 = match.group(4)

    num1 = _parse_number_with_suffix(num1_str)
    num2 = _parse_number_with_suffix(num2_str)

    if num1 is None or num2 is None or num2 == 0:
        return None

    # Check what kind of rate we're forming
    rate_result = _form_rate(num1, unit1, num2, unit2)
    return rate_result


def _form_rate(num1: float, unit1: str, num2: float, unit2: str) -> Optional[UnitResult]:
    """
    Form a rate from two values with units.
    E.g., 100 MB / 10 s → 10 MB/s
    """
    unit1_info = get_unit_info(unit1)
    unit2_info = get_unit_info(unit2)

    if not unit1_info or not unit2_info:
        return None

    cat1, base1, canonical1 = unit1_info
    cat2, base2, canonical2 = unit2_info

    # Data / Time → Data rate
    if cat1 in ("data_bytes", "data_bits") and cat2 == "time":
        # Convert both to base units
        data_base = num1 * base1  # in bytes or bits
        time_base = num2 * base2  # in seconds

        rate_value = data_base / time_base

        # Determine appropriate rate unit
        if cat1 == "data_bytes":
            rate_unit, rate_base, rate_canonical = _best_rate_unit(rate_value, "rate_bytes")
        else:
            rate_unit, rate_base, rate_canonical = _best_rate_unit(rate_value, "rate_bits")

        return UnitResult(value=rate_value / rate_base, unit=rate_canonical)

    # Distance / Time → Speed
    if cat1 == "length" and cat2 == "time":
        # Convert both to base units (meters and seconds)
        dist_base = num1 * base1  # in meters
        time_base = num2 * base2  # in seconds

        speed_mps = dist_base / time_base

        # Determine appropriate speed unit based on input
        if canonical1 == "km" or canonical1.startswith("kilo"):
            if canonical2 in ("hr", "hour", "hours"):
                return UnitResult(value=speed_mps / (1000/3600), unit="km/h")
        if canonical1 in ("mi", "mile", "miles"):
            if canonical2 in ("hr", "hour", "hours"):
                return UnitResult(value=speed_mps / (1609.344/3600), unit="mph")

        # Default to m/s
        return UnitResult(value=speed_mps, unit="m/s")

    return None


def _best_rate_unit(value_in_base: float, category: str) -> Tuple[str, float, str]:
    """Find the best rate unit to display a value (not too many digits)."""
    if category == "rate_bytes":
        thresholds = [
            (1e12, 1e12, "TB/s"),
            (1e9, 1e9, "GB/s"),
            (1e6, 1e6, "MB/s"),
            (1e3, 1e3, "KB/s"),
            (0, 1, "B/s"),
        ]
    else:  # rate_bits
        thresholds = [
            (1e12, 1e12, "Tbps"),
            (1e9, 1e9, "Gbps"),
            (1e6, 1e6, "Mbps"),
            (1e3, 1e3, "Kbps"),
            (0, 1, "bps"),
        ]

    for threshold, base, unit in thresholds:
        if value_in_base >= threshold:
            return (unit, base, unit)

    return thresholds[-1]


def _parse_number_with_suffix(s: str) -> Optional[float]:
    """
    Parse a number string with optional SI suffix.

    Case-sensitive SI prefixes:
    - k (lowercase) = 1,000 (kilo)
    - M (uppercase) = 1,000,000 (mega)
    - G (uppercase) = 1,000,000,000 (giga)
    - B (uppercase) = 1,000,000,000 (billion)

    Note: B for billions only applies when attached directly to number.
    """
    s = s.strip().replace(',', '')
    if not s:
        return None

    # Case-sensitive SI prefixes for numbers
    suffix_multipliers = {
        'k': 1e3,   # kilo (lowercase only)
        'M': 1e6,   # mega (uppercase only)
        'G': 1e9,   # giga (uppercase only)
        'B': 1e9,   # billion (uppercase only)
    }

    last_char = s[-1]
    if last_char in suffix_multipliers:
        try:
            base = float(s[:-1])
            return base * suffix_multipliers[last_char]
        except ValueError:
            return None

    try:
        return float(s)
    except ValueError:
        return None


def get_all_unit_names() -> set:
    """Get all registered unit names (for reserved words)."""
    names = set(CASE_INSENSITIVE_WORDS.keys())
    names.update(CASE_SENSITIVE_SYMBOLS.keys())
    names.update(TEMP_SYMBOLS_CASE_SENSITIVE.keys())
    names.update(TEMP_WORDS_CASE_INSENSITIVE.keys())
    return names
