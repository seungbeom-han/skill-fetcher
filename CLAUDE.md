- This skill fetching suite periodically checks updates in AI agent skill github repositories and copies them into the skills in home directory.

## Functionalities
### Extracting skills from remote repo
- Download entire git repo onto @tmp/ and identify skills.
- Skills can be found by searching for directories containing SKILL.md in appropriate header format.
- After finishing skill updates, remove copied git repo.

### Skill update
- Compare headers to match skills in home directory to skills in remote repo.
- Completely replace the skill into the one in remote repo.

### Gitlab CI
- Update crontab. This should not be temporary.

## Implementation guide
- Implement skill fetching functionalities for claude and codex.
- Do not use any external python packages.
