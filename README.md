# Reckn

*Pronounced "reckon"*

A Soulver-like calculator notepad for the terminal. Type math expressions on the left, see results on the right - with variables, units, currencies, percentages, dates, and more.

## Install

Requires Python 3.10+.

```bash
pipx install reckn
```

That's it. If you don't have pipx: `pip install pipx` or `sudo apt install pipx` (Debian/Ubuntu) or `brew install pipx` (macOS).

Alternatively, with pip:

```bash
pip install reckn
```

### Linux Desktop Integration

To add Reckn to your application menu:

```bash
reckn --install-desktop
```

### From Source

```bash
git clone https://github.com/davigno/reckn.git
cd reckn
pipx install .
```

## Usage

```bash
reckn                  # New empty pad
reckn mybudget         # Open or create named pad
reckn --list           # List saved pads
reckn --version        # Show version
```

Press `F2` inside the app for a full syntax reference and keyboard shortcuts.

## What Can It Do?

```
# Monthly Budget
salary = 5000                    5,000
tax = 22% of salary                1,100
rent = 1200 EUR                    €1,200
rent in USD                        $1,415.28
---                                5,715.28

# Trip Planning
distance = 450 km                  450 km
distance in miles                  279.62 mi
speed = 100 km/h                   100 km/h
distance / speed as timespan       4 hr 30 min

# Dates
today                              25 March 2026
vacation = June 15                 15 June 2026
vacation - today                   2 months 21 days

# Time & Timezones
meeting = 2:30pm EST               2:30 pm EST
meeting in CET                     8:30 pm CET
now in Tokyo                       2:45 am (Tokyo)
time difference between CET and PST    9 hr
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `F1` | File menu |
| `F2` | Help / syntax reference |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+N` | New pad |
| `Ctrl+O` | Open pad |
| `Ctrl+S` | Save pad |
| `Ctrl+E` | Export as markdown |
| `Ctrl+T` | Toggle floating total |
| `Ctrl+K` | Toggle comment |
| `Ctrl+X` | Delete line |
| `Ctrl+C` | Copy result to clipboard |
| `Ctrl+V` | Paste |
| `Ctrl+Q` | Quit |
| `Click result` | Insert line reference |

## Syntax Reference

### Arithmetic & Variables

```
2 + 3 * (10 - 4)            → 20
2 ^ 10                       → 1,024
100k + 50k                   → 150,000       (SI: k, M, B, G)
salary = 60k                 → 60,000        (variable assignment)
line1 + line2                → (line refs)
```

### Units & Conversions

Convert with `in`, `to`, or `as`. Compatible units mix automatically.

```
10 inches in cm              → 25.4 cm
5 km in miles                → 3.11 mi
100 degC in degF             → 212 °F
1000 MB in GB                → 1 GB
100 km/h in mph              → 62.14 mph
1 km + 500 m                 → 1,500 m
500 km / 2 hours             → 250 km/h
```

**Supported:** length (mm-mi), weight (mg-lb), time (ms-year), data (B-PB, bits), speed, temperature.

### Currencies

Live rates from frankfurter.app, cached locally for offline use.

```
$100 in EUR                  → €84.79
100 GBP to USD               → $135.89
rent = 100 USD               → $100          (unit preserved)
rent * 12                    → $1,200
```

### Percentages

```
25% of 1000                  → 250
10% off 200                  → 180
200 + 10%                    → 220
50 as % of 200               → 25%
```

### Proportions

```
3 is to 6 as what is to 10   → 5
3 is to 6 as 9 is to what    → 18
10 kg is to 20 kg as ? is to 50 kg → 25 kg
```

Use `what`, `x`, or `?` for the unknown. Works with units, currencies, variables, and line references.

### Dates & Clock Time

```
today                        → 25 March 2026
today + 3 weeks              → 15 April 2026
from March 1 to April 1      → 1 month
7:45am + 9 hours             → 4:45 pm
3:35pm - 11:00am             → 4 hr 35 min
5.5 hours as timespan        → 5 hr 30 min
```

### Timezones

```
now in Tokyo                 → 2:45 am (Tokyo)
now in EST                   → 1:45 pm EST
3:30pm CET in PST            → 6:30 am PST
meeting = 2pm EST            → 2:00 pm EST
meeting in CET               → 8:00 pm CET
time difference between CET and PST → 9 hr
Tokyo vs New_York            → 13 hr
```

Use city names or abbreviations (case-insensitive). Ambiguous abbreviations show the default: `CST (US Central)`.

### Math Functions

```
sqrt(144)                    → 12
abs(-42)                     → 42
round(3.14159, 2)            → 3.14
floor(3.9)                   → 3
ceil(3.1)                    → 4
min(10, 20, 5)               → 5
max(3, 7, 1)                 → 7
log(1)                       → 0
log10(100)                   → 2
sin(0) / cos(0)              → 0 / 1
sqrt(144) km                 → 12 km          (unit suffix works)
abs(-50) USD                 → $50            (currency too)
```

### Structure

```
# Heading                    (section header, resets subtotals)
// Comment                   (not evaluated)
label: 1200                  (display only, no variable)
var = 1200                   (variable assignment)
---                          (subtotal)
===                          (subtotal, alternate style)
```

## Data Storage

All data in `~/.config/reckn/`:

- `pads/<name>.json` - saved pads
- `currency_cache.json` - cached exchange rates

## Roadmap

Planned for future releases:

- ~~Math functions~~ (added in v1.1.0)
- ~~Proportions~~ (added in v1.2.0)
- ~~Undo/redo~~ (added in v1.2.0)
- ~~Time zone conversions~~ (added in v1.3.0)
- ~~Multiple tabs~~ (added in v1.4.0)
- ~~Settings menu with themes~~ (added in v1.5.0)
- Sectioned help screen
- Language (i18n) — localized formula keywords (EN, IT, ES, FR, PT, DE)
- Locale — number formatting (decimal/thousands separators)
- Additional display toggles (line numbers, smart spaces, etc.)

## About

I'm a product person, not a developer. This project was built entirely with [Claude Code](https://claude.ai/claude-code) by Anthropic - I brought the idea and the product direction, Claude wrote the code.

## License

MIT
