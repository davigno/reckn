"""Entry point for running Reckn as a module."""

import argparse
import sys

from . import __version__
from .pad import list_pads, load_pad, PADS_DIR


def install_desktop():
    """Install desktop entry and icon for Linux desktop integration."""
    import shutil
    import subprocess
    from pathlib import Path

    pkg_dir = Path(__file__).parent
    icon_src = pkg_dir / "assets" / "reckn.svg"

    if not icon_src.exists():
        print(f"Error: icon not found at {icon_src}", file=sys.stderr)
        sys.exit(1)

    # Install icon
    icon_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
    icon_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(icon_src, icon_dir / "reckn.svg")
    print(f"  Icon -> {icon_dir / 'reckn.svg'}")

    # Generate and install .desktop file
    reckn_exe = shutil.which("reckn") or "reckn"
    desktop_content = (
        "[Desktop Entry]\n"
        "Name=Reckn\n"
        "Comment=A calculator notepad for the terminal\n"
        f"Exec={reckn_exe}\n"
        "Icon=reckn\n"
        "Terminal=true\n"
        "Type=Application\n"
        "Categories=Utility;Calculator;\n"
        "Keywords=calculator;notepad;math;units;currency;\n"
    )

    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = desktop_dir / "reckn.desktop"
    desktop_file.write_text(desktop_content)
    print(f"  Desktop entry -> {desktop_file}")

    # Update desktop database (best effort)
    try:
        subprocess.run(["update-desktop-database", str(desktop_dir)],
                       capture_output=True, check=False)
    except FileNotFoundError:
        pass

    print("Done. Reckn should now appear in your application menu.")


def main():
    parser = argparse.ArgumentParser(
        prog="reckn",
        description="Reckn - A calculator notepad for the terminal"
    )
    parser.add_argument(
        "pad_name",
        nargs="?",
        help="Name of pad to open"
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"reckn {__version__}"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all saved pads"
    )
    parser.add_argument(
        "--install-desktop",
        action="store_true",
        help="Install desktop entry and icon (Linux)"
    )

    args = parser.parse_args()

    if args.install_desktop:
        install_desktop()
        return

    if args.list:
        pads = list_pads()
        if not pads:
            print(f"No saved pads found in {PADS_DIR}")
        else:
            print(f"Saved pads ({len(pads)}):")
            for pad in pads:
                modified = pad.get("modified", "")[:10]  # Just the date part
                print(f"  {pad['name']:20} {modified}")
        return

    # Import app here to avoid loading Textual for --list
    from .app import RecknApp

    app = RecknApp(pad_name=args.pad_name)
    app.run()


if __name__ == "__main__":
    main()
