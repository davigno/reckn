"""Expression tokenizer and parser for Reckn."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional
import re


class TokenType(Enum):
    NUMBER = auto()
    IDENTIFIER = auto()
    LINE_REF = auto()
    OPERATOR = auto()
    LPAREN = auto()
    RPAREN = auto()
    EQUALS = auto()
    CURRENCY_SYMBOL = auto()  # $, €, £, ¥ and compound symbols like R$
    COMMA = auto()
    EOF = auto()


# Currency symbols that should be tokenized
CURRENCY_SYMBOLS = {'$', '€', '£', '¥'}
COMPOUND_CURRENCY_PREFIXES = {'R', 'A', 'C', 'HK', 'S', 'NZ', 'MX'}  # R$, A$, etc.


@dataclass
class Token:
    type: TokenType
    value: str
    position: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r})"


class Tokenizer:
    """Breaks input string into tokens."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def peek(self) -> Optional[str]:
        if self.pos < self.length:
            return self.text[self.pos]
        return None

    def advance(self) -> Optional[str]:
        if self.pos < self.length:
            char = self.text[self.pos]
            self.pos += 1
            return char
        return None

    def skip_whitespace(self) -> None:
        while self.peek() and self.peek().isspace():
            self.advance()

    def read_number(self) -> str:
        """Read a number, including decimals and SI suffixes (k, M, G)."""
        start = self.pos
        has_decimal = False

        while self.peek():
            char = self.peek()
            if char.isdigit():
                self.advance()
            elif char == '.' and not has_decimal:
                has_decimal = True
                self.advance()
            elif char == ',':
                # Skip thousand separators in input
                next_pos = self.pos + 1
                if next_pos < self.length and self.text[next_pos].isdigit():
                    self.advance()
                else:
                    break
            else:
                break

        # Check for SI suffix (case-sensitive)
        # k = kilo (1,000), M = mega (1,000,000), G = giga (1,000,000,000), B = billion
        # Note: B is billions when immediately attached to number (1.2B)
        # But "B" with space is bytes unit (100 B), handled separately
        if self.peek() and self.peek() in 'kMGB':
            suffix = self.peek()
            # Make sure it's not part of a longer identifier (like MB, GB, Mbps)
            next_pos = self.pos + 1
            if next_pos >= self.length or not (self.text[next_pos].isalnum() or self.text[next_pos] == '_' or self.text[next_pos] == '/'):
                self.advance()

        return self.text[start:self.pos]

    def read_identifier(self) -> str:
        """Read an identifier (variable name or keyword)."""
        start = self.pos
        while self.peek() and (self.peek().isalnum() or self.peek() in '_-'):
            self.advance()
        return self.text[start:self.pos]

    def tokenize(self) -> List[Token]:
        """Tokenize the entire input string."""
        tokens = []

        while self.pos < self.length:
            self.skip_whitespace()

            if self.pos >= self.length:
                break

            start_pos = self.pos
            char = self.peek()

            # Numbers
            if char.isdigit() or (char == '.' and self.pos + 1 < self.length and self.text[self.pos + 1].isdigit()):
                value = self.read_number()
                tokens.append(Token(TokenType.NUMBER, value, start_pos))

            # Identifiers and line references
            elif char.isalpha() or char == '_':
                value = self.read_identifier()
                # Check if it's a line reference
                if re.match(r'^line\d+$', value, re.IGNORECASE):
                    tokens.append(Token(TokenType.LINE_REF, value, start_pos))
                else:
                    tokens.append(Token(TokenType.IDENTIFIER, value, start_pos))

            # Operators
            elif char in '+-*/^':
                self.advance()
                tokens.append(Token(TokenType.OPERATOR, char, start_pos))

            # Parentheses
            elif char == '(':
                self.advance()
                tokens.append(Token(TokenType.LPAREN, char, start_pos))
            elif char == ')':
                self.advance()
                tokens.append(Token(TokenType.RPAREN, char, start_pos))

            # Assignment
            elif char == '=':
                self.advance()
                tokens.append(Token(TokenType.EQUALS, char, start_pos))

            # Comma (for function arguments)
            elif char == ',':
                self.advance()
                tokens.append(Token(TokenType.COMMA, char, start_pos))

            # Currency symbols
            elif char in CURRENCY_SYMBOLS:
                self.advance()
                tokens.append(Token(TokenType.CURRENCY_SYMBOL, char, start_pos))

            # Compound currency symbols (R$, A$, C$, etc.)
            elif char.isupper() and self.pos + 1 < self.length:
                # Check for two-char prefix like HK, NZ, MX
                if self.pos + 2 < self.length:
                    two_char = self.text[self.pos:self.pos+2]
                    if two_char in COMPOUND_CURRENCY_PREFIXES and self.text[self.pos+2] == '$':
                        self.advance()
                        self.advance()
                        self.advance()
                        tokens.append(Token(TokenType.CURRENCY_SYMBOL, two_char + '$', start_pos))
                        continue
                # Check for single-char prefix like R, A, C, S
                if char in COMPOUND_CURRENCY_PREFIXES and self.text[self.pos+1] == '$':
                    self.advance()
                    self.advance()
                    tokens.append(Token(TokenType.CURRENCY_SYMBOL, char + '$', start_pos))
                    continue
                # Not a currency - skip
                self.advance()

            # Unknown character - skip it
            else:
                self.advance()

        tokens.append(Token(TokenType.EOF, '', self.pos))
        return tokens


@dataclass
class ParseResult:
    """Result of parsing a line."""
    is_assignment: bool = False
    variable_name: Optional[str] = None
    expression_tokens: List[Token] = None
    is_heading: bool = False
    is_comment: bool = False
    error: Optional[str] = None

    def __post_init__(self):
        if self.expression_tokens is None:
            self.expression_tokens = []


class Parser:
    """Parses tokenized expressions."""

    def __init__(self):
        pass

    def parse_line(self, line: str) -> ParseResult:
        """Parse a single line of input."""
        stripped = line.strip()

        # Check for heading
        if stripped.startswith('#'):
            return ParseResult(is_heading=True)

        # Check for comment
        if stripped.startswith('//'):
            return ParseResult(is_comment=True)

        # Strip label if present (text followed by : at start)
        label_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*', stripped)
        if label_match:
            stripped = stripped[label_match.end():]

        if not stripped:
            return ParseResult()

        # Tokenize
        tokenizer = Tokenizer(stripped)
        tokens = tokenizer.tokenize()

        # Check for variable assignment: identifier = expression
        if (len(tokens) >= 3 and
            tokens[0].type == TokenType.IDENTIFIER and
            tokens[1].type == TokenType.EQUALS):
            return ParseResult(
                is_assignment=True,
                variable_name=tokens[0].value,
                expression_tokens=tokens[2:]  # Everything after the =
            )

        return ParseResult(expression_tokens=tokens)


def expand_si_suffix(value: str) -> float:
    """
    Convert a number string with SI suffix to float.

    Case-sensitive SI prefixes:
    - k (lowercase) = 1,000 (kilo)
    - M (uppercase) = 1,000,000 (mega)
    - G (uppercase) = 1,000,000,000 (giga)
    - B (uppercase) = 1,000,000,000 (billion - common in finance)

    Note: B for billions only applies when attached directly to number (1.2B).
    "B" with space (100 B) is handled as bytes unit separately.
    """
    value = value.replace(',', '')  # Remove thousand separators

    if not value:
        return 0.0

    # Case-sensitive SI/number prefixes
    suffix_multipliers = {
        'k': 1_000,           # kilo (lowercase only)
        'M': 1_000_000,       # mega (uppercase only)
        'G': 1_000_000_000,   # giga (uppercase only)
        'B': 1_000_000_000,   # billion (uppercase only, common in finance)
    }

    last_char = value[-1]
    if last_char in suffix_multipliers:
        base = float(value[:-1])
        return base * suffix_multipliers[last_char]

    return float(value)
