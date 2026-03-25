"""Syntax highlighting for Reckn editor lines."""

import re
from typing import Set

from rich.text import Text

try:
    from .parser import Tokenizer, TokenType
except ImportError:
    from parser import Tokenizer, TokenType

# Lazy-cached module references
_units_mod = None
_currencies_mod = None
_dates_mod = None


def _get_units():
    global _units_mod
    if _units_mod is None:
        try:
            from . import units as _units_mod
        except ImportError:
            import units as _units_mod
    return _units_mod


def _get_currencies():
    global _currencies_mod
    if _currencies_mod is None:
        try:
            from . import currencies as _currencies_mod
        except ImportError:
            import currencies as _currencies_mod
    return _currencies_mod


def _get_dates():
    global _dates_mod
    if _dates_mod is None:
        try:
            from . import dates as _dates_mod
        except ImportError:
            import dates as _dates_mod
    return _dates_mod


def _is_unit(name: str) -> bool:
    """Check if name is a known unit or date keyword."""
    units = _get_units()
    dates = _get_dates()
    return (
        name in units.CASE_SENSITIVE_SYMBOLS
        or name.lower() in units.CASE_INSENSITIVE_WORDS
        or units.is_temperature_unit(name)
        or dates.is_date_reserved_word(name)
    )


def _is_currency(name: str) -> bool:
    """Check if name is a known currency code."""
    return _get_currencies().is_currency(name)


# Keywords that act as syntactic glue (dim style)
_KEYWORD_GLUE = {"of", "off", "on", "in", "to", "as", "from", "before", "after", "timespan"}

# Math function names
_MATH_FUNCTIONS = {"sqrt", "log", "log2", "log10", "sin", "cos", "tan", "abs", "round", "floor", "ceil", "min", "max"}

# SI suffixes on numbers
_SI_SUFFIXES = set("kMGB")


def highlight_line(text: str, known_variables: Set[str]) -> Text:
    """Apply syntax highlighting to a line of editor text.

    Args:
        text: The raw line text.
        known_variables: Set of lowercase variable names currently defined.

    Returns:
        A Rich Text object with styles applied. No cursor overlay.
    """
    if not text:
        return Text(" ")

    stripped = text.strip()

    # Comments: entire line dim italic
    if stripped.startswith("//"):
        return Text(text, style="dim italic")

    # Headings: entire line bold yellow underline
    if stripped.startswith("#"):
        return Text(text, style="bold yellow underline")

    # Subtotal markers (--- or ===)
    if len(stripped) >= 3 and (all(c == '-' for c in stripped) or all(c == '=' for c in stripped)):
        return Text(text, style="bold yellow")

    # Expression line — token-based highlighting
    result = Text()
    expr_offset = 0

    # Detect label prefix (e.g. "rent: ")
    label_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_-]*\s*:\s*)', text)
    if label_match:
        result.append(label_match.group(1), style="dim")
        expr_offset = label_match.end()

    expr_text = text[expr_offset:]
    if not expr_text.strip():
        # Label with no expression after it
        if not result.plain:
            return Text(" ")
        return result

    # Tokenize the expression
    tokenizer = Tokenizer(expr_text)
    tokens = tokenizer.tokenize()

    # Track position within expr_text
    pos = 0

    # Detect variable assignment (IDENTIFIER = ...)
    token_start = 0
    if (len(tokens) >= 3
            and tokens[0].type == TokenType.IDENTIFIER
            and tokens[1].type == TokenType.EQUALS):
        var_token = tokens[0]
        eq_token = tokens[1]

        # Gap before variable name
        if var_token.position > 0:
            result.append(expr_text[:var_token.position])

        # Variable name in bold green
        result.append(var_token.value, style="bold green")

        # Gap between var name and =
        gap_start = var_token.position + len(var_token.value)
        if gap_start < eq_token.position:
            result.append(expr_text[gap_start:eq_token.position])

        # The = sign
        result.append("=")

        # Move past the = sign
        pos = eq_token.position + len(eq_token.value)
        token_start = 2

    # Process remaining tokens
    for i in range(token_start, len(tokens)):
        token = tokens[i]
        if token.type == TokenType.EOF:
            break

        # Fill gap (whitespace/unknown chars) between current pos and token start
        if token.position > pos:
            result.append(expr_text[pos:token.position])

        # Classify and style the token
        style = _classify_token(token, known_variables)

        # Special case: NUMBER with SI suffix — split into number + suffix
        if token.type == TokenType.NUMBER and len(token.value) > 1 and token.value[-1] in _SI_SUFFIXES:
            result.append(token.value[:-1])  # number part, default
            result.append(token.value[-1], style="cyan")
        else:
            if style:
                result.append(token.value, style=style)
            else:
                result.append(token.value)

        pos = token.position + len(token.value)

    # Trailing text after last token
    if pos < len(expr_text):
        result.append(expr_text[pos:])

    return result


def _classify_token(token, known_variables: Set[str]) -> str:
    """Return Rich style string for a token, or empty string for default."""
    if token.type == TokenType.IDENTIFIER:
        lower = token.value.lower()
        # Math functions
        if lower in _MATH_FUNCTIONS:
            return "cyan bold"
        # Keyword glue first (of, off, on, in, to, as, from, before, after)
        if lower in _KEYWORD_GLUE:
            return "dim"
        # Units and date keywords
        if _is_unit(token.value):
            return "#ff69b4"
        # Currency codes (USD, EUR, etc.)
        if _is_currency(token.value):
            return "#ff69b4"
        # Variable references
        if lower in known_variables:
            return "green"
        return ""

    if token.type == TokenType.LINE_REF:
        return "cyan"

    if token.type == TokenType.CURRENCY_SYMBOL:
        return "#ff69b4"

    # NUMBER, OPERATOR, LPAREN, RPAREN, EQUALS — default
    return ""
