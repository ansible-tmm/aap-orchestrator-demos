# Service Health 101: Service State Routing

**Status: Coming soon** — scaffold only. Playbooks and AO workflow JSON not built yet.

## What this demo shows

One host, one service (`httpd`). Run a check playbook that publishes `service_state`. Route remediation in a single switch — no nested Controller decision trees.

| `service_state` | Path | Planned action |
|---|---|---|
| `active` | Green — done | Log OK, no changes |
| `inactive` | Yellow — start it | Start the service |
| `failed` | Orange — recover | Inspect logs and restart |
| `not-found` | Red — install | Install the package and enable the unit |

## Workflow

```mermaid
flowchart LR
  Trigger[Manual or schedule] --> CheckJT[JT: check_service]
  CheckJT --> Switch{service_state}
  Switch -->|active| Done[JT: remediate_log_ok]
  Switch -->|inactive| Start[JT: remediate_start_service]
  Switch -->|failed| Recover[JT: remediate_restart_service]
  Switch -->|not-found| Install[JT: remediate_install_service]
```

## Playbooks

🚧 **Under development** — playbook list and source links will be added when this demo is built.

## Why not binary branching?

The same four outcomes in a Controller-style workflow require nested success/failure steps that still guess at failure meaning. The switch reads one artifact and routes by **meaning**.

## Planned artifacts

When built, this level will include:

```

  ao/               # automation orchestrator workflow JSON
  playbooks/    # check_service + four remediate playbooks
  README.md         # this file
```

## Demo ideas

- Stop `httpd` → workflow routes to **inactive** → start path
- `dnf remove httpd` → workflow routes to **not-found** → install path
