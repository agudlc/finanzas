## Committing

Stage the work, then stop and ask. The user reads the diff in VS Code and says
when to go ahead. This holds even when a skill says to commit.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues on `agudlc/finanzas` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the default five triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
