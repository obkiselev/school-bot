# Codex Working Notes (School Bot)

## Scope
- Repository root now contains app files directly (no nested `school_bot/` folder).
- Main branch: `main`.
- Release tag format: `vX.Y.Z`.
- Current implemented version line: `v1.7.5`.

## Release Checklist
1. Update version references in `README.md`, `readme.txt`, `PROGRESS.md`.
2. Run tests: `pytest -q`.
3. Commit with release message.
4. Create tag: `git tag vX.Y.Z`.
5. Push branch and tag:
   - `git push origin main`
   - `git push origin vX.Y.Z`
6. Verify remote:
   - `git ls-remote https://github.com/obkiselev/school-bot refs/heads/main refs/tags/vX.Y.Z`

## Deploy Checklist (server)
- Server: `45.152.113.91`
- SSH port: `4422`
- User: `school_bot`
- App dir: `/opt/school_bot`
- Service: `school_bot.service`

Commands:
```bash
SSH_KEY="~/.ssh/id_ed25519_rag"
SSH="ssh -i $SSH_KEY -p 4422 school_bot@45.152.113.91"

tar czf /tmp/school_bot.tar.gz --exclude=venv --exclude=data --exclude=.git --exclude=__pycache__ -C /path/to/repo .
scp -i "$SSH_KEY" -P 4422 /tmp/school_bot.tar.gz school_bot@45.152.113.91:/tmp/
$SSH "cd /opt/school_bot && tar xzf /tmp/school_bot.tar.gz && venv/bin/pip install -r requirements.txt"
$SSH "sudo systemctl restart school_bot"
$SSH "sudo systemctl status school_bot --no-pager -l"
```

## Machine Profiles

- KATANA 17:
  - SSH key: `C:\Users\Олег\.ssh\id_ed25519_rag`
  - Typical repo root: `E:\claude`
  - Deploy script path: `E:\claude\school_bot\_repo\work\deploy-school-bot.ps1`
  - Known issue: deploy script may fail on `scp` port handling; fallback to manual `scp -P 4422` + remote `ssh` commands.

- Lenovo:
  - SSH key: `C:\Users\OKiselev.KOMPUTER\.ssh\id_ed25519_rag`
  - Same release/deploy flow, but local paths can differ.
  - Before deploy, auto-detect local specifics (`git rev-parse --show-toplevel`, `Get-Command ssh,scp,tar`) and continue without asking user.

## Notes
- Keep secrets only in `.env` (never commit).
- If `.py` changed, deploy + restart service before closing task.
- For SCP from this environment, prefer Git Bash path style (`/d/...`) with `D:/Programs/Git/bin/bash.exe`.
- Final user-facing line for completed requests: `Задача завершена, можно проверять.`

## Autonomy Policy (No Confirmation)
- Do not ask the user for confirmation for: `git add/commit/tag/push/rebase`, release fixation, deploy, restart, or health/status checks.
- If push is rejected (`non-fast-forward`), run `git fetch` + `git rebase origin/main` + `git push` automatically.
- Always update development history files on release/fixation: `README.md`, `readme.txt`, `PROGRESS.md`.
- Always include in final report: commit hash, tag, test result, deploy result, service status.
- Git/version fixation rule: all local git actions and GitHub push actions related to release/fixation are always performed autonomously without asking the user again, including repeated confirmations for local commit/tag/push flows.
- If standard git fixation flow fails, immediately try all reasonable known workarounds autonomously until the result is achieved. This includes restaging exact files, checking tag/branch state, recreating or force-updating tags, retrying push after fetch/rebase, and using any already-known project-specific git/deploy fallback path. The user cares about the final commit/tag/push result, not about intermediate git friction.
