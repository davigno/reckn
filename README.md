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

# Time
meeting = 2:30pm                   2:30 pm
meeting + 1 hr 45 min              4:15 pm
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `F1` | File menu |
| `F2` | Help / syntax reference |
| `Ctrl+N` | New pad |
| `Ctrl+O` | Open pad |
| `Ctrl+S` | Save pad |
| `Ctrl+E` | Export as markdown |
| `Ctrl+T` | Toggle floating total |
| `Ctrl+K` | Toggle comment |
| `Ctrl+X` | Delete line |
| `Ctrl+C` | Copy result |
| `Ctrl+Shift+C` | Copy entire pad |
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

### Dates & Clock Time

```
today                        → 25 March 2026
today + 3 weeks              → 15 April 2026
from March 1 to April 1      → 1 month
7:45am + 9 hours             → 4:45 pm
3:35pm - 11:00am             → 4 hr 35 min
5.5 hours as timespan        → 5 hr 30 min
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

## License

MIT
