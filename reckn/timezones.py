"""Timezone data, lookups, and conversion for Reckn.

Uses Python's zoneinfo module (3.10+) for DST-aware conversions.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Tuple


# Abbreviation → list of (iana_id, display_label, is_default)
# First entry with is_default=True is the default for ambiguous abbreviations.
ABBREVIATIONS: dict[str, list[tuple[str, str, bool]]] = {
    # Universal
    "utc": [("UTC", "UTC", True)],
    "gmt": [("Europe/London", "GMT", True)],

    # North America
    "est": [("America/New_York", "EST", True)],
    "edt": [("America/New_York", "EDT", True)],
    "cst": [("America/Chicago", "US Central", True), ("Asia/Shanghai", "China", False)],
    "cdt": [("America/Chicago", "CDT", True)],
    "mst": [("America/Denver", "MST", True)],
    "mdt": [("America/Denver", "MDT", True)],
    "pst": [("America/Los_Angeles", "PST", True)],
    "pdt": [("America/Los_Angeles", "PDT", True)],
    "akst": [("America/Anchorage", "AKST", True)],
    "akdt": [("America/Anchorage", "AKDT", True)],
    "hst": [("Pacific/Honolulu", "HST", True)],
    "ast": [("America/Halifax", "AST", True)],

    # Europe
    "cet": [("Europe/Paris", "CET", True)],
    "cest": [("Europe/Paris", "CEST", True)],
    "eet": [("Europe/Athens", "EET", True)],
    "eest": [("Europe/Athens", "EEST", True)],
    "wet": [("Europe/Lisbon", "WET", True)],
    "west": [("Europe/Lisbon", "WEST", True)],
    "bst": [("Europe/London", "British Summer", True), ("Asia/Dhaka", "Bangladesh", False)],
    "ist": [("Asia/Kolkata", "India", True), ("Europe/Dublin", "Ireland", False), ("Asia/Jerusalem", "Israel", False)],
    "msk": [("Europe/Moscow", "MSK", True)],

    # Asia
    "jst": [("Asia/Tokyo", "JST", True)],
    "kst": [("Asia/Seoul", "KST", True)],
    "hkt": [("Asia/Hong_Kong", "HKT", True)],
    "sgt": [("Asia/Singapore", "SGT", True)],
    "pht": [("Asia/Manila", "PHT", True)],
    "ict": [("Asia/Bangkok", "ICT", True)],
    "wib": [("Asia/Jakarta", "WIB", True)],
    "wit": [("Asia/Jayapura", "WIT", True)],
    "wita": [("Asia/Makassar", "WITA", True)],

    # Oceania
    "aest": [("Australia/Sydney", "AEST", True)],
    "aedt": [("Australia/Sydney", "AEDT", True)],
    "acst": [("Australia/Adelaide", "ACST", True)],
    "awst": [("Australia/Perth", "AWST", True)],
    "nzst": [("Pacific/Auckland", "NZST", True)],
    "nzdt": [("Pacific/Auckland", "NZDT", True)],
}

# City name → (iana_id, display_label)
# All keys are lowercase. Underscores replace spaces.
CITIES: dict[str, tuple[str, str]] = {
    # North America
    "new_york": ("America/New_York", "New York"),
    "los_angeles": ("America/Los_Angeles", "Los Angeles"),
    "chicago": ("America/Chicago", "Chicago"),
    "denver": ("America/Denver", "Denver"),
    "toronto": ("America/Toronto", "Toronto"),
    "vancouver": ("America/Vancouver", "Vancouver"),
    "mexico_city": ("America/Mexico_City", "Mexico City"),
    "anchorage": ("America/Anchorage", "Anchorage"),
    "honolulu": ("Pacific/Honolulu", "Honolulu"),
    "miami": ("America/New_York", "Miami"),
    "san_francisco": ("America/Los_Angeles", "San Francisco"),

    # South America
    "sao_paulo": ("America/Sao_Paulo", "Sao Paulo"),
    "buenos_aires": ("America/Argentina/Buenos_Aires", "Buenos Aires"),
    "bogota": ("America/Bogota", "Bogota"),
    "lima": ("America/Lima", "Lima"),
    "santiago": ("America/Santiago", "Santiago"),

    # Europe
    "london": ("Europe/London", "London"),
    "paris": ("Europe/Paris", "Paris"),
    "berlin": ("Europe/Berlin", "Berlin"),
    "rome": ("Europe/Rome", "Rome"),
    "madrid": ("Europe/Madrid", "Madrid"),
    "amsterdam": ("Europe/Amsterdam", "Amsterdam"),
    "brussels": ("Europe/Brussels", "Brussels"),
    "zurich": ("Europe/Zurich", "Zurich"),
    "vienna": ("Europe/Vienna", "Vienna"),
    "lisbon": ("Europe/Lisbon", "Lisbon"),
    "moscow": ("Europe/Moscow", "Moscow"),
    "istanbul": ("Europe/Istanbul", "Istanbul"),
    "athens": ("Europe/Athens", "Athens"),
    "dublin": ("Europe/Dublin", "Dublin"),
    "stockholm": ("Europe/Stockholm", "Stockholm"),
    "oslo": ("Europe/Oslo", "Oslo"),
    "helsinki": ("Europe/Helsinki", "Helsinki"),
    "warsaw": ("Europe/Warsaw", "Warsaw"),
    "prague": ("Europe/Prague", "Prague"),
    "copenhagen": ("Europe/Copenhagen", "Copenhagen"),
    "bucharest": ("Europe/Bucharest", "Bucharest"),

    # Asia
    "tokyo": ("Asia/Tokyo", "Tokyo"),
    "seoul": ("Asia/Seoul", "Seoul"),
    "beijing": ("Asia/Shanghai", "Beijing"),
    "shanghai": ("Asia/Shanghai", "Shanghai"),
    "hong_kong": ("Asia/Hong_Kong", "Hong Kong"),
    "singapore": ("Asia/Singapore", "Singapore"),
    "mumbai": ("Asia/Kolkata", "Mumbai"),
    "delhi": ("Asia/Kolkata", "Delhi"),
    "dubai": ("Asia/Dubai", "Dubai"),
    "bangkok": ("Asia/Bangkok", "Bangkok"),
    "jakarta": ("Asia/Jakarta", "Jakarta"),
    "manila": ("Asia/Manila", "Manila"),
    "kuala_lumpur": ("Asia/Kuala_Lumpur", "Kuala Lumpur"),
    "taipei": ("Asia/Taipei", "Taipei"),
    "tel_aviv": ("Asia/Jerusalem", "Tel Aviv"),
    "riyadh": ("Asia/Riyadh", "Riyadh"),
    "karachi": ("Asia/Karachi", "Karachi"),

    # Oceania
    "sydney": ("Australia/Sydney", "Sydney"),
    "melbourne": ("Australia/Melbourne", "Melbourne"),
    "perth": ("Australia/Perth", "Perth"),
    "brisbane": ("Australia/Brisbane", "Brisbane"),
    "auckland": ("Pacific/Auckland", "Auckland"),

    # Africa
    "cairo": ("Africa/Cairo", "Cairo"),
    "lagos": ("Africa/Lagos", "Lagos"),
    "johannesburg": ("Africa/Johannesburg", "Johannesburg"),
    "nairobi": ("Africa/Nairobi", "Nairobi"),
    "casablanca": ("Africa/Casablanca", "Casablanca"),
}

# Build a set of all known timezone names for fast lookup
_ALL_NAMES: set[str] = set(ABBREVIATIONS.keys()) | set(CITIES.keys())


def is_known_timezone(name: str) -> bool:
    """Check if a name is a recognized timezone abbreviation or city."""
    return name.lower().replace(" ", "_") in _ALL_NAMES


def resolve_timezone(name: str) -> Optional[Tuple[str, str, bool]]:
    """Resolve a timezone name to (iana_id, display_label, is_ambiguous).

    Checks cities first (never ambiguous), then abbreviations.
    Returns None if the name is not a recognized timezone.
    """
    key = name.lower().replace(" ", "_")

    # Cities are never ambiguous
    if key in CITIES:
        iana_id, label = CITIES[key]
        return (iana_id, label, False)

    # Abbreviations may be ambiguous
    if key in ABBREVIATIONS:
        entries = ABBREVIATIONS[key]
        # Find the default entry
        for iana_id, label, is_default in entries:
            if is_default:
                is_ambiguous = len(entries) > 1
                if is_ambiguous:
                    display = f"{name.upper()} ({label})"
                else:
                    display = label
                return (iana_id, display, is_ambiguous)

    return None


def convert_clock_time(hour: int, minute: int,
                       source_iana: Optional[str],
                       target_iana: str) -> Tuple[int, int]:
    """Convert a clock time from source timezone to target timezone.

    Args:
        hour: Hour (0-23)
        minute: Minute (0-59)
        source_iana: Source IANA timezone ID, or None for local time
        target_iana: Target IANA timezone ID

    Returns:
        (hour, minute) in the target timezone
    """
    today = datetime.now().date()

    if source_iana:
        # Create timezone-aware datetime in source zone
        source_tz = ZoneInfo(source_iana)
        dt = datetime(today.year, today.month, today.day, hour, minute, tzinfo=source_tz)
    else:
        # Create naive datetime (local time), make it aware
        naive = datetime(today.year, today.month, today.day, hour, minute)
        dt = naive.astimezone()  # Converts to system local timezone (aware)

    # Convert to target timezone
    target_tz = ZoneInfo(target_iana)
    converted = dt.astimezone(target_tz)

    return (converted.hour, converted.minute)


def timezone_offset_hours(tz1_iana: str, tz2_iana: str) -> float:
    """Calculate the offset difference between two timezones in hours.

    Returns tz1_offset - tz2_offset. Positive means tz1 is ahead.
    For example, CET - PST = +9.0 hours.
    """
    now = datetime.now(timezone.utc)

    tz1 = ZoneInfo(tz1_iana)
    tz2 = ZoneInfo(tz2_iana)

    offset1 = now.astimezone(tz1).utcoffset()
    offset2 = now.astimezone(tz2).utcoffset()

    diff_seconds = offset1.total_seconds() - offset2.total_seconds()
    return diff_seconds / 3600
