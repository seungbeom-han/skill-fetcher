#!/usr/bin/env python3
"""Install a persistent crontab entry that runs the skill fetcher.

The schedule is taken from ``config.json``'s ``crontab_args`` block, e.g.::

    "crontab_args": {
        "minute": "0",
        "hour": "3",
        "day_of_month": "*",
        "month": "*",
        "day_of_week": "*"
    }

The entry is written into the user's real crontab (via ``crontab -``), so it
survives reboots and shell sessions -- it is not temporary. Re-running this
script replaces the previously installed entry rather than duplicating it.

Only the Python standard library is used -- no external packages.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.json"
FETCHER = ROOT / "scripts" / "skill_fetcher.py"

# Marker used to find/replace our own line in the crontab idempotently.
MARKER = "# skill-fetcher (managed by install_crontab.py)"

CRON_FIELDS = ("minute", "hour", "day_of_month", "month", "day_of_week")
CRON_DEFAULTS = {
    "minute": "0",
    "hour": "3",
    "day_of_month": "*",
    "month": "*",
    "day_of_week": "*",
}


def build_schedule(crontab_args: dict) -> str:
    """Build the five-field cron schedule from config, filling defaults."""
    return " ".join(str(crontab_args.get(f, CRON_DEFAULTS[f])) for f in CRON_FIELDS)


def build_entry(schedule: str, python: str) -> str:
    """Build the full crontab line (with marker comment)."""
    # Redirect output to a log next to the repo for later inspection.
    log = ROOT / "data" / "skill_fetcher.log"
    command = f"{python} {FETCHER} >> {log} 2>&1"
    return f"{MARKER}\n{schedule} {command}"


def read_crontab() -> str:
    """Return the current crontab contents (empty string if none)."""
    result = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        # No crontab yet -> treat as empty.
        return ""
    return result.stdout


def strip_existing(crontab: str) -> str:
    """Remove any previously-installed skill-fetcher entry (marker + next line)."""
    lines = crontab.splitlines()
    kept: list[str] = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if line.strip() == MARKER:
            skip_next = True  # drop the command line that follows the marker
            continue
        kept.append(line)
    return "\n".join(kept)


def write_crontab(content: str) -> None:
    content = content.rstrip("\n") + "\n"
    proc = subprocess.run(["crontab", "-"], input=content, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"crontab install failed: {proc.stderr.strip()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--python", default=sys.executable,
                        help="Python interpreter to run the fetcher with.")
    parser.add_argument("--remove", action="store_true",
                        help="Remove the managed entry instead of installing it.")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="Print the entry that would be installed and exit.")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    with open(args.config) as fh:
        config = json.load(fh)
    schedule = build_schedule(config.get("crontab_args", {}))
    entry = build_entry(schedule, args.python)

    if args.print_only:
        print(entry)
        return 0

    current = read_crontab()
    stripped = strip_existing(current)

    if args.remove:
        write_crontab(stripped)
        print("Removed skill-fetcher crontab entry.")
        return 0

    new_crontab = (stripped.rstrip("\n") + "\n\n" + entry).lstrip("\n")
    write_crontab(new_crontab)
    print("Installed skill-fetcher crontab entry:")
    print(f"  {schedule} -> {FETCHER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
