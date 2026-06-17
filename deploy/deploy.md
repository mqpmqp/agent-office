# VPS Deployment Notes

This directory contains examples only. Do not copy files into `/etc/systemd` or other system directories automatically from this project.

## Package Locally

From the project root:

```bash
python -m compileall -q agent_office
bash scripts/verify.sh
```

Then archive the project while excluding runtime artifacts such as `.ai/tasks/`, `.ai/logs/`, `.ai/tmp/`, `.ai/finalize/`, caches, and local environment files.

## Upload To VPS

Human operator example:

```bash
scp agent-office.tar.gz user@host:/tmp/
ssh user@host
sudo mkdir -p /opt/agent-office
sudo tar -xzf /tmp/agent-office.tar.gz -C /opt/agent-office --strip-components=1
cd /opt/agent-office
python3 -m compileall -q agent_office
bash scripts/verify.sh
```

## Optional systemd Setup

Use `deploy/systemd.service.example` as a template only. A human operator may copy and adapt it:

```bash
sudo cp deploy/systemd.service.example /etc/systemd/system/agent-office.service
sudo systemctl daemon-reload
sudo systemctl start agent-office.service
sudo systemctl status agent-office.service
```

The example runs a mock smoke workflow and does not call real Gemini, Codex, Grok Build, or Claude Code providers.

## Real Adapter Boundary

Mock mode proves the protocol. Real adapters should be added later behind the same artifact contract:

- Gemini writes `gemini-context.md`.
- Codex writes `codex-report.md` and `patch.diff`.
- Grok Build writes `grok-review.md`.
- Claude reads only `final-for-claude.md` and writes `claude-decision.md`.

Credentials must stay in environment variables or operator-managed secret stores. They must not be committed or written into `.ai/tasks/` artifacts.
