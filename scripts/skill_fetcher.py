#!/usr/bin/env python3
"""Skill fetching suite.

Periodically checks AI agent skill GitHub/GitLab repositories for updates and
copies matching skills into the local skill directories for ``claude`` and
``codex``.

Workflow (see ../CLAUDE.md):
  1. Clone each configured git repo into ``data/tmp/``.
  2. Identify skills: directories containing a ``SKILL.md`` with a valid
     frontmatter header (``name`` + ``description``).
  3. Match remote skills to local skills by their frontmatter ``name``.
  4. Completely replace each matched local skill with the remote version.
  5. Remove the cloned repo when finished.

Only the Python standard library is used -- no external packages.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Repository root (parent of this scripts/ directory).
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_TMP = ROOT / "tmp"

# Where each agent keeps its skills. Resolved at runtime so $HOME is honoured.
SKILL_TARGETS = {
    "claude": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".codex" / "skills",
}


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_config(path: Path) -> dict:
    """Load and validate config.json.

    The template ships with placeholder values; those are filtered out so a
    freshly-cloned repo does not try to clone a non-URL.
    """
    with open(path) as fh:
        config = json.load(fh)

    urls = []
    for url in config.get("git_repo_urls", []):
        url = str(url).strip()
        # Skip blanks and the descriptive placeholder shipped in the template.
        # Real git URLs / paths never contain whitespace, so that's a safe filter.
        if not url or any(c.isspace() for c in url):
            continue
        urls.append(url)
    config["git_repo_urls"] = urls
    config.setdefault("crontab_args", {})
    return config


# --------------------------------------------------------------------------- #
# SKILL.md parsing
# --------------------------------------------------------------------------- #
def parse_frontmatter(skill_md: Path) -> dict | None:
    """Parse the leading ``---`` delimited YAML-ish frontmatter of a SKILL.md.

    Returns a dict of the top-level scalar keys (notably ``name`` and
    ``description``) or ``None`` if the file lacks a valid header. Only simple
    ``key: value`` pairs are extracted -- enough to match skills by name -- so
    no YAML dependency is required.
    """
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    header: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        # Only consider top-level keys (no indentation) of the form "key: value".
        if line and not line[0].isspace() and ":" in line:
            key, _, value = line.partition(":")
            header[key.strip()] = value.strip()
    else:
        # No closing delimiter found -> malformed header.
        return None

    return header


def is_valid_skill_header(header: dict | None) -> bool:
    """A skill header must declare a non-empty name and description."""
    return bool(header) and bool(header.get("name")) and bool(header.get("description"))


def find_skills(root: Path) -> dict[str, Path]:
    """Find every skill under ``root``.

    A skill is a directory containing a ``SKILL.md`` with a valid header.
    Returns a mapping of frontmatter ``name`` -> skill directory.
    On duplicate names the first one found wins (a warning is printed).
    """
    skills: dict[str, Path] = {}
    for skill_md in sorted(root.rglob("SKILL.md")):
        header = parse_frontmatter(skill_md)
        if not is_valid_skill_header(header):
            continue
        name = header["name"]
        skill_dir = skill_md.parent
        if name in skills:
            print(f"  ! duplicate skill name '{name}' at {skill_dir} (keeping {skills[name]})")
            continue
        skills[name] = skill_dir
    return skills


# --------------------------------------------------------------------------- #
# Git
# --------------------------------------------------------------------------- #
def clone_repo(url: str, dest: Path) -> bool:
    """Shallow-clone ``url`` into ``dest``. Returns True on success."""
    if dest.exists():
        shutil.rmtree(dest)
    print(f"  cloning {url}")
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        print(f"  ! clone failed:\n{result.stdout.strip()}")
        return False
    return True


# --------------------------------------------------------------------------- #
# Skill update
# --------------------------------------------------------------------------- #
def replace_skill(remote_dir: Path, target_dir: Path) -> None:
    """Completely replace ``target_dir`` with the contents of ``remote_dir``."""
    if target_dir.exists():
        shutil.rmtree(target_dir)
    # Copy everything except any embedded VCS metadata.
    shutil.copytree(
        remote_dir,
        target_dir,
        ignore=shutil.ignore_patterns(".git", ".gitignore"),
    )


def update_target(remote_skills: dict[str, Path], target_name: str, target_root: Path,
                  dry_run: bool = False) -> int:
    """Update one agent's skill directory from the remote skills.

    Only skills already present locally (matched by name) are replaced, per the
    update spec. Returns the number of skills updated.
    """
    if not target_root.exists():
        print(f"  - {target_name}: skill dir {target_root} missing, skipping")
        return 0

    local_skills = find_skills(target_root)
    updated = 0
    for name, remote_dir in sorted(remote_skills.items()):
        if name not in local_skills:
            continue
        target_dir = local_skills[name]
        action = "would update" if dry_run else "updating"
        print(f"  - {target_name}: {action} '{name}' -> {target_dir}")
        if not dry_run:
            replace_skill(remote_dir, target_dir)
        updated += 1
    return updated


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def fetch_all(config: dict, tmp_root: Path, targets: dict[str, Path],
              dry_run: bool = False) -> int:
    """Run the full fetch/update cycle. Returns total skills updated."""
    urls = config["git_repo_urls"]
    if not urls:
        print("No git_repo_urls configured; nothing to do.")
        return 0

    tmp_root.mkdir(parents=True, exist_ok=True)
    total_updated = 0

    for url in urls:
        print(f"\n== {url} ==")
        # Use a unique temp dir per repo to avoid name collisions.
        repo_dir = Path(tempfile.mkdtemp(prefix="repo-", dir=tmp_root))
        try:
            if not clone_repo(url, repo_dir):
                continue
            remote_skills = find_skills(repo_dir)
            print(f"  found {len(remote_skills)} skill(s) in repo")
            for target_name, target_root in targets.items():
                total_updated += update_target(
                    remote_skills, target_name, target_root, dry_run=dry_run
                )
        finally:
            # Always remove the copied git repo.
            shutil.rmtree(repo_dir, ignore_errors=True)

    print(f"\nDone. {total_updated} skill update(s) "
          f"{'simulated' if dry_run else 'applied'}.")
    return total_updated


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG,
                        help=f"Path to config.json (default: {DEFAULT_CONFIG})")
    parser.add_argument("--tmp", type=Path, default=DEFAULT_TMP,
                        help=f"Temp dir for clones (default: {DEFAULT_TMP})")
    parser.add_argument("--target", action="append", choices=sorted(SKILL_TARGETS),
                        help="Limit to specific agent target(s); repeatable. "
                             "Default: all (claude, codex).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without modifying skills.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    config = load_config(args.config)

    if args.target:
        targets = {name: SKILL_TARGETS[name] for name in args.target}
    else:
        targets = dict(SKILL_TARGETS)

    fetch_all(config, args.tmp, targets, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
