"""Proportion expression handling for Reckn.

Supports patterns like:
  3 is to 6 as what is to 10       → 5
  3 is to 6 as 9 is to what        → 18
  $100 is to $300 as what is to $600  → $200
  distance is to time as what is to 2 hr  → (with units)
"""

import re
from typing import Optional
from dataclasses import dataclass


@dataclass
class ProportionResult:
    """Result of evaluating a proportion expression."""
    value: float
    unit: object = None  # Optional Unit from value.py


def try_parse_proportion(expression: str, resolve_var: callable,
                         evaluate_expr: callable = None) -> Optional[ProportionResult]:
    """
    Try to parse and evaluate a proportion expression.

    Supported forms:
      A is to B as what is to D   → solves for C: A/B = C/D → C = A*D/B
      A is to B as C is to what   → solves for D: A/B = C/D → D = B*C/A

    Each slot (A, B, C, D) can be a number, variable, line reference,
    or sub-expression — evaluated through the normal parser pipeline.

    Args:
        expression: The expression string to parse
        resolve_var: Function to resolve variable names to ParsedValue
        evaluate_expr: Function to evaluate sub-expressions, returns ParsedValue or None

    Returns:
        ProportionResult if this is a proportion expression, None otherwise
    """
    expression = expression.strip()

    # Pattern: A is to B as (what|x) is to D
    # or:      A is to B as C is to (what|x)
    # Allow flexible whitespace around "is to" and "as"
    match = re.match(
        r'^(.+?)\s+is\s+to\s+(.+?)\s+as\s+(.+?)\s+is\s+to\s+(.+?)$',
        expression, re.IGNORECASE
    )
    if not match:
        return None

    a_str = match.group(1).strip()
    b_str = match.group(2).strip()
    c_str = match.group(3).strip()
    d_str = match.group(4).strip()

    a_is_unknown = _is_unknown(a_str)
    b_is_unknown = _is_unknown(b_str)
    c_is_unknown = _is_unknown(c_str)
    d_is_unknown = _is_unknown(d_str)

    # Exactly one unknown required
    unknowns = sum([a_is_unknown, b_is_unknown, c_is_unknown, d_is_unknown])
    if unknowns != 1:
        return None

    # Evaluate the known slots
    from .percentages import ParsedValue

    def _eval_slot(s):
        return _parse_slot(s, resolve_var, evaluate_expr)

    if a_is_unknown:
        b = _eval_slot(b_str)
        c = _eval_slot(c_str)
        d = _eval_slot(d_str)
        if b is None or c is None or d is None or c.value == 0:
            return None
        # A/B = C/D → A = B*C/D
        result_value = b.value * c.value / d.value
        result_unit = b.unit  # A pairs with B
        return ProportionResult(result_value, result_unit)

    elif b_is_unknown:
        a = _eval_slot(a_str)
        c = _eval_slot(c_str)
        d = _eval_slot(d_str)
        if a is None or c is None or d is None or a.value == 0:
            return None
        # A/B = C/D → B = A*D/C
        result_value = a.value * d.value / c.value
        result_unit = a.unit  # B pairs with A
        return ProportionResult(result_value, result_unit)

    elif c_is_unknown:
        a = _eval_slot(a_str)
        b = _eval_slot(b_str)
        d = _eval_slot(d_str)
        if a is None or b is None or d is None or b.value == 0:
            return None
        # A/B = C/D → C = A*D/B
        result_value = a.value * d.value / b.value
        result_unit = d.unit  # C pairs with D
        return ProportionResult(result_value, result_unit)

    else:  # d_is_unknown
        a = _eval_slot(a_str)
        b = _eval_slot(b_str)
        c = _eval_slot(c_str)
        if a is None or b is None or c is None or a.value == 0:
            return None
        # A/B = C/D → D = B*C/A
        result_value = b.value * c.value / a.value
        result_unit = c.unit  # D pairs with C
        return ProportionResult(result_value, result_unit)


def _is_unknown(s: str) -> bool:
    """Check if a slot represents the unknown variable."""
    return s.lower() in ('what', 'x', '?')


def _parse_slot(s: str, resolve_var: callable,
                evaluate_expr: callable = None):
    """Parse a proportion slot as a number, variable, or expression.

    Returns a ParsedValue (with optional unit) or None.
    """
    from .percentages import ParsedValue

    s = s.strip()

    # Try as a number (with optional SI suffix)
    number_match = re.match(r'^([\d,]+\.?\d*)([kKmMbBgG])?$', s)
    if number_match:
        num_str = number_match.group(1).replace(',', '')
        value = float(num_str)
        suffix = number_match.group(2)
        if suffix:
            multipliers = {'k': 1e3, 'K': 1e3, 'm': 1e6, 'M': 1e6,
                           'b': 1e9, 'B': 1e9, 'g': 1e9, 'G': 1e9}
            value *= multipliers[suffix]
        return ParsedValue(value)

    # Try as a variable
    var_value = resolve_var(s)
    if var_value is not None:
        if isinstance(var_value, ParsedValue):
            return var_value
        return ParsedValue(var_value)

    # Try as a sub-expression (e.g. "100 km", "$50", "salary + bonus")
    if evaluate_expr is not None:
        result = evaluate_expr(s)
        if result is not None:
            if isinstance(result, ParsedValue):
                return result
            return ParsedValue(result)

    return None
