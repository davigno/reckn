"""Currency conversion with live rates for Reckn."""

import json
import os
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Callable
import re

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


@dataclass
class CurrencyResult:
    """Result of a currency conversion."""
    value: float
    currency: str  # ISO code for display
    symbol: str    # Symbol for display (e.g., €, $)
    error: bool = False
    error_message: str = ""


# Currency symbol to ISO code mapping
# The "owner" of each symbol is the most common currency using it
SYMBOL_TO_ISO = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    # Compound symbols
    "R$": "BRL",
    "A$": "AUD",
    "C$": "CAD",
    "HK$": "HKD",
    "S$": "SGD",
    "NZ$": "NZD",
    "MX$": "MXN",
}

# ISO code to display symbol mapping
ISO_TO_SYMBOL = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "BRL": "R$",
    "AUD": "A$",
    "CAD": "C$",
    "HKD": "HK$",
    "SGD": "S$",
    "NZD": "NZ$",
    "MXN": "MX$",
}

# Cache configuration
CACHE_DIR = Path.home() / ".config" / "reckn"
CACHE_FILE = CACHE_DIR / "currency_cache.json"
API_BASE_URL = "https://api.frankfurter.app"
RETRY_INTERVAL = 600  # 10 minutes in seconds


class CurrencyConverter:
    """Handles currency conversion with rate caching."""

    def __init__(self):
        self.rates: Dict[str, float] = {}  # Rates relative to EUR (API base)
        self.base_currency = "EUR"
        self.last_fetch_time: float = 0
        self.last_fetch_failed: bool = False
        self.is_offline: bool = False
        self.is_loading: bool = False
        self._fetch_thread: Optional[threading.Thread] = None
        self._load_cached_rates()

    def _load_cached_rates(self) -> None:
        """Load rates from disk cache."""
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    self.rates = data.get("rates", {})
                    self.base_currency = data.get("base", "EUR")
                    self.last_fetch_time = data.get("timestamp", 0)
        except (json.JSONDecodeError, IOError):
            pass

    def _save_cached_rates(self) -> None:
        """Save rates to disk cache."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, 'w') as f:
                json.dump({
                    "rates": self.rates,
                    "base": self.base_currency,
                    "timestamp": self.last_fetch_time,
                }, f)
        except IOError:
            pass

    def fetch_rates(self) -> bool:
        """
        Fetch latest rates from API.
        Returns True if successful, False otherwise.
        """
        if not HAS_REQUESTS:
            self.is_offline = True
            return False

        try:
            response = requests.get(
                f"{API_BASE_URL}/latest",
                timeout=5
            )
            response.raise_for_status()
            data = response.json()

            self.rates = data.get("rates", {})
            self.base_currency = data.get("base", "EUR")
            # Add the base currency itself with rate 1
            self.rates[self.base_currency] = 1.0
            self.last_fetch_time = time.time()
            self.last_fetch_failed = False
            self.is_offline = False

            self._save_cached_rates()
            return True

        except Exception:
            self.last_fetch_failed = True
            self.is_offline = True
            return False

    def fetch_rates_in_background(self, on_complete: Optional[Callable] = None) -> None:
        """Fetch rates in a daemon thread. Calls on_complete(success) when done."""
        if self.is_loading:
            return
        self.is_loading = True

        def _worker():
            try:
                success = self.fetch_rates()
            except Exception:
                success = False
            finally:
                self.is_loading = False
            if on_complete:
                on_complete(success)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        self._fetch_thread = t

    def should_retry_fetch(self) -> bool:
        """Check if we should retry fetching rates."""
        if not self.last_fetch_failed:
            return False
        return time.time() - self.last_fetch_time >= RETRY_INTERVAL

    def ensure_rates(self) -> bool:
        """
        Check if rates are available. Non-blocking — never fetches synchronously.
        Returns True if rates are available (from cache or prior fetch).
        """
        if self.rates:
            # Trigger background retry if prior fetch failed and it's been 10+ min
            if self.last_fetch_failed and self.should_retry_fetch() and not self.is_loading:
                self.fetch_rates_in_background()
            return True
        # No rates available yet
        return False

    def get_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        """
        Get conversion rate between two currencies.
        Returns None if rate is not available.
        """
        if not self.ensure_rates():
            return None

        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        # Get rates relative to base (EUR)
        from_rate = self.rates.get(from_currency)
        to_rate = self.rates.get(to_currency)

        if from_rate is None or to_rate is None:
            return None

        # Convert: amount in from_currency -> EUR -> to_currency
        # from_rate is EUR per 1 from_currency
        # to_rate is EUR per 1 to_currency
        # So: amount * (to_rate / from_rate) gives amount in to_currency
        return to_rate / from_rate

    def convert(self, amount: float, from_currency: str, to_currency: str) -> Optional[CurrencyResult]:
        """
        Convert an amount between currencies.
        Returns CurrencyResult or None if conversion not possible.
        """
        rate = self.get_rate(from_currency, to_currency)

        if rate is None:
            if self.is_offline and not self.rates:
                return CurrencyResult(
                    value=0, currency=to_currency, symbol="",
                    error=True, error_message="no rate"
                )
            return None

        result_value = amount * rate
        to_iso = to_currency.upper()
        to_symbol = ISO_TO_SYMBOL.get(to_iso, "")

        return CurrencyResult(
            value=result_value,
            currency=to_iso,
            symbol=to_symbol
        )


# Global converter instance
_converter: Optional[CurrencyConverter] = None


def get_converter() -> CurrencyConverter:
    """Get or create the global currency converter."""
    global _converter
    if _converter is None:
        _converter = CurrencyConverter()
    return _converter


def normalize_currency(currency_str: str) -> Optional[str]:
    """
    Normalize a currency string to ISO code.
    Accepts symbols ($, €, £, R$, etc.) or ISO codes (USD, EUR, GBP, etc.).
    Returns None if not recognized.
    """
    currency_str = currency_str.strip()

    # Check if it's a known symbol
    if currency_str in SYMBOL_TO_ISO:
        return SYMBOL_TO_ISO[currency_str]

    # Check if it's an ISO code (3 uppercase letters)
    upper = currency_str.upper()
    if len(upper) == 3 and upper.isalpha():
        return upper

    return None


def try_parse_currency_expression(expression: str, resolve_var: Callable) -> Optional[CurrencyResult]:
    """
    Try to parse and evaluate a currency conversion expression.

    Patterns:
    - "100 USD in EUR"
    - "100$ in €"
    - "100 $ to EUR"
    - "$100 in EUR"
    - "€50 to USD"

    Args:
        expression: The expression string to parse
        resolve_var: Function to resolve variable names to values

    Returns:
        CurrencyResult if this is a currency conversion, None otherwise
    """
    expression = expression.strip()

    # Pattern 1: <number> <currency> (in|to|as) <currency>
    # Handles: 100 USD in EUR, 100$ in €, 100 $ to EUR
    pattern1 = r'^([\d,]+\.?\d*)\s*([A-Za-z$€£¥]+\$?)\s+(?:in|to|as)\s+([A-Za-z$€£¥]+\$?)$'
    match = re.match(pattern1, expression, re.IGNORECASE)

    if match:
        amount_str = match.group(1).replace(',', '')
        from_curr = match.group(2)
        to_curr = match.group(3)

        try:
            amount = float(amount_str)
        except ValueError:
            return None

        from_iso = normalize_currency(from_curr)
        to_iso = normalize_currency(to_curr)

        if from_iso and to_iso:
            return get_converter().convert(amount, from_iso, to_iso)

    # Pattern 2: <symbol><number> (in|to|as) <currency>
    # Handles: $100 in EUR, €50 to USD, £30 in USD
    pattern2 = r'^([A-Z]{0,2}[$€£¥])\s*([\d,]+\.?\d*)\s+(?:in|to|as)\s+([A-Za-z$€£¥]+\$?)$'
    match = re.match(pattern2, expression, re.IGNORECASE)

    if match:
        from_symbol = match.group(1)
        amount_str = match.group(2).replace(',', '')
        to_curr = match.group(3)

        try:
            amount = float(amount_str)
        except ValueError:
            return None

        from_iso = normalize_currency(from_symbol)
        to_iso = normalize_currency(to_curr)

        if from_iso and to_iso:
            return get_converter().convert(amount, from_iso, to_iso)

    # Pattern 3: Variable-based conversion
    # Handles: price USD in EUR (where price is a variable)
    pattern3 = r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s+([A-Za-z$€£¥]+\$?)\s+(?:in|to|as)\s+([A-Za-z$€£¥]+\$?)$'
    match = re.match(pattern3, expression, re.IGNORECASE)

    if match:
        var_name = match.group(1)
        from_curr = match.group(2)
        to_curr = match.group(3)

        amount = resolve_var(var_name)
        if amount is None:
            return None

        from_iso = normalize_currency(from_curr)
        to_iso = normalize_currency(to_curr)

        if from_iso and to_iso:
            return get_converter().convert(amount, from_iso, to_iso)

    return None


def is_currency(s: str) -> bool:
    """Check if a string is a recognized currency symbol or code."""
    return normalize_currency(s) is not None


def get_all_currency_codes() -> set:
    """Get all known currency codes and symbols (for reserved words)."""
    codes = set(SYMBOL_TO_ISO.keys())
    codes.update(SYMBOL_TO_ISO.values())
    codes.update(ISO_TO_SYMBOL.keys())
    return codes


def format_currency_result(result: CurrencyResult) -> str:
    """Format a currency result for display."""
    if result.error:
        return result.error_message

    # Format the value
    if result.value == int(result.value):
        formatted_value = f"{int(result.value):,}"
    else:
        formatted_value = f"{result.value:,.2f}"

    # Use symbol if available, otherwise ISO code
    if result.symbol:
        return f"{formatted_value} {result.symbol}"
    else:
        return f"{formatted_value} {result.currency}"
