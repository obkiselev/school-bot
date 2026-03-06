# Codex Working Notes (School Bot)

## Scope
- Repository root now contains app files directly (no nested `school_bot/` folder).
- Main branch: `main`.
- Release tag format: `vX.Y.Z`.
- Current implemented version line: `v1.2.0`.

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

## Notes
- Keep secrets only in `.env` (never commit).
- If `.py` changed, deploy + restart service before closing task.
- For SCP from this environment, prefer Git Bash path style (`/d/...`) with `D:/Programs/Git/bin/bash.exe`.
- Final user-facing line for completed requests: `Задача завершена, можно проверять.`
