"""Expression evaluator for Reckn with unit-preserving values."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
import re

try:
    from .parser import Token, TokenType, ParseResult, Parser, expand_si_suffix, CURRENCY_SYMBOLS
    from .value import Value, Unit
    from .percentages import try_parse_percentage_expression, PercentageResult, ParsedValue
    from .proportions import try_parse_proportion, ProportionResult
except ImportError:
    from parser import Token, TokenType, ParseResult, Parser, expand_si_suffix, CURRENCY_SYMBOLS
    from value import Value, Unit
    from percentages import try_parse_percentage_expression, PercentageResult, ParsedValue
    from proportions import try_parse_proportion, ProportionResult

# Lazy imports to avoid circular dependencies
_units_module = None
_currencies_module = None
_dates_module = None


def _get_units_module():
    global _units_module
    if _units_module is None:
        try:
            from . import units as _units_module
        except ImportError:
            import units as _units_module
    return _units_module


def _get_currencies_module():
    global _currencies_module
    if _currencies_module is None:
        try:
            from . import currencies as _currencies_module
        except ImportError:
            import currencies as _currencies_module
    return _currencies_module


def _get_dates_module():
    global _dates_module
    if _dates_module is None:
        try:
            from . import dates as _dates_module
        except ImportError:
            import dates as _dates_module
    return _dates_module


class EvaluationContext:
    """Holds variables and line results for evaluation."""

    def __init__(self):
        self.variables: Dict[str, Value] = {}
        self.line_results: Dict[int, Value] = {}  # 1-indexed line number -> result

    def set_variable(self, name: str, value: Value) -> None:
        self.variables[name.lower()] = value

    def get_variable(self, name: str) -> Optional[Value]:
        return self.variables.get(name.lower())

    def set_line_result(self, line_num: int, value: Value) -> None:
        self.line_results[line_num] = value

    def get_line_result(self, line_num: int) -> Optional[Value]:
        return self.line_results.get(line_num)


def is_known_unit(name: str) -> bool:
    """Check if a name is a known unit, date keyword, or month name."""
    units = _get_units_module()
    dates = _get_dates_module()
    return (
        name in units.CASE_SENSITIVE_SYMBOLS or
        name.lower() in units.CASE_INSENSITIVE_WORDS or
        units.is_temperature_unit(name) or
        dates.is_date_reserved_word(name)
    )


def is_known_currency(name: str) -> bool:
    """Check if a name is a known currency."""
    currencies = _get_currencies_module()
    return currencies.is_currency(name)


import math

# Math functions registry: name -> (function, min_args, max_args)
MATH_FUNCTIONS = {
    "sqrt": (math.sqrt, 1, 1),
    "log": (math.log, 1, 1),
    "log2": (math.log2, 1, 1),
    "log10": (math.log10, 1, 1),
    "sin": (math.sin, 1, 1),
    "cos": (math.cos, 1, 1),
    "tan": (math.tan, 1, 1),
    "abs": (abs, 1, 1),
    "round": (round, 1, 2),
    "floor": (math.floor, 1, 1),
    "ceil": (math.ceil, 1, 1),
    "min": (min, 2, 99),
    "max": (max, 2, 99),
}


def is_math_function(name: str) -> bool:
    """Check if a name is a known math function."""
    return name.lower() in MATH_FUNCTIONS


def get_unit_info(unit_name: str) -> Optional[Tuple[str, float, str]]:
    """Get unit info: (category, base_multiplier, canonical_name)."""
    units = _get_units_module()
    # Check temperature first
    if units.is_temperature_unit(unit_name):
        canonical = units._get_temp_canonical(unit_name)
        return ("temperature", 1.0, canonical) if canonical else None
    return units.get_unit_info(unit_name)


def parse_unit(unit_name: str) -> Optional[Unit]:
    """Parse a unit name into a Unit object."""
    # First check if it's a registered unit (including rate units like km/h, mph)
    info = get_unit_info(unit_name)
    if info:
        category, _, canonical = info
        # Speed and rate units have / in their canonical form
        if '/' in canonical:
            parts = canonical.split('/')
            return Unit.rate(parts[0], parts[1], category)
        return Unit.simple(canonical, category)

    # Check for compound rate units not in registry (e.g., custom X/Y)
    if '/' in unit_name:
        parts = unit_name.split('/')
        if len(parts) == 2:
            num_info = get_unit_info(parts[0])
            denom_info = get_unit_info(parts[1])
            if num_info and denom_info:
                return Unit.rate(num_info[2], denom_info[2], num_info[0])
        return None

    # Check if it's a currency
    currencies = _get_currencies_module()
    iso = currencies.normalize_currency(unit_name)
    if iso:
        return Unit.currency(iso)

    return None


def convert_value(value: Value, target_unit: Unit) -> Optional[Value]:
    """Convert a Value to a different unit."""
    units = _get_units_module()
    currencies = _get_currencies_module()

    # If value has no unit, just attach the target unit
    if value.unit is None:
        return Value(value.value, target_unit)

    # Currency conversion
    if value.unit.is_currency and target_unit.is_currency:
        from_iso = value.unit.iso_code
        to_iso = target_unit.iso_code
        converter = currencies.get_converter()
        result = converter.convert(value.value, from_iso, to_iso)
        if result and not result.error:
            return Value(result.value, target_unit)
        if converter.is_loading:
            return Value.loading()
        return None

    # Don't convert currency to non-currency or vice versa
    if value.unit.is_currency or target_unit.is_currency:
        return None

    # Temperature conversion (special case - not linear)
    if value.unit.category == "temperature":
        from_unit = value.unit.canonical
        to_unit = target_unit.canonical
        result = units._convert_temperature(value.value, from_unit, to_unit)
        if result is not None:
            return Value(result, target_unit)
        return None

    # Handle rate unit conversions (e.g., km/h to mph)
    if value.unit.is_rate and target_unit.is_rate:
        from_canonical = value.unit.canonical
        to_canonical = target_unit.canonical
        from_info = get_unit_info(from_canonical)
        to_info = get_unit_info(to_canonical)
        if from_info and to_info:
            from_category, from_base, _ = from_info
            to_category, to_base, _ = to_info
            if from_category == to_category:
                base_value = value.value * from_base
                result = base_value / to_base
                return Value(result, target_unit)
            # Check compatible categories
            conversion_key = (from_category, to_category)
            if conversion_key in units.COMPATIBLE_CATEGORIES:
                factor = units.COMPATIBLE_CATEGORIES[conversion_key]
                base_value = value.value * from_base
                cross_value = base_value / factor
                result = cross_value / to_base
                return Value(result, target_unit)
        return None

    # Standard unit conversion
    from_info = get_unit_info(value.unit.canonical)
    to_info = get_unit_info(target_unit.canonical)

    if not from_info or not to_info:
        return None

    from_category, from_base, _ = from_info
    to_category, to_base, _ = to_info

    # Same category - direct conversion
    if from_category == to_category:
        base_value = value.value * from_base
        result = base_value / to_base
        return Value(result, target_unit)

    # Check for compatible categories (bits <-> bytes)
    conversion_key = (from_category, to_category)
    if conversion_key in units.COMPATIBLE_CATEGORIES:
        factor = units.COMPATIBLE_CATEGORIES[conversion_key]
        base_value = value.value * from_base
        cross_value = base_value / factor
        result = cross_value / to_base
        return Value(result, target_unit)

    return None


class Evaluator:
    """Evaluates parsed expressions using recursive descent, returning Value objects."""

    def __init__(self, context: EvaluationContext):
        self.context = context
        self.tokens: List[Token] = []
        self.pos: int = 0

    def current(self) -> Token:
        """Return the current token without advancing."""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return Token(TokenType.EOF, '', -1)

    def peek(self, offset: int = 1) -> Token:
        """Look ahead by offset tokens without advancing."""
        if self.pos + offset < len(self.tokens):
            return self.tokens[self.pos + offset]
        return Token(TokenType.EOF, '', -1)

    def advance(self) -> Token:
        """Return current token and advance to next."""
        token = self.current()
        self.pos += 1
        return token

    def evaluate(self, tokens: List[Token]) -> Optional[Value]:
        """Evaluate a list of tokens and return the result as a Value."""
        self.tokens = tokens
        self.pos = 0

        if not tokens or (len(tokens) == 1 and tokens[0].type == TokenType.EOF):
            return None

        try:
            result = self.parse_conversion()
            return result
        except (ValueError, ZeroDivisionError, KeyError, IndexError):
            # Expected errors during parsing/evaluation
            return None
        except RecursionError:
            # Prevent crash on deeply nested expressions
            return None

    def parse_conversion(self) -> Value:
        """Parse unit conversion (lowest precedence): expr (in|to|as) unit."""
        left = self.parse_expression()

        # Check for conversion keywords
        while self.current().type == TokenType.IDENTIFIER:
            keyword = self.current().value.lower()
            if keyword in ('in', 'to', 'as'):
                self.advance()

                # Special case: "as timespan"
                if (keyword == 'as' and self.current().type == TokenType.IDENTIFIER
                        and self.current().value.lower() == 'timespan'):
                    self.advance()
                    dates = _get_dates_module()
                    # Convert the value to total seconds
                    if isinstance(left.value, (int, float)):
                        if left.unit and left.unit.category == "time":
                            units_mod = _get_units_module()
                            info = units_mod.get_unit_info(left.unit.canonical)
                            if info:
                                _, base_seconds, _ = info
                                total_seconds = left.value * base_seconds
                                left = Value.timespan(total_seconds)
                                continue
                        elif left.unit is None:
                            # Plain number — treat as seconds
                            left = Value.timespan(float(left.value))
                            continue
                    raise ValueError("Cannot convert to timespan")

                target_unit = self._parse_unit_specifier()
                if target_unit:
                    converted = convert_value(left, target_unit)
                    if converted:
                        left = converted
                    else:
                        raise ValueError(f"Cannot convert to {target_unit}")
                else:
                    raise ValueError("Invalid unit specifier")
            else:
                break

        # After conversion, continue with any remaining arithmetic operators
        # Handle term-level operators (* /) first for correct precedence
        while self.current().type == TokenType.OPERATOR and self.current().value in '*/':
            op = self.advance().value
            right = self.parse_power()
            left = self._apply_multiplicative_op(left, op, right)

        # Then handle expression-level operators (+ -)
        while self.current().type == TokenType.OPERATOR and self.current().value in '+-':
            op = self.advance().value
            right = self.parse_term()
            left = self._apply_additive_op(left, op, right)

        return left

    def _parse_unit_specifier(self) -> Optional[Unit]:
        """Parse a unit specifier (e.g., 'km', 'USD', 'km/h', '$', '€')."""
        # Handle currency symbol as target unit
        if self.current().type == TokenType.CURRENCY_SYMBOL:
            symbol = self.advance().value
            currencies = _get_currencies_module()
            iso = currencies.normalize_currency(symbol)
            if iso:
                return Unit.currency(iso)
            return None

        if self.current().type != TokenType.IDENTIFIER:
            return None

        unit_str = self.advance().value

        # Check for rate unit: unit/unit
        if self.current().type == TokenType.OPERATOR and self.current().value == '/':
            self.advance()
            if self.current().type == TokenType.IDENTIFIER:
                denom = self.advance().value
                unit_str = f"{unit_str}/{denom}"

        return parse_unit(unit_str)

    def parse_expression(self) -> Value:
        """Parse addition and subtraction."""
        left = self.parse_term()

        while self.current().type == TokenType.OPERATOR and self.current().value in '+-':
            op = self.advance().value
            right = self.parse_term()
            left = self._apply_additive_op(left, op, right)

        return left

    def _apply_additive_op(self, left: Value, op: str, right: Value) -> Value:
        """
        Apply + or - with unit handling.

        Rules:
        - Date +/- duration → date
        - Date - date → interval
        - Same unit: direct operation, keep unit
        - Same category: convert left to right's unit, result in right's unit
        - One has unit, other plain: result uses the unit
        - Both plain: result is plain
        """
        from datetime import date as Date
        dates = _get_dates_module()

        # Date + time_unit → date (calendar addition)
        if left.is_date and right.unit and right.unit.category == "time":
            interval = self._value_to_interval(right)
            if interval is not None:
                if op == '+':
                    return Value.date(dates.add_interval_to_date(left.value, interval))
                else:
                    return Value.date(dates.add_interval_to_date(left.value, -interval))

        # time_unit + date → date (only addition is commutative)
        if right.is_date and left.unit and left.unit.category == "time" and op == '+':
            interval = self._value_to_interval(left)
            if interval is not None:
                return Value.date(dates.add_interval_to_date(right.value, interval))

        # Date - date → interval
        if left.is_date and right.is_date and op == '-':
            return Value.interval(dates.date_difference(right.value, left.value))

        # Date +/- interval
        if left.is_date and right.is_interval:
            if op == '+':
                return Value.date(dates.add_interval_to_date(left.value, right.value))
            else:
                return Value.date(dates.add_interval_to_date(left.value, -right.value))

        # Interval + date (only addition)
        if right.is_date and left.is_interval and op == '+':
            return Value.date(dates.add_interval_to_date(right.value, left.value))

        # Interval +/- interval
        if left.is_interval and right.is_interval:
            if op == '+':
                return Value.interval(left.value + right.value)
            else:
                return Value.interval(left.value + (-right.value))

        # Clock time + time_unit → clock time
        if left.is_clock_time and right.unit and right.unit.category == "time":
            minutes = self._value_to_minutes(right)
            if minutes is not None:
                if op == '+':
                    return Value.clock_time(dates.clock_time_add_minutes(left.value, minutes))
                else:
                    return Value.clock_time(dates.clock_time_add_minutes(left.value, -minutes))

        # time_unit + clock time → clock time (only addition)
        if right.is_clock_time and left.unit and left.unit.category == "time" and op == '+':
            minutes = self._value_to_minutes(left)
            if minutes is not None:
                return Value.clock_time(dates.clock_time_add_minutes(right.value, minutes))

        # Clock time - clock time → timespan
        if left.is_clock_time and right.is_clock_time and op == '-':
            diff_minutes = dates.clock_time_difference(left.value, right.value)
            return Value.timespan(float(diff_minutes * 60))

        # Guard: cannot add/subtract dates/times with incompatible values
        if (left.is_date or right.is_date or left.is_interval or right.is_interval
                or left.is_clock_time or right.is_clock_time):
            raise ValueError("Invalid date/time arithmetic")

        # Both have units
        if left.unit and right.unit:
            # Same unit - direct operation
            if left.unit == right.unit:
                if op == '+':
                    return Value(left.value + right.value, left.unit)
                else:
                    return Value(left.value - right.value, left.unit)

            # Same category - convert left to right's unit
            if left.unit.category and left.unit.category == right.unit.category:
                converted = convert_value(left, right.unit)
                if converted:
                    if op == '+':
                        return Value(converted.value + right.value, right.unit)
                    else:
                        return Value(converted.value - right.value, right.unit)

            # Incompatible units
            raise ValueError(f"Cannot {op} {left.unit} and {right.unit}")

        # Left has unit, right is plain
        if left.unit and not right.unit:
            if op == '+':
                return Value(left.value + right.value, left.unit)
            else:
                return Value(left.value - right.value, left.unit)

        # Right has unit, left is plain
        if right.unit and not left.unit:
            if op == '+':
                return Value(left.value + right.value, right.unit)
            else:
                return Value(left.value - right.value, right.unit)

        # Neither has unit
        if op == '+':
            return Value.plain(left.value + right.value)
        else:
            return Value.plain(left.value - right.value)

    def parse_term(self) -> Value:
        """Parse multiplication and division."""
        left = self.parse_power()

        while self.current().type == TokenType.OPERATOR and self.current().value in '*/':
            op = self.advance().value
            right = self.parse_power()
            left = self._apply_multiplicative_op(left, op, right)

        return left

    def _value_to_interval(self, val: Value):
        """Convert a time-unit Value to a DateInterval for calendar math."""
        dates = _get_dates_module()
        if val.unit is None or val.unit.category != "time":
            return None

        canonical = val.unit.canonical
        n = int(val.value)

        if canonical in ("day", "days"):
            return dates.DateInterval(days=n)
        elif canonical in ("week", "weeks"):
            return dates.DateInterval(days=n * 7)
        elif canonical in ("month", "months"):
            return dates.DateInterval(months=n)
        elif canonical in ("year", "years"):
            return dates.DateInterval(years=n)
        else:
            # Sub-day units (hours, minutes, seconds) — approximate as days
            units_mod = _get_units_module()
            info = units_mod.get_unit_info(canonical)
            if info:
                _, base_seconds, _ = info
                total_seconds = val.value * base_seconds
                return dates.DateInterval(days=int(total_seconds / 86400))
        return None

    def _value_to_minutes(self, val: Value) -> Optional[int]:
        """Convert a time-unit Value to total minutes for clock time math."""
        if val.unit is None or val.unit.category != "time":
            return None
        units_mod = _get_units_module()
        info = units_mod.get_unit_info(val.unit.canonical)
        if info:
            _, base_seconds, _ = info
            return int(val.value * base_seconds / 60)
        return None

    def _apply_multiplicative_op(self, left: Value, op: str, right: Value) -> Value:
        """
        Apply * or / with unit handling.

        Rules for multiplication:
        - unit * plain = unit
        - plain * unit = unit
        - unit * unit = compound unit (except currency * currency = error)

        Rules for division:
        - unit / plain = unit
        - unit / same_unit = dimensionless
        - unit / different_unit = compound unit (rate)
        """
        # Date and clock time values cannot be multiplied or divided
        if left.is_date or right.is_date or left.is_clock_time or right.is_clock_time:
            raise ValueError("Cannot multiply or divide dates or times")

        if op == '*':
            # Multiplication: unit * plain = unit, plain * unit = unit
            if left.unit and right.unit:
                # Both have units - create compound unit
                # Currency * currency: treat right as scalar, keep left currency
                if left.unit.is_currency and right.unit.is_currency:
                    return Value(left.value * right.value, left.unit)
                new_unit = left.unit * right.unit
                return Value(left.value * right.value, new_unit.simplify())
            elif left.unit:
                return Value(left.value * right.value, left.unit)
            elif right.unit:
                return Value(left.value * right.value, right.unit)
            else:
                return Value.plain(left.value * right.value)
        else:  # Division
            import math
            if right.value == 0 or math.isnan(right.value) or math.isinf(right.value):
                raise ValueError("Division by zero or invalid number")

            if left.unit and right.unit:
                # Both have units - may form rate or cancel out
                if left.unit == right.unit:
                    # Same units cancel: 100 km / 50 km = 2
                    return Value.plain(left.value / right.value)
                else:
                    # Different units - form compound unit
                    new_unit = left.unit / right.unit
                    simplified = new_unit.simplify()
                    if simplified.is_dimensionless:
                        return Value.plain(left.value / right.value)
                    return Value(left.value / right.value, simplified)
            elif left.unit:
                # Unit / plain = same unit
                return Value(left.value / right.value, left.unit)
            elif right.unit:
                # Plain / unit: treat unit as label on the result
                # e.g., 1000000 / 1000 eur → €1,000
                return Value(left.value / right.value, right.unit)
            else:
                return Value.plain(left.value / right.value)

    def parse_power(self) -> Value:
        """Parse exponentiation (right associative)."""
        left = self.parse_unary()

        if self.current().type == TokenType.OPERATOR and self.current().value == '^':
            self.advance()
            right = self.parse_power()  # Right associative
            if (left.is_date or left.is_interval or left.is_clock_time
                    or right.is_date or right.is_interval or right.is_clock_time):
                raise ValueError("Cannot exponentiate dates, intervals, or times")
            # If the exponent picked up a unit (e.g., 10^9 eur), detach it
            # and attach to the result: interpret as (10^9) eur
            trailing_unit = None
            if right.unit:
                if left.unit:
                    raise ValueError("Ambiguous units in exponentiation")
                trailing_unit = right.unit
                right = Value.plain(right.value)
            if left.unit:
                # Raise the value, keep the unit (simplified view)
                # e.g., (2 m)^2 = 4 m (not 4 m^2 for simplicity)
                return Value(left.value ** right.value, left.unit)
            return Value(left.value ** right.value, trailing_unit)

        return left

    def parse_unary(self) -> Value:
        """Parse unary operators (+ and -)."""
        if self.current().type == TokenType.OPERATOR and self.current().value in '+-':
            op = self.advance().value
            operand = self.parse_unary()
            if op == '-':
                if operand.is_date or operand.is_clock_time:
                    raise ValueError("Cannot negate a date or time")
                if operand.is_interval:
                    return Value.interval(-operand.value)
                return Value(-operand.value, operand.unit)
            return operand

        return self.parse_primary()

    def _parse_function_call(self, func_name: str) -> Value:
        """Parse a function call: func_name(arg1, arg2, ...)."""
        self.advance()  # consume function name
        self.advance()  # consume (

        # Parse arguments
        args = []
        if self.current().type != TokenType.RPAREN:
            args.append(self.parse_conversion())
            while self.current().type == TokenType.COMMA:
                self.advance()  # consume ,
                args.append(self.parse_conversion())

        if self.current().type != TokenType.RPAREN:
            raise ValueError(f"Missing closing parenthesis for {func_name}()")
        self.advance()  # consume )

        func, min_args, max_args = MATH_FUNCTIONS[func_name.lower()]
        if not (min_args <= len(args) <= max_args):
            raise ValueError(f"{func_name}() expects {min_args}-{max_args} arguments, got {len(args)}")

        # Extract numeric values
        raw_values = []
        for arg in args:
            if not isinstance(arg.value, (int, float)):
                raise ValueError(f"{func_name}() requires numeric arguments")
            raw_values.append(arg.value)

        # round() needs int for second arg (decimal places)
        if func_name.lower() == 'round' and len(raw_values) == 2:
            raw_values[1] = int(raw_values[1])

        # Apply function
        result_value = func(*raw_values)

        # Unit handling: abs and round preserve units, others strip them
        if func_name.lower() in ('abs', 'round', 'floor', 'ceil') and len(args) == 1:
            return Value(float(result_value), args[0].unit)
        if func_name.lower() in ('min', 'max'):
            # All args must have same unit (or no unit)
            first_unit = args[0].unit
            if all(a.unit == first_unit for a in args):
                return Value(float(result_value), first_unit)
        return Value.plain(float(result_value))

    def parse_primary(self) -> Value:
        """Parse primary expressions: numbers, variables, line refs, parentheses."""
        token = self.current()

        # Currency symbol prefix (e.g., $100, €50)
        if token.type == TokenType.CURRENCY_SYMBOL:
            self.advance()
            symbol = token.value
            # Expect a number to follow
            if self.current().type == TokenType.NUMBER:
                num_value = expand_si_suffix(self.advance().value)
                currencies = _get_currencies_module()
                iso = currencies.normalize_currency(symbol)
                if iso:
                    return Value(num_value, Unit.currency(iso))
            raise ValueError(f"Expected number after currency symbol {symbol}")

        # Number (possibly followed by unit or currency symbol suffix)
        if token.type == TokenType.NUMBER:
            self.advance()
            num_value = expand_si_suffix(token.value)

            # Check for currency symbol suffix (e.g., 100$)
            if self.current().type == TokenType.CURRENCY_SYMBOL:
                symbol = self.advance().value
                currencies = _get_currencies_module()
                iso = currencies.normalize_currency(symbol)
                if iso:
                    return Value(num_value, Unit.currency(iso))

            # Check for following unit
            if self.current().type == TokenType.IDENTIFIER:
                unit_name = self.current().value

                # Check for rate unit: identifier/identifier (e.g., km/h)
                if self.peek().type == TokenType.OPERATOR and self.peek().value == '/':
                    next_next = self.peek(2)
                    if next_next.type == TokenType.IDENTIFIER:
                        # Try to parse as a combined rate unit
                        combined = f"{unit_name}/{next_next.value}"
                        combined_unit = parse_unit(combined)
                        if combined_unit:
                            self.advance()  # consume first identifier
                            self.advance()  # consume /
                            self.advance()  # consume second identifier
                            return Value(num_value, combined_unit)

                unit = parse_unit(unit_name)
                if unit:
                    self.advance()
                    return Value(num_value, unit)

            return Value.plain(num_value)

        # Variable or unit-attached expression
        if token.type == TokenType.IDENTIFIER:
            # Check for math function call: identifier followed by (
            if is_math_function(token.value) and self.peek().type == TokenType.LPAREN:
                result = self._parse_function_call(token.value)
                # Check for unit suffix: sqrt(144) km, abs(-5) USD
                if self.current().type == TokenType.CURRENCY_SYMBOL:
                    symbol = self.advance().value
                    currencies = _get_currencies_module()
                    iso = currencies.normalize_currency(symbol)
                    if iso:
                        return Value(result.value, Unit.currency(iso))
                if self.current().type == TokenType.IDENTIFIER:
                    unit_name = self.current().value
                    if unit_name.lower() not in ('in', 'to', 'as'):
                        unit = parse_unit(unit_name)
                        if unit:
                            self.advance()
                            return Value(result.value, unit)
                return result

            self.advance()
            var_name = token.value

            # Check for clock time keyword: "now" resolves to current time of day
            dates = _get_dates_module()
            if var_name.lower() == "now":
                return Value.clock_time(dates.resolve_now_time())

            # Check for date keywords (today, yesterday, tomorrow)
            if var_name.lower() in dates.DATE_KEYWORDS:
                return Value.date(dates.resolve_date_keyword(var_name))

            # First check if it's a variable
            var_value = self.context.get_variable(var_name)

            if var_value is not None:
                # Variable found - check for unit application
                # BUT: skip if next token is a conversion keyword (in/to/as)
                # Those should be handled at the parse_conversion level
                if self.current().type == TokenType.IDENTIFIER:
                    next_val = self.current().value.lower()
                    # Don't consume conversion keywords here - let parse_conversion handle them
                    if next_val not in ('in', 'to', 'as'):
                        unit_name = self.current().value
                        unit = parse_unit(unit_name)
                        if unit:
                            self.advance()
                            # If variable already has a unit, convert
                            if var_value.unit:
                                converted = convert_value(var_value, unit)
                                if converted:
                                    return converted
                                raise ValueError(f"Cannot convert {var_value.unit} to {unit}")
                            # Variable is plain - attach unit
                            return Value(var_value.value, unit)
                return var_value

            # Not a variable - might be a unit by itself (error case usually)
            raise ValueError(f"Unknown variable: {var_name}")

        # Line reference
        if token.type == TokenType.LINE_REF:
            self.advance()
            line_num = int(token.value[4:])
            line_value = self.context.get_line_result(line_num)
            if line_value is None:
                raise ValueError(f"No result for line {line_num}")

            # Check for unit application (but not conversion keywords)
            if self.current().type == TokenType.IDENTIFIER:
                next_val = self.current().value.lower()
                if next_val not in ('in', 'to', 'as'):
                    unit_name = self.current().value
                    unit = parse_unit(unit_name)
                    if unit:
                        self.advance()
                        if line_value.unit:
                            converted = convert_value(line_value, unit)
                            if converted:
                                return converted
                            raise ValueError(f"Cannot convert {line_value.unit} to {unit}")
                        return Value(line_value.value, unit)

            return line_value

        # Parenthesized expression
        if token.type == TokenType.LPAREN:
            self.advance()
            result = self.parse_conversion()  # Allow conversions inside parens
            if self.current().type != TokenType.RPAREN:
                raise ValueError("Missing closing parenthesis")
            self.advance()

            # Check for currency symbol suffix (e.g., (1 + 9)$)
            if self.current().type == TokenType.CURRENCY_SYMBOL:
                symbol = self.advance().value
                currencies = _get_currencies_module()
                iso = currencies.normalize_currency(symbol)
                if iso:
                    return Value(result.value, Unit.currency(iso))

            # Check for unit suffix (e.g., (1 + 9)km)
            if self.current().type == TokenType.IDENTIFIER:
                unit_name = self.current().value
                next_val = unit_name.lower()
                if next_val not in ('in', 'to', 'as'):
                    # Check for rate unit: identifier/identifier (e.g., km/h)
                    if self.peek().type == TokenType.OPERATOR and self.peek().value == '/':
                        next_next = self.peek(2)
                        if next_next.type == TokenType.IDENTIFIER:
                            combined = f"{unit_name}/{next_next.value}"
                            combined_unit = parse_unit(combined)
                            if combined_unit:
                                self.advance()  # consume first identifier
                                self.advance()  # consume /
                                self.advance()  # consume second identifier
                                return Value(result.value, combined_unit)

                    unit = parse_unit(unit_name)
                    if unit:
                        self.advance()
                        return Value(result.value, unit)

            return result

        raise ValueError(f"Unexpected token: {token}")


def format_number(
    value: float,
    decimal_places: int = 6
) -> str:
    """Format a number with thousand separators and appropriate decimal places."""
    if value is None:
        return ""

    # Use scientific notation for very large or very small numbers
    abs_val = abs(value)
    if abs_val != 0 and (abs_val >= 1e12 or abs_val < 1e-6):
        return f"{value:.6g}"

    # Check if it's effectively an integer
    if value == int(value) and abs_val < 1e15:
        return f"{int(value):,}"

    # Format with specified decimal places, then strip trailing zeros
    formatted = f"{value:,.{decimal_places}f}"
    if '.' in formatted:
        formatted = formatted.rstrip('0').rstrip('.')

    return formatted


def format_value(val: Value) -> str:
    """Format a Value for display."""
    if val is None:
        return ""

    # Loading placeholder
    if val.is_loading:
        return "loading..."

    # Date formatting
    if val.is_date:
        dates = _get_dates_module()
        return dates.format_date(val.value)

    # Interval formatting
    if val.is_interval:
        dates = _get_dates_module()
        return dates.format_interval(val.value)

    # Clock time formatting
    if val.is_clock_time:
        dates = _get_dates_module()
        return dates.format_clock_time(val.value)

    # Timespan formatting
    if val.is_timespan:
        dates = _get_dates_module()
        return dates.format_timespan(val.value)

    if val.unit is None:
        return format_number(val.value)

    # Currency formatting
    if val.unit.is_currency:
        currencies = _get_currencies_module()
        iso = val.unit.iso_code
        symbol = currencies.ISO_TO_SYMBOL.get(iso, iso)

        # Format with 2 decimal places for currency
        if val.value == int(val.value):
            formatted = f"{int(val.value):,}"
        else:
            formatted = f"{val.value:,.2f}"

        # Prefix symbols for major currencies
        if symbol in ('$', '£', '€', '¥'):
            return f"{symbol}{formatted}"
        else:
            return f"{formatted} {symbol}"

    # Regular unit formatting
    return f"{format_number(val.value)} {val.unit}"


def format_total_values(values: List[Value]) -> str:
    """Format a list of grouped Values as pipe-separated string."""
    if not values:
        return "0"
    parts = [format_value(v) for v in values]
    return " | ".join(parts)


class LineEvaluator:
    """Evaluates multiple lines, tracking variables and results."""

    def __init__(self):
        self.parser = Parser()
        self.context = EvaluationContext()
        # Track line types for subtotal calculation
        self._line_types: Dict[int, str] = {}  # line_num -> "heading", "subtotal", "normal"
        self._tracked_results: Dict[int, Value] = {}  # line_num -> Value (all summable results)
        self._pending_percentage: Optional[Tuple[int, float]] = None  # (line_num, percentage)

    def evaluate_lines(self, lines: List[str]) -> List[Tuple[str, str]]:
        """Evaluate multiple lines and return list of (input, result) tuples."""
        results = []

        for i, line in enumerate(lines, start=1):
            result = self.evaluate_line(line, i)
            results.append((line, result))

        return results

    def _get_expression_text(self, line: str, parse_result: ParseResult) -> str:
        """Extract the expression text from a line (after stripping labels, etc.)."""
        stripped = line.strip()

        # Strip label if present
        label_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*', stripped)
        if label_match:
            stripped = stripped[label_match.end():]

        # If it's an assignment, get the part after the =
        if parse_result.is_assignment:
            eq_pos = stripped.find('=')
            if eq_pos != -1:
                stripped = stripped[eq_pos + 1:].strip()

        return stripped

    def _evaluate_sub_expression(self, expr: str):
        """Evaluate a sub-expression string and return its value with unit info.

        Used by percentage expressions to handle things like '(100 + 50)' or 'salary + bonus'.
        Returns a ParsedValue (with optional unit) or None.
        """
        try:
            parse_result = self.parser.parse_line(expr)
            if not parse_result or not parse_result.expression_tokens:
                return None
            evaluator = Evaluator(self.context)
            val = evaluator.evaluate(parse_result.expression_tokens)
            if val is not None and isinstance(val.value, (int, float)):
                return ParsedValue(val.value, val.unit)
        except Exception:
            pass
        return None

    def _resolve_variable(self, name: str):
        """Resolve a variable name to its value with unit info (for percentage parsing).

        Returns a ParsedValue (with optional unit) or None.
        """
        line_match = re.match(r'^line(\d+)$', name, re.IGNORECASE)
        if line_match:
            line_num = int(line_match.group(1))
            val = self.context.get_line_result(line_num)
            if val and isinstance(val.value, (int, float)):
                return ParsedValue(val.value, val.unit)
            return None

        val = self.context.get_variable(name)
        if val and isinstance(val.value, (int, float)):
            return ParsedValue(val.value, val.unit)
        return None

    def _resolve_variable_value(self, name: str) -> Optional[Value]:
        """Resolve a variable name to its full Value (for date-aware parsing)."""
        line_match = re.match(r'^line(\d+)$', name, re.IGNORECASE)
        if line_match:
            line_num = int(line_match.group(1))
            return self.context.get_line_result(line_num)

        return self.context.get_variable(name)

    def _group_and_sum(self, line_numbers) -> List[Value]:
        """Group tracked results by unit and sum within each group."""
        from collections import defaultdict
        groups: Dict[Optional[Unit], float] = defaultdict(float)

        for ln in line_numbers:
            val = self._tracked_results.get(ln)
            if val is None or not isinstance(val.value, (int, float)):
                continue
            groups[val.unit] += val.value

        results = []
        # Plain numbers first
        if None in groups:
            results.append(Value.plain(groups[None]))
        # Then unit groups, sorted by string representation
        for key in sorted((k for k in groups if k is not None), key=str):
            results.append(Value(groups[key], key))
        return results

    def _is_subtotal_marker(self, text: str) -> bool:
        """Check if text is a subtotal marker (--- or ===)."""
        stripped = text.strip()
        return stripped in ('---', '===') or (
            len(stripped) >= 3 and
            (all(c == '-' for c in stripped) or all(c == '=' for c in stripped))
        )

    def _calculate_subtotal_values(self, line_number: int) -> List[Value]:
        """Calculate subtotal values grouped by unit, back to previous heading/subtotal."""
        line_nums = []
        for ln in range(line_number - 1, 0, -1):
            line_type = self._line_types.get(ln, "normal")
            if line_type in ("heading", "subtotal"):
                break
            line_nums.append(ln)
        return self._group_and_sum(line_nums)

    def _apply_percentage_modifier(self, line_number: int, values: List[Value]) -> List[Value]:
        """Apply percentage modifier from previous line to subtotal values."""
        if line_number < 2:
            return values
        if hasattr(self, '_pending_percentage') and self._pending_percentage:
            pct_line, pct_value = self._pending_percentage
            if pct_line == line_number - 1:
                # Apply the percentage to each group
                modified = []
                for v in values:
                    modifier = v.value * (pct_value / 100.0)
                    modified.append(Value(v.value + modifier, v.unit))
                # Remove the percentage line from tracked results
                if pct_line in self._tracked_results:
                    del self._tracked_results[pct_line]
                return modified
        return values

    def evaluate_line(self, line: str, line_number: int) -> str:
        """Evaluate a single line and return formatted result."""
        parse_result = self.parser.parse_line(line)

        # Headings and comments have no result
        if parse_result.is_heading or parse_result.is_comment:
            self._line_types[line_number] = "heading" if parse_result.is_heading else "normal"
            return ""

        # Check for subtotal line (--- or ===)
        stripped = line.strip()

        # Check for subtotal assignment: var = ---
        subtotal_assignment_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*(---+|===+)\s*$', stripped)
        if subtotal_assignment_match:
            var_name = subtotal_assignment_match.group(1)
            values = self._calculate_subtotal_values(line_number)
            values = self._apply_percentage_modifier(line_number, values)

            # For variable assignment, store first value (or plain sum)
            if len(values) == 1:
                val = values[0]
            else:
                plain_sum = sum(v.value for v in values if v.unit is None)
                val = Value.plain(plain_sum) if plain_sum else (values[0] if values else Value.plain(0.0))

            self._line_types[line_number] = "subtotal"
            # Don't add to _tracked_results (avoids double-counting)
            self.context.set_line_result(line_number, val)
            self.context.set_variable(var_name, val)
            return format_total_values(values)

        # Check for plain subtotal line
        if self._is_subtotal_marker(stripped):
            values = self._calculate_subtotal_values(line_number)
            values = self._apply_percentage_modifier(line_number, values)

            # Store first value for line references
            val = values[0] if values else Value.plain(0.0)
            self._line_types[line_number] = "subtotal"
            # Don't add to _tracked_results (avoids double-counting)
            self.context.set_line_result(line_number, val)
            return format_total_values(values)

        # Empty line
        if not parse_result.expression_tokens:
            return ""

        self._line_types[line_number] = "normal"

        # Get expression text for percentage parsing (still uses old pattern matching)
        expr_text = self._get_expression_text(line, parse_result)

        # Check for standalone percentage (e.g., "22%") - these can modify the next subtotal
        standalone_pct_match = re.match(r'^(\d+(?:\.\d+)?)\s*%\s*$', expr_text.strip())
        if standalone_pct_match:
            pct_value = float(standalone_pct_match.group(1))
            self._pending_percentage = (line_number, pct_value)
            val = Value.plain(pct_value)
            self.context.set_line_result(line_number, val)
            # Don't add to _tracked_results - standalone percentages shouldn't be summed
            return f"{format_number(pct_value)}%"

        # Clear pending percentage for non-percentage lines
        self._pending_percentage = None

        # Try clock time expressions (before dates — clock time patterns are more specific)
        dates = _get_dates_module()
        clock_result = dates.try_parse_clock_time_expression(expr_text, self._resolve_variable_value)
        if clock_result is not None:
            if clock_result.result_type == "clock_time":
                val = Value.clock_time(clock_result.value)
            else:  # timespan
                val = Value.timespan(clock_result.value)

            self.context.set_line_result(line_number, val)
            if parse_result.is_assignment and parse_result.variable_name:
                self.context.set_variable(parse_result.variable_name, val)

            return format_value(val)

        # Try date expressions (before percentages — date patterns are more specific)
        date_result = dates.try_parse_date_expression(expr_text, self._resolve_variable_value)
        if date_result is not None:
            if date_result.is_date:
                val = Value.date(date_result.value)
            else:
                val = Value.interval(date_result.value)

            self.context.set_line_result(line_number, val)
            if parse_result.is_assignment and parse_result.variable_name:
                self.context.set_variable(parse_result.variable_name, val)

            return format_value(val)

        # Try percentage expressions (keep using old parser for now)
        pct_result = try_parse_percentage_expression(expr_text, self._resolve_variable, self._evaluate_sub_expression)
        if pct_result is not None:
            val = Value(pct_result.value, pct_result.unit)

            self.context.set_line_result(line_number, val)
            if parse_result.is_assignment and parse_result.variable_name:
                self.context.set_variable(parse_result.variable_name, val)

            # Only track results (not percentage results like "50 as a % of 200")
            if not pct_result.is_percentage:
                self._tracked_results[line_number] = val

            # Format with percentage sign if appropriate
            if pct_result.is_percentage:
                return f"{format_number(pct_result.value)}%"
            return format_value(val)

        # Try proportion expressions (e.g. "3 is to 6 as what is to 10")
        prop_result = try_parse_proportion(expr_text, self._resolve_variable, self._evaluate_sub_expression)
        if prop_result is not None:
            val = Value(prop_result.value, prop_result.unit)

            self.context.set_line_result(line_number, val)
            if parse_result.is_assignment and parse_result.variable_name:
                self.context.set_variable(parse_result.variable_name, val)

            if isinstance(val.value, (int, float)) and not val.is_loading:
                self._tracked_results[line_number] = val

            return format_value(val)

        # Use the new unified evaluator
        evaluator = Evaluator(self.context)
        value = evaluator.evaluate(parse_result.expression_tokens)

        if value is None:
            return ""

        # Store the result
        self.context.set_line_result(line_number, value)

        if parse_result.is_assignment and parse_result.variable_name:
            self.context.set_variable(parse_result.variable_name, value)

        # Track numeric results for floating total and subtotals
        if isinstance(value.value, (int, float)) and not value.is_loading:
            self._tracked_results[line_number] = value

        return format_value(value)

    def get_floating_totals(self) -> List[Value]:
        """Get grouped totals of all tracked results."""
        return self._group_and_sum(self._tracked_results.keys())

    def is_subtotal_line(self, line_number: int) -> bool:
        """Check if a line is a subtotal line."""
        return self._line_types.get(line_number) == "subtotal"
