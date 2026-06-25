# skill-fetcher

Periodically syncs AI agent skills from remote git repositories into the local
skill directories for **claude** (`~/.claude/skills`) and **codex**
(`~/.codex/skills`).

Pure Python standard library — no external packages.

## How it works

For each repo URL in `config.json`:

1. Shallow-clone it into `data/tmp/` (a unique temp dir per repo).
2. Discover skills: any directory containing a `SKILL.md` whose frontmatter
   header declares a `name` and `description`.
3. Match each remote skill to a local skill **by frontmatter `name`**.
4. **Completely replace** each matched local skill directory with the remote
   one (for both claude and codex).
5. Remove the cloned repo.

Only skills that already exist locally are updated; unmatched remote skills are
left alone. Malformed `SKILL.md` files (no valid header) are ignored.

## Configuration — `config.json`

```json
{
    "crontab_args": {
        "minute": "0", "hour": "3",
        "day_of_month": "*", "month": "*", "day_of_week": "*"
    },
    "git_repo_urls": [
        "https://github.com/example/agent-skills.git"
    ]
}
```

- `git_repo_urls` — repositories to fetch skills from. The placeholder line is
  ignored automatically.
- `crontab_args` — schedule fields for the cron job (any omitted field defaults
  to the values above: daily at 03:00).

## Usage

Run a sync manually:

```bash
python3 scripts/skill_fetcher.py            # update claude + codex
python3 scripts/skill_fetcher.py --dry-run  # preview, no changes
python3 scripts/skill_fetcher.py --target codex   # one agent only
```

Install the recurring cron job (persistent — survives reboots/sessions):

```bash
python3 scripts/install_crontab.py          # install / update the entry
python3 scripts/install_crontab.py --print  # show the line without installing
python3 scripts/install_crontab.py --remove # uninstall
```

Installation is idempotent: re-running replaces the managed entry (marked with a
comment) without duplicating it or disturbing other crontab lines. Cron output
is appended to `data/skill_fetcher.log`.
