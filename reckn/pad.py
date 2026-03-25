"""Pad model for save/load operations."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, asdict


PADS_DIR = Path.home() / ".config" / "reckn" / "pads"


@dataclass
class Pad:
    """Represents a saved pad."""
    name: str
    lines: List[str]
    created: str
    modified: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Pad":
        """Create from dictionary."""
        return cls(
            name=data.get("name", "untitled"),
            lines=data.get("lines", []),
            created=data.get("created", datetime.now().isoformat()),
            modified=data.get("modified", datetime.now().isoformat()),
        )

    @classmethod
    def new(cls, name: str = "untitled") -> "Pad":
        """Create a new empty pad."""
        now = datetime.now().isoformat()
        return cls(name=name, lines=[], created=now, modified=now)


def ensure_pads_dir() -> None:
    """Ensure the pads directory exists."""
    PADS_DIR.mkdir(parents=True, exist_ok=True)


def get_pad_path(name: str) -> Path:
    """Get the file path for a pad."""
    # Sanitize name for filesystem
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ").strip()
    if not safe_name:
        safe_name = "untitled"
    return PADS_DIR / f"{safe_name}.json"


def save_pad(pad: Pad) -> Path:
    """Save a pad to disk. Returns the path."""
    ensure_pads_dir()
    pad.modified = datetime.now().isoformat()

    path = get_pad_path(pad.name)
    with open(path, 'w') as f:
        json.dump(pad.to_dict(), f, indent=2)

    return path


def load_pad(name: str) -> Optional[Pad]:
    """Load a pad from disk by name."""
    path = get_pad_path(name)
    if not path.exists():
        return None

    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return Pad.from_dict(data)
    except (json.JSONDecodeError, IOError):
        return None


def load_pad_from_path(path: Path) -> Optional[Pad]:
    """Load a pad from a specific path."""
    if not path.exists():
        return None

    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return Pad.from_dict(data)
    except (json.JSONDecodeError, IOError):
        return None


def list_pads() -> List[dict]:
    """List all saved pads with metadata."""
    ensure_pads_dir()
    pads = []

    for path in PADS_DIR.glob("*.json"):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            pads.append({
                "name": data.get("name", path.stem),
                "path": path,
                "modified": data.get("modified", ""),
            })
        except (json.JSONDecodeError, IOError):
            continue

    # Sort by modified date, newest first
    pads.sort(key=lambda x: x.get("modified", ""), reverse=True)
    return pads


def delete_pad(name: str) -> bool:
    """Delete a pad. Returns True if deleted."""
    path = get_pad_path(name)
    if path.exists():
        path.unlink()
        return True
    return False
