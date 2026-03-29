"""User settings for Reckn — persisted to ~/.config/reckn/settings.json."""

import json
from dataclasses import dataclass, asdict
from pathlib import Path

SETTINGS_PATH = Path.home() / ".config" / "reckn" / "settings.json"


@dataclass
class Settings:
    theme: str = "textual-dark"
    pads_directory: str = ""  # Empty = default (~/.config/reckn/pads)
    show_totals: bool = True


def load_settings() -> Settings:
    """Load settings from disk. Returns defaults if file missing or invalid."""
    if not SETTINGS_PATH.exists():
        return Settings()
    try:
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
        return Settings(
            theme=data.get("theme", "textual-dark"),
            pads_directory=data.get("pads_directory", ""),
            show_totals=data.get("show_totals", True),
        )
    except (json.JSONDecodeError, IOError):
        return Settings()


def save_settings(settings: Settings) -> None:
    """Save settings to disk."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(asdict(settings), f, indent=2)
