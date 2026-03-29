# Reckn - Project Context for Claude Code

## Project Overview

Reckn is a terminal-based calculator notepad inspired by [Soulver](https://soulver.app). Users type natural-language math expressions on the left side, and results appear in real-time on the right - like a spreadsheet merged with a scratchpad. It supports variables, units, currencies, percentages, and line references.

**Repository:** `/home/david/Development/claude_code/reckn`
**Version:** 1.0.0
**Status:** Phase 1 complete, versioned release

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| UI Framework | Textual (terminal UI) |
| Currency Rates | frankfurter.app (free, no API key) |
| Data Storage | JSON files in `~/.config/reckn/pads/` |
| Package Management | pyproject.toml with setuptools |

## Project Structure

```
reckn/
├── CLAUDE.md              # This file - project context for Claude
├── SPEC.md                # Original product specification
├── README.md              # User-facing documentation
├── pyproject.toml         # Package configuration, dependencies
├── test_input.txt         # Test cases for manual testing
└── reckn/
    ├── __init__.py        # Package marker, __version__
    ├── __main__.py        # CLI entry point (argparse, --version, --install-desktop)
    ├── app.py             # Textual app: UI layout, keybindings, screens
    ├── parser.py          # Tokenizer: text → tokens (NUMBER, IDENTIFIER, etc.)
    ├── evaluator.py       # Evaluator: tokens → Value objects, arithmetic
    ├── value.py           # Value and Unit dataclasses (unit-aware results)
    ├── units.py           # Unit definitions, conversion logic, rate formation
    ├── currencies.py      # Currency fetching, caching, symbol mapping
    ├── percentages.py     # Percentage expression patterns
    ├── proportions.py     # Proportion expressions (A is to B as X is to D)
    ├── timezones.py       # Timezone data, lookups, conversion (zoneinfo)
    ├── dates.py           # Date/calendar math, clock time, timespan support
    ├── highlighter.py     # Syntax highlighting for editor lines (Rich Text)
    ├── clipboard.py       # System clipboard (xclip/xsel/pyperclip fallback)
    ├── pad.py             # Pad model: save/load JSON, file management
    ├── assets/
    │   └── reckn.svg      # Application icon for desktop integration
    └── test_repl.py       # Simple REPL for testing evaluator
```

## Architecture Decisions

### 1. Unit-Aware Values

Values carry their unit metadata through all operations:

```python
@dataclass
class Value:
    value: Union[float, date, DateInterval, ClockTime]
    unit: Optional[Unit] = None  # e.g., Unit.simple("km", "length")
```

This allows:
- `rent = 100 USD` stores `Value(100, Unit.currency("USD"))`
- `rent * 12` returns `Value(1200, Unit.currency("USD"))` → displays as `$1,200`
- `rent in EUR` converts using the stored unit

### 2. Case-Sensitive Unit Symbols

Unit symbols are case-sensitive because casing carries meaning:
- `km` = kilometers, `Km` = invalid
- `MB` = megabytes, `Mb` = megabits
- `K` = Kelvin, `k` = kilo prefix (1000)
- `B` = bytes, `b` = bits

Full word aliases (`kilometers`, `megabytes`) are case-insensitive.

### 3. Single-Token Variables Only

Variables must be single tokens using underscores, hyphens, or camelCase:
- Valid: `monthly_rent`, `tax-rate`, `taxRate`
- Invalid: `monthly rent` (would be parsed as two tokens)

This simplifies parsing and avoids ambiguity with unit expressions.

### 4. Reserved Words System

Unit names and currency codes are reserved - they cannot be used as variable names:
- `meter = 5` → would conflict with "meter" unit
- `USD = 100` → would conflict with USD currency

The evaluator checks `is_known_unit()` and `is_known_currency()` before treating identifiers as variables.

### 5. Currency Caching Strategy

- **Async fetch:** Rates are fetched in a background thread on app startup (never blocks UI)
- **Session cache:** Rates stored in `CurrencyConverter` instance
- **Disk cache:** `~/.config/reckn/currency_cache.json`
- **Loading state:** Currency lines show "loading..." while rates are being fetched
- **Auto re-evaluation:** When rates arrive, all lines re-evaluate automatically
- **Retry interval:** 10 minutes between failed fetch attempts (background, non-blocking)
- **Offline mode:** Uses cached rates if available; status bar shows `[offline]` if no rates at all

### 6. Number Formatting

- Thousand separators: `1,000,000`
- Trailing zeros stripped: `1.5` not `1.500000`
- Scientific notation for very large/small: `1e+308`, `1e-07`
- Currencies: 2 decimal places with symbol prefix (`$100.00`)

## Parser Pipeline

```
Input Line
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. PRE-PROCESS (in Parser.parse_line)                       │
│    - Skip if starts with # (heading) or // (comment)        │
│    - Strip labels (text before : at line start)             │
│    - Detect variable assignment (identifier = expression)   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. TOKENIZE (in Tokenizer.tokenize)                         │
│    - NUMBER: digits, decimals, SI suffixes (100k, 2.5M)     │
│    - IDENTIFIER: variable names, unit names, keywords       │
│    - LINE_REF: line1, line2, etc.                           │
│    - OPERATOR: + - * / ^                                    │
│    - CURRENCY_SYMBOL: $ € £ ¥ R$ A$ etc.                    │
│    - LPAREN, RPAREN, EQUALS, EOF                            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. PARSE (in Evaluator - recursive descent)                 │
│    Grammar (precedence low to high):                        │
│    conversion  → expression (("in"|"to"|"as") unit)?        │
│    expression  → term (('+' | '-') term)*                   │
│    term        → power (('*' | '/') power)*                 │
│    power       → unary ('^' power)?                         │
│    unary       → ('+' | '-')? primary                       │
│    primary     → NUMBER unit? | IDENTIFIER | LINE_REF | ()  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. EVALUATE (returns Value object)                          │
│    - Resolve variables from EvaluationContext               │
│    - Resolve line references from stored results            │
│    - Apply arithmetic with unit propagation                 │
│    - Handle unit conversions                                │
│    - Store result in context for line refs                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. FORMAT (format_value)                                    │
│    - Plain numbers: thousand separators                     │
│    - Currencies: symbol + 2 decimals ($100.00)              │
│    - Units: number + unit suffix (100 km)                   │
│    - Dates: "12 June 2025"                                  │
│    - Clock times: "7:45 am"                                 │
│    - Timespans: "5 hr 30 min"                               │
└─────────────────────────────────────────────────────────────┘
```

**Special cases:** Clock time, date, and percentage expressions are handled by dedicated pre-parsers before the main evaluator (in that order), as they have patterns that require regex matching on the raw expression text before tokenization.

## What's Implemented (Phase 1)

| Feature | Status | Module |
|---------|--------|--------|
| Basic arithmetic (+, -, *, /, ^, parentheses) | ✅ | evaluator.py |
| Variables (single-token, case-insensitive) | ✅ | evaluator.py |
| Line references (line1, line2, ...) | ✅ | evaluator.py |
| SI notation (100k, 2.5M, 1.2B, 1.2G) | ✅ | parser.py |
| Headings (#) and comments (//) | ✅ | parser.py |
| Labels (text: value) | ✅ | parser.py |
| Unit conversions (length, weight, time, data, temp, speed) | ✅ | units.py |
| Unit arithmetic (1 km + 500 m) | ✅ | units.py |
| Rate formation (100 km / 2 hr → 50 km/h) | ✅ | units.py |
| Unit-aware variables (rent = 100 USD, rent * 12) | ✅ | value.py, evaluator.py |
| Currency conversion with live rates | ✅ | currencies.py |
| Currency symbols ($, €, £, ¥) | ✅ | parser.py, evaluator.py |
| Percentage expressions (25% of, 10% off, etc.) | ✅ | percentages.py |
| Real-time evaluation with debounce | ✅ | app.py |
| Save/load pads (Ctrl+S, Ctrl+O) | ✅ | pad.py, app.py |
| New pad (Ctrl+N), Quit (Ctrl+Q) | ✅ | app.py |
| Export as markdown (Ctrl+E) | ✅ | app.py |
| Subtotals (--- or ===) | ✅ | evaluator.py, app.py |
| Floating total (Ctrl+T toggle) | ✅ | evaluator.py, app.py |
| Click result to insert line reference | ✅ | app.py |
| Toggle comment (Ctrl+K) | ✅ | app.py |
| Delete line (Ctrl+X) | ✅ | app.py |
| Dynamic scrolling (up to 100 lines) | ✅ | app.py |
| Date keywords (today, yesterday, tomorrow, now) | ✅ | dates.py, evaluator.py |
| Date literals (June 12, 2025-06-12, etc.) | ✅ | dates.py |
| Date arithmetic (today + 3 weeks, June 12 + 3 months 5 days) | ✅ | dates.py, evaluator.py |
| Natural language date math (4 days from now, 3 weeks after March 14) | ✅ | dates.py |
| Date intervals (from March 12 to July 30) | ✅ | dates.py |
| Date variables and line references | ✅ | dates.py, evaluator.py |
| Clock time parsing (7:45am, 15:35, now) | ✅ | dates.py, evaluator.py |
| Clock time arithmetic (7:45am + 9 hours, 3:35pm - 11:00am) | ✅ | dates.py, evaluator.py |
| Timespan formatting (5.5 hours as timespan) | ✅ | dates.py, evaluator.py |
| Clock time variables and line references | ✅ | dates.py, evaluator.py |
| Copy result to clipboard (Ctrl+C) | ✅ | clipboard.py, app.py |
| Paste from clipboard (Ctrl+V) | ✅ | clipboard.py, app.py |
| CLI with argparse (reckn, reckn name, --list) | ✅ | __main__.py |
| Number formatting (thousands, decimals, scientific) | ✅ | evaluator.py |
| Proportions (3 is to 6 as what is to 10) | ✅ | proportions.py |
| Undo/redo (Ctrl+Z / Ctrl+Y) | ✅ | app.py (Editor) |
| Timezone conversions (now in Tokyo, CET - PST) | ✅ | timezones.py, dates.py |

## Phase 2 Features (Not Yet Implemented)

From SPEC.md - these are future enhancements:

- Multiple tabs/sheets
- Sectioned help screen (navigable tabs/sections — help is getting long)
- Export to CSV
- Custom user-defined units
- Settings menu (language/i18n, locale/number formatting, themes, pads directory, display toggles)

## Testing

### Manual Testing

```bash
# Activate virtual environment
source .venv/bin/activate

# Run test REPL with test file
python reckn/test_repl.py test_input.txt

# Interactive REPL mode
python reckn/test_repl.py

# Run the app
reckn
```

### Test File

`test_input.txt` contains comprehensive test cases for all features. Check that all lines produce expected results.

### Unit Tests

No pytest suite yet. Testing is done via:
1. `test_repl.py` with `test_input.txt`
2. Manual testing in the app
3. Inline Python testing of specific functions

## Known Limitations & Quirks

### Parsing Limitations

1. **Rate units in expressions:** `100 km/h` is tokenized as `100`, `km`, `/`, `h`. The evaluator special-cases this to recognize it as a rate unit.

2. **"in" keyword ambiguity:** `in` is both a conversion keyword AND the inches unit. The parser prioritizes the conversion meaning when it follows a value.

3. **Percentage patterns:** Percentages use regex pattern matching, not the recursive descent parser. Sub-expressions like `25% of (100 + 50)` are supported via an `evaluate_expr` callback passed to the percentage parser.

### Unit Limitations

1. **Compound units:** Only simple rates (X/Y) are supported. Complex units like `kg*m/s^2` aren't handled.

2. **Unit multiplication:** `100 km * 2 km` creates `km*km` but there's no area unit to convert to.

3. **Temperature:** Non-linear conversions (C↔F↔K) are special-cased, not using the standard base-unit approach.

### Currency Limitations

1. **Rate updates:** Rates are cached for the session. Restart app for fresh rates.

2. **Limited symbols:** Only common symbols ($, €, £, ¥, R$, A$, C$, etc.) are recognized. Others must use ISO codes.

## Code Style Notes

- **Imports:** Use try/except for relative vs absolute imports (supports both `python -m reckn` and direct script execution)
- **Type hints:** Used throughout but not complete. `Value` and `Unit` are the core types.
- **Error handling:** Evaluation catches specific exceptions and returns None/empty for invalid expressions
- **Lazy loading:** Currency and unit modules are lazy-loaded to avoid circular imports

## Common Development Tasks

### Adding a New Unit

1. Edit `reckn/units.py`
2. Use `_register_unit(category, base_value, symbol, *word_aliases)`
3. Example: `_register_unit("length", 1852, "nmi", "nautical mile", "nautical miles")`

### Adding a New Currency Symbol

1. Edit `reckn/currencies.py`
2. Add to `SYMBOL_TO_ISO` dict
3. Add to `ISO_TO_SYMBOL` for display

### Adding a New Percentage Pattern

1. Edit `reckn/percentages.py`
2. Add a new `_try_*` function
3. Call it from `try_parse_percentage_expression()`

### Debugging Evaluation

```python
from reckn.parser import Parser
from reckn.evaluator import Evaluator, EvaluationContext

p = Parser()
result = p.parse_line("100 km in miles")
print("Tokens:", [(t.type.name, t.value) for t in result.expression_tokens])

ctx = EvaluationContext()
e = Evaluator(ctx)
val = e.evaluate(result.expression_tokens)
print("Result:", val)
```
