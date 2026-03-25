"""Percentage expression handling for Reckn."""

import re
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class ParsedValue:
    """A parsed numeric value that may carry unit information."""
    value: float
    unit: object = None  # Optional Unit from value.py


@dataclass
class PercentageResult:
    """Result of evaluating a percentage expression."""
    value: float
    is_percentage: bool = False  # True if result should display as "X%"
    unit: object = None  # Optional Unit carried from the base value


def try_parse_percentage_expression(expression: str, resolve_var: callable,
                                     evaluate_expr: callable = None) -> Optional[PercentageResult]:
    """
    Try to parse and evaluate a percentage expression.

    Args:
        expression: The expression string to parse
        resolve_var: Function to resolve variable names to values
        evaluate_expr: Optional function to evaluate arbitrary sub-expressions (e.g. "100 + 50")
                       Returns Optional[float].

    Returns:
        PercentageResult if this is a percentage expression, None otherwise
    """
    expression = expression.strip()

    # Try each pattern in order
    result = _try_as_percent_of(expression, resolve_var, evaluate_expr)
    if result is not None:
        return result

    result = _try_percent_of(expression, resolve_var, evaluate_expr)
    if result is not None:
        return result

    result = _try_percent_off(expression, resolve_var, evaluate_expr)
    if result is not None:
        return result

    result = _try_percent_on(expression, resolve_var, evaluate_expr)
    if result is not None:
        return result

    result = _try_value_plus_percent(expression, resolve_var, evaluate_expr)
    if result is not None:
        return result

    result = _try_value_minus_percent(expression, resolve_var, evaluate_expr)
    if result is not None:
        return result

    return None


def _parse_number_or_var(s: str, resolve_var: callable,
                         evaluate_expr: callable = None) -> Optional[ParsedValue]:
    """Parse a string as a number, variable, or evaluable sub-expression.

    Returns a ParsedValue with optional unit information preserved."""
    s = s.strip()

    # Try as a number (with optional SI suffix)
    number_match = re.match(r'^([\d,]+\.?\d*)([kKmMbB])?$', s)
    if number_match:
        num_str = number_match.group(1).replace(',', '')
        value = float(num_str)
        suffix = number_match.group(2)
        if suffix:
            multipliers = {'k': 1e3, 'K': 1e3, 'm': 1e6, 'M': 1e6, 'b': 1e9, 'B': 1e9}
            value *= multipliers[suffix]
        return ParsedValue(value)

    # Try as a variable
    var_value = resolve_var(s)
    if var_value is not None:
        if isinstance(var_value, ParsedValue):
            return var_value
        return ParsedValue(var_value)

    # Try as a sub-expression (e.g. "(100 + 50)" or "salary + bonus")
    if evaluate_expr is not None:
        result = evaluate_expr(s)
        if result is not None:
            if isinstance(result, ParsedValue):
                return result
            return ParsedValue(result)

    return None


def _try_percent_of(expression: str, resolve_var: callable,
                     evaluate_expr: callable = None) -> Optional[PercentageResult]:
    """
    Parse: 25% of 1000 → 250, 25% of (100 + 50) → 37.5
    """
    match = re.match(r'^([\d.]+)\s*%\s+of\s+(.+)$', expression, re.IGNORECASE)
    if match:
        percent = float(match.group(1))
        base_str = match.group(2)
        base = _parse_number_or_var(base_str, resolve_var, evaluate_expr)
        if base is not None:
            return PercentageResult(value=(percent / 100) * base.value, unit=base.unit)
    return None


def _try_percent_off(expression: str, resolve_var: callable,
                      evaluate_expr: callable = None) -> Optional[PercentageResult]:
    """
    Parse: 10% off 200 → 180, 10% off (salary + bonus)
    """
    match = re.match(r'^([\d.]+)\s*%\s+off\s+(.+)$', expression, re.IGNORECASE)
    if match:
        percent = float(match.group(1))
        base_str = match.group(2)
        base = _parse_number_or_var(base_str, resolve_var, evaluate_expr)
        if base is not None:
            return PercentageResult(value=base.value - (percent / 100) * base.value, unit=base.unit)
    return None


def _try_percent_on(expression: str, resolve_var: callable,
                     evaluate_expr: callable = None) -> Optional[PercentageResult]:
    """
    Parse: 10% on 200 → 220, 10% on (salary + bonus)
    """
    match = re.match(r'^([\d.]+)\s*%\s+on\s+(.+)$', expression, re.IGNORECASE)
    if match:
        percent = float(match.group(1))
        base_str = match.group(2)
        base = _parse_number_or_var(base_str, resolve_var, evaluate_expr)
        if base is not None:
            return PercentageResult(value=base.value + (percent / 100) * base.value, unit=base.unit)
    return None


def _try_value_plus_percent(expression: str, resolve_var: callable,
                             evaluate_expr: callable = None) -> Optional[PercentageResult]:
    """
    Parse: 200 + 10% → 220, (200 + 100) + 15% → 345
    """
    match = re.match(r'^(.+?)\s*\+\s*([\d.]+)\s*%\s*$', expression)
    if match:
        base_str = match.group(1)
        percent = float(match.group(2))
        base = _parse_number_or_var(base_str, resolve_var, evaluate_expr)
        if base is not None:
            return PercentageResult(value=base.value + (percent / 100) * base.value, unit=base.unit)
    return None


def _try_value_minus_percent(expression: str, resolve_var: callable,
                              evaluate_expr: callable = None) -> Optional[PercentageResult]:
    """
    Parse: 200 - 10% → 180, (200 + 100) - 15% → 255
    """
    match = re.match(r'^(.+?)\s*-\s*([\d.]+)\s*%\s*$', expression)
    if match:
        base_str = match.group(1)
        percent = float(match.group(2))
        base = _parse_number_or_var(base_str, resolve_var, evaluate_expr)
        if base is not None:
            return PercentageResult(value=base.value - (percent / 100) * base.value, unit=base.unit)
    return None


def _try_as_percent_of(expression: str, resolve_var: callable,
                        evaluate_expr: callable = None) -> Optional[PercentageResult]:
    """
    Parse: 50 as a % of 200 → 25%, (30 + 20) as a % of 200 → 25%
    """
    match = re.match(r'^(.+?)\s+as\s+a?\s*%\s+of\s+(.+)$', expression, re.IGNORECASE)
    if match:
        part_str = match.group(1)
        whole_str = match.group(2)
        part = _parse_number_or_var(part_str, resolve_var, evaluate_expr)
        whole = _parse_number_or_var(whole_str, resolve_var, evaluate_expr)
        if part is not None and whole is not None and whole.value != 0:
            return PercentageResult(value=(part.value / whole.value) * 100, is_percentage=True)
    return None
